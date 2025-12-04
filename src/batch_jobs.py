import json
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from google import genai
from google.genai import types
from google.cloud import storage
from PIL import Image

from src.ai_agent import CBETAAgent
from src.schemas import FinalAnswer
from src.main import summarize_final_answer, build_fragment_note
from src.config import get_output_dir
from src.api.schemas import (
    JobStatusEnum,
    BatchStatusResponse,
    BatchResultItem,
    BatchResultsResponse,
)


@dataclass
class SessionJob:
    session_id: str
    alias: str
    image_path: Path
    history: List[types.Content]
    done: bool = False
    error: Optional[str] = None
    final_answer: Optional[FinalAnswer] = None
    last_round: int = 0


class BatchProcessor:
    """
    负责 orchestrate 多任务 × 多轮 Batch API 调度，并与本地 Session 记录互通。
    """

    def __init__(self, agent: CBETAAgent, *, bucket_name: Optional[str] = None):
        self.agent = agent
        # 直接复用 Agent 已初始化好的 Vertex AI 客户端，确保批处理与单图流程共享同一凭据/项目配置。
        self.client = agent.client
        self.gcs_bucket_name = bucket_name or os.getenv(
            "VERTEX_BATCH_BUCKET", "hanhan_dunhuang_batch_storage"
        )
        if not self.gcs_bucket_name:
            raise ValueError(
                "VERTEX_BATCH_BUCKET 未配置，无法使用 Vertex Batch API。"
            )
        self.storage_client = storage.Client()
        self._gcs_bucket = self.storage_client.bucket(self.gcs_bucket_name)
        self._lock = threading.Lock()
        self._batches: Dict[str, Dict] = {}

    # ------------------------------------------------------------------ #
    # Public APIs
    # ------------------------------------------------------------------ #
    def run_batch(self, batch_id: str, jobs: List[Dict[str, Any]]):
        """
        供后台线程调用，串行 orchestrate 整个 Batch 生命周期。
        jobs: [{"session_id": "...", "path": Path()}, ...]
        """
        session_map = {}
        for item in jobs:
            session_id = item["session_id"]
            path = Path(item["path"])
            alias = item.get("alias") or path.stem
            alias = f"{alias}_{session_id[:8]}"
            history = self._build_initial_history(image_path=path)
            self.agent.session_manager.save_session(session_id, [])
            session_map[session_id] = SessionJob(
                session_id=session_id,
                alias=alias,
                image_path=path,
                history=history,
            )

        with self._lock:
            self._batches[batch_id] = {
                "status": JobStatusEnum.batch_pending,
                "round": 0,
                "sessions": session_map,
                "error": None,
            }

        try:
            max_rounds = self.agent.config.max_tool_rounds
            for round_index in range(1, max_rounds + 1):
                pending_sessions = [
                    s for s in session_map.values() if not s.done and not s.error
                ]
                if not pending_sessions:
                    break

                self._update_batch_progress(
                    batch_id, JobStatusEnum.batch_running, round_index
                )

                input_uri, output_uri = self._prepare_batch_round(
                    pending_sessions, batch_id, round_index
                )

                # 使用与单图流程一致的重试策略：
                # - 普通轮：normal_retries 次（AgentConfig.normal_retries）
                # - 每次失败后等待 retry_interval 秒（AgentConfig.retry_interval）
                def _create_and_wait():
                    job = self.client.batches.create(
                        model=self.agent.config.model_name,
                        src=input_uri,
                        config=types.CreateBatchJobConfig(
                            display_name=f"batch-{batch_id}-round-{round_index}",
                            dest=types.BatchJobDestination(gcs_uri=output_uri),
                        ),
                    )
                    return self._wait_for_job(job.name)

                job = self.agent._call_with_retry(
                    _create_and_wait,
                    max_retries=self.agent.config.normal_retries,
                    retry_interval=self.agent.config.retry_interval,
                )

                responses_payload = self._load_batch_outputs(output_uri)
                if not responses_payload:
                    for session in pending_sessions:
                        session.error = "Batch 返回空结果"
                    continue

                for idx, payload in enumerate(responses_payload):
                    if idx >= len(pending_sessions):
                        continue
                    session = pending_sessions[idx]
                    if payload.get("error"):
                        session.error = self._stringify_error(payload["error"])
                        continue

                    response_data = payload.get("response")
                    if not response_data:
                        session.error = "Batch 响应为空"
                        continue

                    try:
                        response = types.GenerateContentResponse.model_validate(
                            response_data
                        )
                    except Exception as exc:
                        session.error = f"解析 Batch 响应失败: {exc}"
                        continue

                    if not response.candidates:
                        session.error = "空响应"
                        continue
                    content = response.candidates[0].content
                    session.history.append(content)

                    round_result = self.agent._handle_model_response(
                        session_id=session.session_id,
                        round_index=round_index,
                        response=response,
                        content=content,
                        stream_handler=None,
                    )

                    session.last_round = round_index

                    if round_result["next_user_content"]:
                        session.history.append(round_result["next_user_content"])

                    if round_result["json_result"]:
                        session.done = True
                        session.final_answer = round_result["json_result"]
                        self._finalize_session(session)
                    elif round_result["should_break"]:
                        session.error = "模型未返回结构化结果"

            # 对仍未完成的 session 进行最终结构化输出
            self._update_batch_progress(
                batch_id, JobStatusEnum.batch_merging, max_rounds + 1
            )
            for session in session_map.values():
                if session.done or session.error:
                    continue
                # 进入最终结构化阶段
                result = self.agent._force_structured_output(
                    session.history, session.session_id
                )
                if result:
                    session.done = True
                    session.final_answer = result
                    self._finalize_session(session)
                else:
                    session.error = "最终结构化输出失败"

            has_error = any(s.error for s in session_map.values())
            final_status = (
                JobStatusEnum.failed if has_error else JobStatusEnum.succeeded
            )
            self._update_batch_progress(batch_id, final_status, max_rounds)
        except Exception as exc:
            # 记录更具体的错误信息，便于通过 HTTP 接口排查 Batch 失败原因
            error_msg = f"Batch 执行异常: {repr(exc)}"
            with self._lock:
                batch = self._batches.get(batch_id)
                if batch:
                    batch["status"] = JobStatusEnum.failed
                    batch["error"] = error_msg
            for session in session_map.values():
                if not session.done and not session.error:
                    session.error = error_msg
        finally:
            # 清理临时图片
            for session in session_map.values():
                try:
                    session.image_path.unlink(missing_ok=True)
                except OSError:
                    pass

    def get_status(self, batch_id: str) -> Optional[BatchStatusResponse]:
        with self._lock:
            batch = self._batches.get(batch_id)
            if not batch:
                return None
            sessions = batch["sessions"]
            total = len(sessions)
            completed = len([s for s in sessions.values() if s.done and not s.error])
            failed = len([s for s in sessions.values() if s.error])
            details = []
            for session in sessions.values():
                details.append(
                    {
                        "session_id": session.session_id,
                        "alias": session.alias,
                        "done": session.done,
                        "error": session.error,
                        "last_round": session.last_round,
                    }
                )
            return BatchStatusResponse(
                batch_id=batch_id,
                status=batch["status"],
                round=batch["round"],
                total_jobs=total,
                completed_jobs=completed,
                failed_jobs=failed,
                details=details,
            )

    def get_results(
        self, batch_id: str, session_id: Optional[str] = None
    ) -> Optional[BatchResultsResponse]:
        with self._lock:
            batch = self._batches.get(batch_id)
            if not batch:
                return None
            sessions = batch["sessions"]
            items = []
            for sid, session in sessions.items():
                if session_id and sid != session_id:
                    continue
                status = (
                    JobStatusEnum.succeeded
                    if session.done and not session.error
                    else JobStatusEnum.failed
                    if session.error
                    else JobStatusEnum.running
                )
                items.append(
                    BatchResultItem(
                        session_id=sid,
                        status=status,
                        result=session.final_answer.model_dump(mode="json")
                        if session.final_answer
                        else None,
                        error=session.error,
                    )
                )
            return BatchResultsResponse(batch_id=batch_id, items=items)

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #
    def _build_initial_history(self, image_path: Path) -> List[types.Content]:
        prompt = self.agent._build_prompt(ocr_text=None, image_path=None)
        parts: List[types.Part] = [types.Part(text=prompt)]
        try:
            with Image.open(image_path) as img:
                mime_type = Image.MIME.get(img.format, "image/png")
        except Exception:
            mime_type = "image/png"
        image_bytes = image_path.read_bytes()
        parts.append(types.Part.from_bytes(data=image_bytes, mime_type=mime_type))
        return [types.Content(role="user", parts=parts)]

    def _stringify_error(self, error: Any) -> str:
        """将 Google Batch API 的 JobError 等对象安全地转成字符串。"""
        if error is None:
            return ""
        if isinstance(error, str):
            return error

        def _to_serializable(obj: Any) -> Any:
            if hasattr(obj, "to_dict"):
                return obj.to_dict()
            if hasattr(obj, "model_dump"):
                return obj.model_dump()
            if isinstance(obj, dict):
                return {k: _to_serializable(v) for k, v in obj.items()}
            if isinstance(obj, (list, tuple)):
                return [_to_serializable(v) for v in obj]
            return str(obj)

        try:
            return json.dumps(_to_serializable(error), ensure_ascii=False)
        except Exception:
            return repr(error)

    def _wait_for_job(self, job_name: str):
        completed_states = {
            "JOB_STATE_SUCCEEDED",
            "JOB_STATE_FAILED",
            "JOB_STATE_CANCELLED",
            "JOB_STATE_EXPIRED",
        }
        while True:
            job = self.client.batches.get(name=job_name)
            if job.state in completed_states:
                if job.state != "JOB_STATE_SUCCEEDED":
                    raise RuntimeError(f"Batch job {job_name} failed: {job.state}")
                return job
            time.sleep(5)

    def _finalize_session(self, session: SessionJob):
        if not session.final_answer:
            return
        self.agent.session_manager.save_session(
            session.session_id, session.history
        )
        output_base = get_output_dir()
        
        # 从 alias 中提取原始文件名（去掉 session_id 后缀）
        # alias 格式为: filename_sessionid[:8]
        # 提取原始文件名作为文件夹名
        if "_" in session.alias:
            # 去掉最后一个下划线及其后的内容（session_id）
            pic_name = session.alias.rsplit("_", 1)[0]
        else:
            pic_name = session.alias
        
        # 创建以图片名称命名的子文件夹
        pic_output_dir = output_base / pic_name
        pic_output_dir.mkdir(parents=True, exist_ok=True)

        json_path = pic_output_dir / f"{pic_name}_result.json"
        json_path.write_text(
            session.final_answer.model_dump_json(indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        report_path = pic_output_dir / f"{pic_name}_report.txt"
        report_path.write_text(
            summarize_final_answer(session.final_answer),
            encoding="utf-8",
        )

        note_path = pic_output_dir / f"{pic_name}_note.txt"
        note_path.write_text(
            build_fragment_note(session.final_answer, pic_name),
            encoding="utf-8",
        )

    def _update_batch_progress(
        self, batch_id: str, status: JobStatusEnum, round_index: int
    ):
        with self._lock:
            batch = self._batches.get(batch_id)
            if not batch:
                return
            batch["status"] = status
            batch["round"] = round_index

    # ------------------------------------------------------------------ #
    # GCS helpers
    # ------------------------------------------------------------------ #
    def _prepare_batch_round(
        self, sessions: List[SessionJob], batch_id: str, round_index: int
    ) -> Tuple[str, str]:
        """
        构建 JSONL 输入文件并上传到 GCS，返回 (input_uri, output_uri)。
        """
        local_dir = Path("tmp") / "batch_inputs" / batch_id / f"round_{round_index:02d}"
        local_dir.mkdir(parents=True, exist_ok=True)
        input_path = local_dir / "input.jsonl"

        with input_path.open("w", encoding="utf-8") as f:
            for session in sessions:
                contents_payload = [
                    json.loads(content.model_dump_json()) for content in session.history
                ]
                record = {"request": {"contents": contents_payload}}
                f.write(json.dumps(record, ensure_ascii=False))
                f.write("\n")

        gcs_input_path = f"batches/{batch_id}/round_{round_index:02d}/input.jsonl"
        self._upload_file_to_gcs(input_path, gcs_input_path)

        gcs_output_prefix = f"batches/{batch_id}/round_{round_index:02d}/outputs/"
        input_uri = f"gs://{self.gcs_bucket_name}/{gcs_input_path}"
        output_uri = f"gs://{self.gcs_bucket_name}/{gcs_output_prefix}"
        return input_uri, output_uri

    def _upload_file_to_gcs(self, local_path: Path, blob_path: str):
        blob = self._gcs_bucket.blob(blob_path)
        blob.upload_from_filename(str(local_path))

    def _load_batch_outputs(self, dest_uri: str) -> List[Dict[str, Any]]:
        bucket_name, prefix = self._split_gs_uri(dest_uri)
        bucket = (
            self._gcs_bucket
            if bucket_name == self.gcs_bucket_name
            else self.storage_client.bucket(bucket_name)
        )

        payloads: List[Dict[str, Any]] = []
        for blob in bucket.list_blobs(prefix=prefix):
            if not blob.name.endswith(".jsonl"):
                continue
            data = blob.download_as_text(encoding="utf-8")
            for line in data.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    payloads.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return payloads

    @staticmethod
    def _split_gs_uri(uri: str) -> Tuple[str, str]:
        if not uri.startswith("gs://"):
            raise ValueError(f"无效的 GCS URI: {uri}")
        path = uri[5:]
        parts = path.split("/", 1)
        bucket = parts[0]
        prefix = parts[1] if len(parts) > 1 else ""
        return bucket, prefix

