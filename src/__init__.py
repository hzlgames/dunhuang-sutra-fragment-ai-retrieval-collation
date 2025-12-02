"""
使 src 成为可导入的 Python 包。

注意：项目入口仍推荐使用：

    python -m src.main --input input --output output

这样可以确保包内绝对导入（如 `from src.gallica_client import GallicaClient`）在
调试脚本（例如 `src/gallica_mcp.py`）中也能正常工作。
"""


