import json
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from google import genai
from google.genai import types
from PIL import Image

from src.ai_agent import CBETAAgent
from src.schemas import FinalAnswer
from src.main import summarize_final_answer, build_fragment_note
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

    def __init__(self, agent: CBETAAgent):
        self.agent = agent
        self.client = genai.Client()
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

                inline_requests = self._build_inline_requests(pending_sessions)

                # 使用与单图流程一致的重试策略：
                # - 普通轮：normal_retries 次（AgentConfig.normal_retries）
                # - 每次失败后等待 retry_interval 秒（AgentConfig.retry_interval）
                def _create_and_wait():
                    job = self.client.batches.create(
                        model=self.agent.config.model_name,
                        src=inline_requests,
                        config={
                            "display_name": f"batch-{batch_id}-round-{round_index}"
                        },
                    )
                    return self._wait_for_job(job.name)

                job = self.agent._call_with_retry(
                    _create_and_wait,
                    max_retries=self.agent.config.normal_retries,
                    retry_interval=self.agent.config.retry_interval,
                )

                # 根据 google-genai 的最新 Batch API，结果位于 job.dest.inlined_responses
                dest = getattr(job, "dest", None)
                inline_responses = getattr(dest, "inlined_responses", []) if dest else []

                for idx, item in enumerate(inline_responses):
                    # 新版 Batch API 不再接受自定义 key/request 包装，
                    # 因此这里直接按照 inline_responses 与 pending_sessions 的顺序一一对应。
                    if idx >= len(pending_sessions):
                        continue
                    session = pending_sessions[idx]
                    if item.error:
                        session.error = self._stringify_error(item.error)
                        continue

                    response = item.response
                    if not response or not response.candidates:
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

    def _build_inline_requests(self, sessions: List[SessionJob]) -> List[Dict]:
        inline_requests: List[Dict[str, Any]] = []
        for session in sessions:
            # 当前 google-genai Batch API 的 BatchJobSource 仅接受 contents（及可选 config），
            # 不允许在 inlined_requests 中直接传 tools / tool_config / generation_config，
            # 否则会触发 Pydantic 的 extra_forbidden 校验错误。
            # 因此这里仅传入 contents，保持与 minimal_batch_test 的用法一致。
            inline_requests.append(
                {
                    "contents": session.history,
                }
            )
        return inline_requests

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
        output_dir = Path("output")
        output_dir.mkdir(parents=True, exist_ok=True)

        json_path = output_dir / f"{session.alias}_result.json"
        json_path.write_text(
            session.final_answer.model_dump_json(indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        report_path = output_dir / f"{session.alias}_report.txt"
        report_path.write_text(
            summarize_final_answer(session.final_answer),
            encoding="utf-8",
        )

        note_path = output_dir / f"{session.alias}_note.txt"
        note_path.write_text(
            build_fragment_note(session.final_answer, session.alias),
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

