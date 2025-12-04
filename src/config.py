"""
项目全局配置模块。
通过环境变量控制输出目录等关键配置。
"""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def get_output_dir() -> Path:
    """获取输出目录路径，优先使用环境变量 OUTPUT_DIR，默认为 'output'。"""
    output_dir = Path(os.getenv("OUTPUT_DIR", "output"))
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def get_sessions_dir() -> Path:
    """获取会话记录目录路径，默认为 'sessions'。"""
    sessions_dir = Path(os.getenv("SESSIONS_DIR", "sessions"))
    sessions_dir.mkdir(parents=True, exist_ok=True)
    return sessions_dir


def supports_batch() -> bool:
    """判断是否支持 Batch API（需要配置 VERTEX_BATCH_BUCKET）。"""
    bucket = os.getenv("VERTEX_BATCH_BUCKET", "")
    return bool(bucket.strip())


# 版本号
VERSION = "1.0.0"

