"""
后端 API 客户端封装
"""
import requests
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .config import config
from .models import ServerMeta, TaskStatus


class APIError(Exception):
    """API 调用异常"""
    def __init__(self, message: str, status_code: int = 0):
        super().__init__(message)
        self.status_code = status_code


class APIClient:
    """后端 API 客户端"""
    
    def __init__(self, base_url: Optional[str] = None):
        self.base_url = (base_url or config.api_base_url).rstrip("/")
        self.timeout = 60  # 请求超时（秒）
    
    def _url(self, path: str) -> str:
        """构造完整 URL"""
        return f"{self.base_url}{path}"
    
    def _handle_response(self, resp: requests.Response) -> Dict[str, Any]:
        """处理响应"""
        if resp.status_code >= 400:
            try:
                detail = resp.json().get("detail", resp.text)
            except Exception:
                detail = resp.text
            raise APIError(f"API 错误: {detail}", resp.status_code)
        return resp.json()
    
    # ------------------------------------------------------------------ #
    # 健康检查与元信息
    # ------------------------------------------------------------------ #
    
    def health_check(self) -> bool:
        """检查服务是否可用"""
        try:
            resp = requests.get(self._url("/api/v1/meta"), timeout=5)
            return resp.status_code == 200
        except Exception:
            return False
    
    def get_meta(self) -> ServerMeta:
        """获取服务器元信息"""
        resp = requests.get(self._url("/api/v1/meta"), timeout=self.timeout)
        data = self._handle_response(resp)
        return ServerMeta(
            version=data["version"],
            output_dir=data["output_dir"],
            supports_batch=data["supports_batch"],
        )
    
    # ------------------------------------------------------------------ #
    # 单图任务接口
    # ------------------------------------------------------------------ #
    
    def upload_single_image(self, image_path: Path) -> str:
        """
        上传单张图片创建任务。
        
        Returns:
            task_id: 任务 ID
        """
        with open(image_path, "rb") as f:
            files = {"file": (image_path.name, f, "image/png")}
            resp = requests.post(
                self._url("/api/v1/jobs/image"),
                files=files,
                timeout=self.timeout,
            )
        data = self._handle_response(resp)
        return data["task_id"]
    
    def get_job_status(self, task_id: str) -> Dict[str, Any]:
        """
        获取单图任务状态。
        
        Returns:
            包含 task_id, status, result, error 等字段的字典
        """
        resp = requests.get(
            self._url(f"/api/v1/jobs/{task_id}"),
            timeout=self.timeout,
        )
        return self._handle_response(resp)
    
    def get_job_process(self, task_id: str) -> Dict[str, Any]:
        """
        获取任务的 AI 处理过程。
        
        Returns:
            包含 session_id, rounds, total_rounds 的字典
        """
        resp = requests.get(
            self._url(f"/api/v1/jobs/{task_id}/process"),
            timeout=self.timeout,
        )
        return self._handle_response(resp)
    
    def cancel_job(self, task_id: str) -> Dict[str, Any]:
        """
        取消任务。
        
        Returns:
            包含 task_id, status, message 的字典
        """
        resp = requests.post(
            self._url(f"/api/v1/jobs/{task_id}/cancel"),
            timeout=self.timeout,
        )
        return self._handle_response(resp)
    
    def resume_job(self, session_id: str, image_path: Path) -> Tuple[str, str]:
        """
        断点续传任务。
        
        Args:
            session_id: 要恢复的会话 ID
            image_path: 图片路径
        
        Returns:
            (task_id, session_id) 元组
        """
        with open(image_path, "rb") as f:
            files = {"file": (image_path.name, f, "image/png")}
            resp = requests.post(
                self._url("/api/v1/jobs/resume"),
                params={"session_id": session_id},
                files=files,
                timeout=self.timeout,
            )
        data = self._handle_response(resp)
        return data["task_id"], data["session_id"]
    
    # ------------------------------------------------------------------ #
    # 批处理任务接口
    # ------------------------------------------------------------------ #
    
    def upload_batch(self, image_paths: List[Path]) -> str:
        """
        上传多张图片创建批处理任务。
        
        Returns:
            batch_id: 批处理 ID
        """
        files = []
        file_handles = []
        try:
            for path in image_paths:
                f = open(path, "rb")
                file_handles.append(f)
                files.append(("files", (path.name, f, "image/png")))
            
            resp = requests.post(
                self._url("/api/v1/batches"),
                files=files,
                timeout=self.timeout * 2,  # 批量上传需要更长时间
            )
        finally:
            for f in file_handles:
                f.close()
        
        data = self._handle_response(resp)
        return data["batch_id"]
    
    def get_batch_status(self, batch_id: str) -> Dict[str, Any]:
        """
        获取批处理任务状态。
        
        Returns:
            包含 batch_id, status, round, total_jobs, completed_jobs, failed_jobs, details 的字典
        """
        resp = requests.get(
            self._url(f"/api/v1/batches/{batch_id}"),
            timeout=self.timeout,
        )
        return self._handle_response(resp)
    
    def get_batch_results(self, batch_id: str, session_id: Optional[str] = None) -> Dict[str, Any]:
        """
        获取批处理任务结果。
        
        Returns:
            包含 batch_id, items 的字典
        """
        params = {}
        if session_id:
            params["session_id"] = session_id
        
        resp = requests.get(
            self._url(f"/api/v1/batches/{batch_id}/results"),
            params=params,
            timeout=self.timeout,
        )
        return self._handle_response(resp)
    
    # ------------------------------------------------------------------ #
    # 处理过程接口
    # ------------------------------------------------------------------ #
    
    def get_process_by_session(self, session_id: str) -> Dict[str, Any]:
        """
        通过 session_id 获取处理过程。
        
        Returns:
            包含 session_id, rounds, total_rounds 的字典
        """
        resp = requests.get(
            self._url(f"/api/v1/process/{session_id}"),
            timeout=self.timeout,
        )
        return self._handle_response(resp)


# 全局客户端实例
api_client = APIClient()

