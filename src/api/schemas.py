from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class JobStatusEnum(str, Enum):
    pending = "PENDING"
    running = "RUNNING"
    succeeded = "SUCCEEDED"
    failed = "FAILED"
    batch_pending = "BATCH_PENDING"
    batch_running = "BATCH_RUNNING"
    batch_merging = "BATCH_MERGING"


class JobCreateResponse(BaseModel):
    task_id: str = Field(..., description="单张图片异步任务 ID")


class JobStatusResponse(BaseModel):
    task_id: str
    status: JobStatusEnum
    created_at: datetime
    updated_at: datetime
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class BatchCreateResponse(BaseModel):
    batch_id: str = Field(..., description="批处理任务 ID")


class BatchStatusResponse(BaseModel):
    batch_id: str
    status: JobStatusEnum
    round: int
    total_jobs: int
    completed_jobs: int
    failed_jobs: int
    details: List[Dict[str, Any]] = []


class BatchResultItem(BaseModel):
    session_id: str
    status: JobStatusEnum
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class BatchResultsResponse(BaseModel):
    batch_id: str
    items: List[BatchResultItem]


class RoundInfo(BaseModel):
    """单轮处理信息"""
    round_index: int
    timestamp: str
    summary: str = Field(..., description="AI 的思考摘要")
    tool_calls: List[Dict[str, Any]] = Field(default_factory=list, description="工具调用列表")
    notes: List[str] = Field(default_factory=list, description="额外注释")


class ProcessResponse(BaseModel):
    """处理过程响应"""
    session_id: str
    rounds: List[RoundInfo] = Field(..., description="每一轮的处理信息")
    total_rounds: int
