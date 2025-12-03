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
    session_id: Optional[str] = None  # 新增：关联的 session_id


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
            record.updated_at = datetime.utcnow()
            return record

    def get(self, task_id: str) -> Optional[TaskRecord]:
        with self._lock:
            return self._tasks.get(task_id)

