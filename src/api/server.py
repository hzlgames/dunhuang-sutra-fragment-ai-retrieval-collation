import re
import uuid
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv
from fastapi import (
    BackgroundTasks,
    FastAPI,
    File,
    HTTPException,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware

from src.ai_agent import AgentConfig, CBETAAgent
from src.schemas import FinalAnswer
from src.api.schemas import (
    BatchCreateResponse,
    BatchResultsResponse,
    BatchStatusResponse,
    CancelResponse,
    JobCreateResponse,
    JobStatusResponse,
    JobStatusEnum,
    MetaResponse,
    ProcessResponse,
    ResumeResponse,
    RoundInfo,
)
from src.api.task_store import InMemoryTaskStore
from src.batch_jobs import BatchProcessor
from src.config import get_output_dir, supports_batch, VERSION
from src.main import summarize_final_answer, build_fragment_note

load_dotenv()

app = FastAPI(title="Dunhuang Fragment Analyzer API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

task_store = InMemoryTaskStore()
agent = CBETAAgent(AgentConfig(verbose=False))
batch_processor = BatchProcessor(agent=agent)


def _sanitize_output_name(name: str) -> str:
    """将文件/文件夹名称中不安全的字符替换为下划线。"""
    safe = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff._-]+", "_", name.strip())
    safe = safe.strip("._")
    return safe or "output"


def _derive_pic_name(original_name: Optional[str], image_path: Path) -> str:
    """根据原始文件名或临时文件路径推导图片名称。"""
    if original_name:
        candidate = Path(original_name).stem
    else:
        candidate = image_path.stem
    return _sanitize_output_name(candidate)


async def _persist_upload(file: UploadFile, namespace: str) -> Path:
    suffix = Path(file.filename or "").suffix or ".png"
    tmp_dir = Path("tmp") / namespace
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = tmp_dir / f"{uuid.uuid4()}{suffix}"
    data = await file.read()
    tmp_path.write_bytes(data)
    return tmp_path


def _run_single_job(
    task_id: str,
    image_path: Path,
    *,
    original_name: Optional[str] = None,
    resume_session_id: Optional[str] = None,
):
    """
    执行单图分析任务。
    
    Args:
        task_id: 任务 ID
        image_path: 图片路径
        resume_session_id: 若提供，则基于已有 session 续传
    """
    session_id = None
    should_delete_image = True  # 默认删除临时图片
    try:
        # 检查是否已被取消
        if task_store.is_cancel_requested(task_id):
            task_store.update(task_id, status=JobStatusEnum.cancelled)
            return
        
        task_store.update(task_id, status=JobStatusEnum.running, image_path=str(image_path))
        
        # 使用已有 session 或创建新 session
        if resume_session_id:
            session_id = resume_session_id
        else:
            session_id = agent.session_manager.create_session()
        task_store.update(task_id, session_id=session_id)
        
        # 执行分析（注意：参数名是 resume_session_id）
        result: FinalAnswer | None = agent.analyze_and_locate(
            image_path=str(image_path), 
            resume_session_id=session_id,
            cancel_check=lambda: task_store.is_cancel_requested(task_id),
        )
        
        # 再次检查是否被取消
        if task_store.is_cancel_requested(task_id):
            task_store.update(task_id, status=JobStatusEnum.cancelled)
            should_delete_image = False  # 取消时保留图片以便续传
            return
        
        if result is None:
            # 当上游因为 Gemini 503 等原因无法给出结构化结果时，优雅地标记为失败
            task_store.update(
                task_id,
                status=JobStatusEnum.failed,
                error="分析流程未返回结构化结果（可能是模型过载或网络错误），请稍后重试。",
            )
            should_delete_image = False  # 失败时保留图片以便续传
            return
        
        # 保存结果文件到输出目录，每个图片独立子文件夹
        output_base = get_output_dir()
        pic_name = _derive_pic_name(original_name, image_path)
        
        # 创建以图片名称命名的子文件夹
        pic_output_dir = output_base / pic_name
        pic_output_dir.mkdir(parents=True, exist_ok=True)
        
        # 保存 JSON 结果
        json_path = pic_output_dir / f"{pic_name}_result.json"
        json_path.write_text(
            result.model_dump_json(indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        
        # 保存文本报告
        report_path = pic_output_dir / f"{pic_name}_report.txt"
        report_path.write_text(
            summarize_final_answer(result),
            encoding="utf-8",
        )
        
        # 保存文献整理说明
        note_path = pic_output_dir / f"{pic_name}_note.txt"
        note_path.write_text(
            build_fragment_note(result, pic_name),
            encoding="utf-8",
        )
        
        task_store.update(
            task_id,
            status=JobStatusEnum.succeeded,
            result=result.model_dump(mode="json"),
        )
    except Exception as exc:
        task_store.update(task_id, status=JobStatusEnum.failed, error=str(exc))
        should_delete_image = False  # 异常时保留图片以便续传
    finally:
        # 只有成功完成时才删除临时图片
        if should_delete_image:
            try:
                image_path.unlink(missing_ok=True)
            except PermissionError as exc:
                # 仅记录日志，不影响任务最终状态
                print(f"⚠️ 删除临时文件失败（可能被占用）: {image_path} -> {exc}")


@app.post("/api/v1/jobs/image", response_model=JobCreateResponse)
async def create_async_job(
    background_tasks: BackgroundTasks, file: UploadFile = File(...)
):
    if not file:
        raise HTTPException(status_code=400, detail="file is required")
    tmp_path = await _persist_upload(file, "single-job")
    task_id = str(uuid.uuid4())
    task_store.create(task_id)
    original_name = file.filename or Path(tmp_path).name
    background_tasks.add_task(
        _run_single_job,
        task_id,
        tmp_path,
        original_name=original_name,
    )
    return JobCreateResponse(task_id=task_id)


@app.get("/api/v1/jobs/{task_id}", response_model=JobStatusResponse)
async def get_async_job(task_id: str):
    record = task_store.get(task_id)
    if not record:
        raise HTTPException(status_code=404, detail="task not found")
    return JobStatusResponse(
        task_id=record.task_id,
        status=record.status,
        created_at=record.created_at,
        updated_at=record.updated_at,
        result=record.result,
        error=record.error,
    )


@app.post("/api/v1/batches", response_model=BatchCreateResponse)
async def create_batch(
    background_tasks: BackgroundTasks, files: List[UploadFile] = File(...)
):
    if not files:
        raise HTTPException(status_code=400, detail="至少上传一张图片")
    job_entries = []
    for upload in files:
        tmp_path = await _persist_upload(upload, "batch-job")
        original_name = upload.filename or tmp_path.stem
        session_id = str(uuid.uuid4())
        job_entries.append(
            {
                "session_id": session_id,
                "path": tmp_path,
                "alias": Path(original_name).stem or f"batch_{session_id[:8]}",
            }
        )
    batch_id = str(uuid.uuid4())
    background_tasks.add_task(batch_processor.run_batch, batch_id, job_entries)
    return BatchCreateResponse(batch_id=batch_id)


@app.get("/api/v1/batches/{batch_id}", response_model=BatchStatusResponse)
async def get_batch(batch_id: str):
    status = batch_processor.get_status(batch_id)
    if not status:
        raise HTTPException(status_code=404, detail="batch not found")
    return status


@app.get("/api/v1/batches/{batch_id}/results", response_model=BatchResultsResponse)
async def get_batch_results(batch_id: str, session_id: Optional[str] = None):
    results = batch_processor.get_results(batch_id, session_id=session_id)
    if not results:
        raise HTTPException(status_code=404, detail="batch not found")
    return results


@app.get("/api/v1/process/{session_id}", response_model=ProcessResponse)
async def get_process_details(session_id: str):
    """获取 AI 处理的中间过程（思考、工具调用等）"""
    import json
    from pathlib import Path
    
    rounds_file = Path("sessions") / f"{session_id}.rounds.jsonl"
    if not rounds_file.exists():
        raise HTTPException(
            status_code=404, 
            detail=f"未找到 session {session_id} 的处理记录"
        )
    
    rounds = []
    try:
        with open(rounds_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    round_data = json.loads(line)
                    rounds.append(RoundInfo(**round_data))
    except Exception as exc:
        raise HTTPException(
            status_code=500, 
            detail=f"读取处理记录失败: {str(exc)}"
        )
    
    return ProcessResponse(
        session_id=session_id,
        rounds=rounds,
        total_rounds=len(rounds)
    )


@app.get("/api/v1/jobs/{task_id}/process", response_model=ProcessResponse)
async def get_job_process(task_id: str):
    """通过 task_id 获取处理过程"""
    record = task_store.get(task_id)
    if not record:
        raise HTTPException(status_code=404, detail="task not found")
    
    if not record.session_id:
        raise HTTPException(
            status_code=404, 
            detail="该任务没有关联的 session_id，可能任务未开始执行"
        )
    
    # 复用上面的逻辑
    import json
    from pathlib import Path
    
    session_id = record.session_id
    rounds_file = Path("sessions") / f"{session_id}.rounds.jsonl"
    if not rounds_file.exists():
        raise HTTPException(
            status_code=404, 
            detail=f"未找到处理记录（session: {session_id}）"
        )
    
    rounds = []
    try:
        with open(rounds_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    round_data = json.loads(line)
                    rounds.append(RoundInfo(**round_data))
    except Exception as exc:
        raise HTTPException(
            status_code=500, 
            detail=f"读取处理记录失败: {str(exc)}"
        )
    
    return ProcessResponse(
        session_id=session_id,
        rounds=rounds,
        total_rounds=len(rounds)
    )


# ------------------------------------------------------------------ #
# 取消与断点续传接口
# ------------------------------------------------------------------ #

@app.post("/api/v1/jobs/{task_id}/cancel", response_model=CancelResponse)
async def cancel_job(task_id: str):
    """请求取消正在进行的任务。"""
    record = task_store.get(task_id)
    if not record:
        raise HTTPException(status_code=404, detail="task not found")
    
    if record.status not in (JobStatusEnum.pending, JobStatusEnum.running):
        raise HTTPException(
            status_code=400,
            detail=f"任务状态为 {record.status.value}，无法取消"
        )
    
    success = task_store.request_cancel(task_id)
    if not success:
        raise HTTPException(status_code=400, detail="取消请求失败")
    
    # 如果任务还在 PENDING 状态，直接标记为 CANCELLED
    if record.status == JobStatusEnum.pending:
        task_store.update(task_id, status=JobStatusEnum.cancelled)
    
    return CancelResponse(
        task_id=task_id,
        status=JobStatusEnum.cancelled,
        message="取消请求已发送，任务将在下一个检查点停止"
    )


@app.post("/api/v1/jobs/resume", response_model=ResumeResponse)
async def resume_job(
    background_tasks: BackgroundTasks,
    session_id: str,
    file: UploadFile = File(...)
):
    """
    基于已有 session_id 断点续传。
    需要重新上传图片文件。
    """
    if not file:
        raise HTTPException(status_code=400, detail="file is required")
    
    # 验证 session 是否存在
    sessions_dir = Path("sessions")
    rounds_file = sessions_dir / f"{session_id}.rounds.jsonl"
    if not rounds_file.exists():
        raise HTTPException(
            status_code=404,
            detail=f"未找到 session {session_id} 的历史记录，无法续传"
        )
    
    # 保存上传的图片
    tmp_path = await _persist_upload(file, "resume-job")
    
    # 创建新任务
    task_id = str(uuid.uuid4())
    task_store.create(task_id)
    
    # 启动后台任务，传入 resume_session_id
    original_name = file.filename or Path(tmp_path).name
    background_tasks.add_task(
        _run_single_job,
        task_id,
        tmp_path,
        original_name=original_name,
        resume_session_id=session_id,
    )
    
    return ResumeResponse(task_id=task_id, session_id=session_id)


# ------------------------------------------------------------------ #
# 元信息接口
# ------------------------------------------------------------------ #

@app.get("/api/v1/meta", response_model=MetaResponse)
async def get_meta():
    """获取服务元信息，包括输出目录、版本号等。"""
    output_dir = get_output_dir()
    return MetaResponse(
        version=VERSION,
        output_dir=str(output_dir.resolve()),
        supports_batch=supports_batch()
    )

