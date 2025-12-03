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
    JobCreateResponse,
    JobStatusResponse,
    JobStatusEnum,
    ProcessResponse,
    RoundInfo,
)
from src.api.task_store import InMemoryTaskStore
from src.batch_jobs import BatchProcessor

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


async def _persist_upload(file: UploadFile, namespace: str) -> Path:
    suffix = Path(file.filename or "").suffix or ".png"
    tmp_dir = Path("tmp") / namespace
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = tmp_dir / f"{uuid.uuid4()}{suffix}"
    data = await file.read()
    tmp_path.write_bytes(data)
    return tmp_path


def _run_single_job(task_id: str, image_path: Path):
    session_id = None
    try:
        task_store.update(task_id, status=JobStatusEnum.running)
        # 创建新 session
        session_id = agent.session_manager.create_session()
        task_store.update(task_id, session_id=session_id)
        # 执行分析（注意：参数名是 resume_session_id）
        result: FinalAnswer | None = agent.analyze_and_locate(
            image_path=str(image_path), 
            resume_session_id=session_id
        )
        if result is None:
            # 当上游因为 Gemini 503 等原因无法给出结构化结果时，优雅地标记为失败
            task_store.update(
                task_id,
                status=JobStatusEnum.failed,
                error="分析流程未返回结构化结果（可能是模型过载或网络错误），请稍后重试。",
            )
            return
        task_store.update(
            task_id,
            status=JobStatusEnum.succeeded,
            result=result.model_dump(mode="json"),
        )
    except Exception as exc:
        task_store.update(task_id, status=JobStatusEnum.failed, error=str(exc))
    finally:
        # 避免 Windows 上因文件句柄未关闭而导致 PermissionError 终止整个请求
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
    background_tasks.add_task(_run_single_job, task_id, tmp_path)
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

