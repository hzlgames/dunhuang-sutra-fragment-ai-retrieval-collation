import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional

from .schemas import JobStatusEnum


@dataclass
class TaskRecord:
    task_id: str
    status: JobStatusEnum
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    session_id: Optional[str] = None  # 关联的 session_id
    image_path: Optional[str] = None  # 原始图片路径（用于断点续传）
    cancel_requested: bool = False  # 取消标志


class InMemoryTaskStore:
    """线程安全的内存任务存储，满足异步 HTTP 接口需求。"""

    def __init__(self):
        self._lock = threading.Lock()
        self._tasks: Dict[str, TaskRecord] = {}

    def create(self, task_id: str) -> TaskRecord:
        with self._lock:
            record = TaskRecord(task_id=task_id, status=JobStatusEnum.pending)
            self._tasks[task_id] = record
            return record

    def update(
        self,
        task_id: str,
        *,
        status: Optional[JobStatusEnum] = None,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        session_id: Optional[str] = None,
        image_path: Optional[str] = None,
    ) -> Optional[TaskRecord]:
        with self._lock:
            record = self._tasks.get(task_id)
            if not record:
                return None
            if status:
                record.status = status
            if result is not None:
                record.result = result
            if error is not None:
                record.error = error
            if session_id is not None:
                record.session_id = session_id
            if image_path is not None:
                record.image_path = image_path
            record.updated_at = datetime.utcnow()
            return record

    def get(self, task_id: str) -> Optional[TaskRecord]:
        with self._lock:
            return self._tasks.get(task_id)

    def request_cancel(self, task_id: str) -> bool:
        """请求取消任务，返回是否成功设置取消标志。"""
        with self._lock:
            record = self._tasks.get(task_id)
            if not record:
                return False
            # 只有 PENDING 或 RUNNING 状态的任务可以被取消
            if record.status not in (JobStatusEnum.pending, JobStatusEnum.running):
                return False
            record.cancel_requested = True
            record.updated_at = datetime.utcnow()
            return True

    def is_cancel_requested(self, task_id: str) -> bool:
        """检查任务是否被请求取消。"""
        with self._lock:
            record = self._tasks.get(task_id)
            return record.cancel_requested if record else False

    def find_by_session_id(self, session_id: str) -> Optional[TaskRecord]:
        """通过 session_id 查找任务记录。"""
        with self._lock:
            for record in self._tasks.values():
                if record.session_id == session_id:
                    return record
            return None

