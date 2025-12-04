"""
本地任务持久化存储
"""
import json
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from .models import TaskRecord, TaskStatus, TaskType


class TaskStore:
    """本地任务存储管理"""
    
    def __init__(self, storage_path: Optional[Path] = None):
        self._storage_path = storage_path or self._default_storage_path()
        self._lock = threading.Lock()
        self._tasks: Dict[str, TaskRecord] = {}
        self._load()
    
    @staticmethod
    def _default_storage_path() -> Path:
        """获取默认存储路径"""
        storage_dir = Path(__file__).parent / "data"
        storage_dir.mkdir(exist_ok=True)
        return storage_dir / "tasks.json"
    
    def _load(self):
        """从文件加载任务"""
        if not self._storage_path.exists():
            return
        
        try:
            with open(self._storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            for item in data.get("tasks", []):
                try:
                    record = TaskRecord(
                        local_id=item["local_id"],
                        task_type=TaskType(item["task_type"]),
                        image_paths=item["image_paths"],
                        status=TaskStatus(item["status"]),
                        task_id=item.get("task_id"),
                        batch_id=item.get("batch_id"),
                        session_id=item.get("session_id"),
                        progress=item.get("progress", 0.0),
                        current_round=item.get("current_round", 0),
                        total_jobs=item.get("total_jobs", 0),
                        completed_jobs=item.get("completed_jobs", 0),
                        failed_jobs=item.get("failed_jobs", 0),
                        result=item.get("result"),
                        error=item.get("error"),
                        created_at=datetime.fromisoformat(item["created_at"]),
                        updated_at=datetime.fromisoformat(item["updated_at"]),
                        retry_count=item.get("retry_count", 0),
                    )
                    self._tasks[record.local_id] = record
                except (KeyError, ValueError) as e:
                    print(f"⚠️ 加载任务记录失败: {e}")
        except (json.JSONDecodeError, IOError) as e:
            print(f"⚠️ 加载任务文件失败: {e}")
    
    def _save(self):
        """保存任务到文件"""
        try:
            self._storage_path.parent.mkdir(parents=True, exist_ok=True)
            
            tasks_data = []
            for record in self._tasks.values():
                tasks_data.append({
                    "local_id": record.local_id,
                    "task_type": record.task_type.value,
                    "image_paths": record.image_paths,
                    "status": record.status.value,
                    "task_id": record.task_id,
                    "batch_id": record.batch_id,
                    "session_id": record.session_id,
                    "progress": record.progress,
                    "current_round": record.current_round,
                    "total_jobs": record.total_jobs,
                    "completed_jobs": record.completed_jobs,
                    "failed_jobs": record.failed_jobs,
                    "result": record.result,
                    "error": record.error,
                    "created_at": record.created_at.isoformat(),
                    "updated_at": record.updated_at.isoformat(),
                    "retry_count": record.retry_count,
                })
            
            with open(self._storage_path, "w", encoding="utf-8") as f:
                json.dump({"tasks": tasks_data}, f, indent=2, ensure_ascii=False)
        except IOError as e:
            print(f"⚠️ 保存任务文件失败: {e}")
    
    def create_task(
        self,
        image_paths: List[str],
        task_type: TaskType = TaskType.SINGLE,
    ) -> TaskRecord:
        """创建新任务"""
        with self._lock:
            local_id = str(uuid.uuid4())
            record = TaskRecord(
                local_id=local_id,
                task_type=task_type,
                image_paths=image_paths,
                status=TaskStatus.QUEUED,
            )
            self._tasks[local_id] = record
            self._save()
            return record
    
    def get_task(self, local_id: str) -> Optional[TaskRecord]:
        """获取任务"""
        with self._lock:
            return self._tasks.get(local_id)
    
    def update_task(self, local_id: str, **kwargs) -> Optional[TaskRecord]:
        """更新任务"""
        with self._lock:
            record = self._tasks.get(local_id)
            if not record:
                return None
            
            for key, value in kwargs.items():
                if hasattr(record, key):
                    setattr(record, key, value)
            
            record.updated_at = datetime.now()
            self._save()
            return record
    
    def delete_task(self, local_id: str) -> bool:
        """删除任务"""
        with self._lock:
            if local_id in self._tasks:
                del self._tasks[local_id]
                self._save()
                return True
            return False
    
    def get_all_tasks(self) -> List[TaskRecord]:
        """获取所有任务"""
        with self._lock:
            return list(self._tasks.values())
    
    def get_active_tasks(self) -> List[TaskRecord]:
        """获取所有活跃任务"""
        with self._lock:
            return [t for t in self._tasks.values() if t.is_active()]
    
    def get_queued_tasks(self) -> List[TaskRecord]:
        """获取所有排队中的任务"""
        with self._lock:
            return [t for t in self._tasks.values() if t.status == TaskStatus.QUEUED]
    
    def get_retryable_tasks(self) -> List[TaskRecord]:
        """获取所有可重试的任务"""
        with self._lock:
            return [t for t in self._tasks.values() if t.can_retry()]
    
    def clear_completed(self) -> int:
        """清除已完成的任务，返回清除数量"""
        with self._lock:
            to_remove = [
                local_id for local_id, t in self._tasks.items()
                if t.status == TaskStatus.SUCCEEDED
            ]
            for local_id in to_remove:
                del self._tasks[local_id]
            if to_remove:
                self._save()
            return len(to_remove)
    
    def clear_all(self) -> int:
        """清除所有任务，返回清除数量"""
        with self._lock:
            count = len(self._tasks)
            self._tasks.clear()
            self._save()
            return count


# 全局任务存储实例
task_store = TaskStore()

