"""
桌面客户端数据模型
"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


class TaskStatus(str, Enum):
    """任务状态枚举"""
    # 客户端内部状态
    QUEUED = "QUEUED"  # 排队等待上传
    UPLOADING = "UPLOADING"  # 正在上传
    
    # 与后端同步的状态
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    
    # 批处理特有状态
    BATCH_PENDING = "BATCH_PENDING"
    BATCH_RUNNING = "BATCH_RUNNING"
    BATCH_MERGING = "BATCH_MERGING"


class TaskType(str, Enum):
    """任务类型"""
    SINGLE = "single"  # 单图任务
    BATCH = "batch"  # 批处理任务


@dataclass
class TaskRecord:
    """任务记录"""
    local_id: str  # 本地唯一标识
    task_type: TaskType
    image_paths: List[str]  # 本地图片路径列表
    status: TaskStatus = TaskStatus.QUEUED
    
    # 后端返回的 ID
    task_id: Optional[str] = None  # 单图任务 ID
    batch_id: Optional[str] = None  # 批处理任务 ID
    session_id: Optional[str] = None  # 会话 ID（用于断点续传）
    
    # 进度信息
    progress: float = 0.0  # 0.0 - 1.0
    current_round: int = 0
    total_jobs: int = 0
    completed_jobs: int = 0
    failed_jobs: int = 0
    
    # 结果信息
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    
    # 时间戳
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    
    # 重试相关
    retry_count: int = 0
    max_retries: int = 3
    
    def can_retry(self) -> bool:
        """是否可以重试"""
        return (
            self.status in (TaskStatus.FAILED, TaskStatus.CANCELLED)
            and self.retry_count < self.max_retries
        )
    
    def can_cancel(self) -> bool:
        """是否可以取消"""
        return self.status in (
            TaskStatus.QUEUED,
            TaskStatus.UPLOADING,
            TaskStatus.PENDING,
            TaskStatus.RUNNING,
            TaskStatus.BATCH_PENDING,
            TaskStatus.BATCH_RUNNING,
        )
    
    def is_active(self) -> bool:
        """是否是活跃任务（需要轮询）"""
        return self.status in (
            TaskStatus.PENDING,
            TaskStatus.RUNNING,
            TaskStatus.BATCH_PENDING,
            TaskStatus.BATCH_RUNNING,
            TaskStatus.BATCH_MERGING,
        )
    
    def is_terminal(self) -> bool:
        """是否是终态"""
        return self.status in (
            TaskStatus.SUCCEEDED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
        )
    
    def get_display_name(self) -> str:
        """获取显示名称"""
        if self.image_paths:
            first_path = Path(self.image_paths[0])
            if len(self.image_paths) == 1:
                return first_path.name
            else:
                return f"{first_path.name} 等 {len(self.image_paths)} 张"
        return f"任务 {self.local_id[:8]}"
    
    def get_status_text(self) -> str:
        """获取状态文本"""
        status_map = {
            TaskStatus.QUEUED: "排队中",
            TaskStatus.UPLOADING: "上传中",
            TaskStatus.PENDING: "等待处理",
            TaskStatus.RUNNING: "处理中",
            TaskStatus.SUCCEEDED: "已完成",
            TaskStatus.FAILED: "失败",
            TaskStatus.CANCELLED: "已取消",
            TaskStatus.BATCH_PENDING: "批处理等待",
            TaskStatus.BATCH_RUNNING: "批处理中",
            TaskStatus.BATCH_MERGING: "结果整合中",
        }
        text = status_map.get(self.status, self.status.value)
        
        # 添加进度信息
        if self.status == TaskStatus.RUNNING and self.current_round > 0:
            text += f" (第{self.current_round}轮)"
        elif self.status in (TaskStatus.BATCH_RUNNING, TaskStatus.BATCH_MERGING):
            if self.total_jobs > 0:
                text += f" ({self.completed_jobs}/{self.total_jobs})"
        
        return text


@dataclass
class BatchDetail:
    """批处理任务详情"""
    session_id: str
    alias: str
    done: bool
    error: Optional[str]
    last_round: int


@dataclass
class ServerMeta:
    """服务器元信息"""
    version: str
    output_dir: str
    supports_batch: bool

