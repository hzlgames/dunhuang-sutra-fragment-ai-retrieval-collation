"""
桌面客户端配置模块
"""
import json
import os
from pathlib import Path
from typing import Optional

# 默认配置
DEFAULT_CONFIG = {
    "api_base_url": "http://127.0.0.1:8000",
    "poll_interval_single": 3,  # 单图任务轮询间隔（秒）
    "poll_interval_batch": 10,  # 批量任务轮询间隔（秒）
    "max_concurrent_uploads": 3,  # 最大并发上传数
    "auto_open_output": False,  # 完成后是否自动打开输出目录
}


class ClientConfig:
    """客户端配置管理类"""
    
    def __init__(self, config_path: Optional[Path] = None):
        self._config_path = config_path or self._default_config_path()
        self._config = DEFAULT_CONFIG.copy()
        self._load()
    
    @staticmethod
    def _default_config_path() -> Path:
        """获取默认配置文件路径"""
        # 优先使用项目目录下的配置文件
        project_config = Path(__file__).parent / "client_config.json"
        if project_config.exists():
            return project_config
        
        # 其次使用用户目录下的配置
        user_config_dir = Path.home() / ".dunhuang_analyzer"
        user_config_dir.mkdir(exist_ok=True)
        return user_config_dir / "client_config.json"
    
    def _load(self):
        """从文件加载配置"""
        if self._config_path.exists():
            try:
                with open(self._config_path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    self._config.update(loaded)
            except (json.JSONDecodeError, IOError) as e:
                print(f"⚠️ 加载配置文件失败: {e}，使用默认配置")
    
    def save(self):
        """保存配置到文件"""
        try:
            self._config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._config_path, "w", encoding="utf-8") as f:
                json.dump(self._config, f, indent=2, ensure_ascii=False)
        except IOError as e:
            print(f"⚠️ 保存配置文件失败: {e}")
    
    @property
    def api_base_url(self) -> str:
        return self._config["api_base_url"]
    
    @api_base_url.setter
    def api_base_url(self, value: str):
        self._config["api_base_url"] = value
    
    @property
    def poll_interval_single(self) -> int:
        return self._config["poll_interval_single"]
    
    @poll_interval_single.setter
    def poll_interval_single(self, value: int):
        self._config["poll_interval_single"] = max(1, value)
    
    @property
    def poll_interval_batch(self) -> int:
        return self._config["poll_interval_batch"]
    
    @poll_interval_batch.setter
    def poll_interval_batch(self, value: int):
        self._config["poll_interval_batch"] = max(1, value)
    
    @property
    def max_concurrent_uploads(self) -> int:
        return self._config["max_concurrent_uploads"]
    
    @max_concurrent_uploads.setter
    def max_concurrent_uploads(self, value: int):
        self._config["max_concurrent_uploads"] = max(1, min(10, value))
    
    @property
    def auto_open_output(self) -> bool:
        return self._config["auto_open_output"]
    
    @auto_open_output.setter
    def auto_open_output(self, value: bool):
        self._config["auto_open_output"] = value


# 全局配置实例
config = ClientConfig()

