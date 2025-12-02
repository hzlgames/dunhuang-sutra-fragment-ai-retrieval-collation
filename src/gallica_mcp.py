"""
Gallica MCP STDIO 客户端封装

通过 MCP (Model Context Protocol) 与 sweet-bnf Node.js 服务进程通信，
提供与旧 GallicaClient 等价的接口，并在 MCP 不可用时回退到本地实现。
"""
import os
import sys
import json
import subprocess
import threading
import queue
import time
import uuid
import atexit
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

from src.gallica_client import GallicaClient

from dotenv import load_dotenv
load_dotenv()

@dataclass
class MCPConfig:
    """MCP 客户端配置"""
    # sweet-bnf 项目路径（包含 package.json）
    server_path: str = os.getenv("GALLICA_MCP_PATH", "")
    # Node.js 可执行文件路径
    node_executable: str = os.getenv("NODE_EXECUTABLE", "node")
    # 启动超时（秒）
    startup_timeout: float = 30.0
    # 请求超时（秒）
    request_timeout: float = 60.0
    # 是否启用 MCP（设为 False 则直接使用 fallback）
    enabled: bool = True
    # 调试模式
    debug: bool = False


class MCPProtocolError(Exception):
    """MCP 协议错误"""
    pass


class GallicaMCPClient:
    """
    Gallica MCP STDIO 客户端
    
    通过子进程启动 sweet-bnf MCP Server，使用 JSON-RPC over STDIO 通信。
    """
    
    JSONRPC_VERSION = "2.0"
    
    def __init__(self, config: Optional[MCPConfig] = None, fallback: Optional[GallicaClient] = None):
        """
        初始化 MCP 客户端
        
        Args:
            config: MCP 配置
            fallback: 回退客户端（MCP 不可用时使用）
        """
        self.config = config or MCPConfig()
        self.fallback = fallback or GallicaClient()
        
        self._process: Optional[subprocess.Popen] = None
        self._reader_thread: Optional[threading.Thread] = None
        self._response_queues: Dict[str, queue.Queue] = {}
        self._lock = threading.Lock()
        self._running = False
        self._tools: Dict[str, Dict] = {}  # 缓存工具元数据
        self._initialized = False
        self._use_fallback = False  # 标记是否使用回退
        self._closed = False
        atexit.register(self.close)
        
        # 尝试启动 MCP 服务
        if self.config.enabled and self.config.server_path:
            try:
                self._start_server()
                self._initialize_session()
                self._initialized = True
                print(f"✅ Gallica MCP Server 已启动: {self.config.server_path}")
            except Exception as e:
                self._switch_to_fallback(f"启动失败: {e}")
        else:
            if not self.config.enabled:
                print("ℹ️ Gallica MCP 已禁用，使用本地回退")
            elif not self.config.server_path:
                print("ℹ️ GALLICA_MCP_PATH 未配置，使用本地回退")
            self._use_fallback = True
    
    def _start_server(self):
        """启动 MCP Server 子进程"""
        if not os.path.isdir(self.config.server_path):
            raise FileNotFoundError(f"MCP Server 路径不存在: {self.config.server_path}")
        
        # 构建启动命令：npm run start 或直接 node dist/index.js
        dist_index = os.path.join(self.config.server_path, "dist", "index.js")
        if os.path.isfile(dist_index):
            cmd = [self.config.node_executable, dist_index]
        else:
            # 尝试用 npm start
            cmd = ["npm", "run", "start"]
        
        if self.config.debug:
            print(f"🚀 启动 MCP Server: {' '.join(cmd)}")
        
        stderr_target = sys.stderr if self.config.debug else subprocess.DEVNULL
        self._process = subprocess.Popen(
            cmd,
            cwd=self.config.server_path,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=stderr_target,
            text=True,
            encoding='utf-8',
            errors='replace',
            bufsize=1,  # 行缓冲
        )
        
        self._running = True
        self._reader_thread = threading.Thread(target=self._read_responses, daemon=True)
        self._reader_thread.start()
    
    def _read_responses(self):
        """后台线程：读取 STDOUT 响应"""
        while self._running and self._process and self._process.stdout:
            try:
                line = self._process.stdout.readline()
                if not line:
                    break
                line = line.strip()
                if not line:
                    continue
                
                if self.config.debug:
                    print(f"📥 MCP 响应: {line[:200]}...")
                
                try:
                    msg = json.loads(line)
                    msg_id = msg.get("id")
                    if msg_id and msg_id in self._response_queues:
                        self._response_queues[msg_id].put(msg)
                except json.JSONDecodeError:
                    if self.config.debug:
                        print(f"⚠️ 无法解析 JSON: {line}")
            except Exception as e:
                if self._running:
                    print(f"❌ 读取响应出错: {e}")
                break
    
    def _send_request(self, method: str, params: Optional[Dict] = None) -> Dict[str, Any]:
        """
        发送 JSON-RPC 请求并等待响应
        
        Args:
            method: RPC 方法名
            params: 参数字典
        
        Returns:
            响应结果
        """
        if not self._process or not self._process.stdin:
            raise MCPProtocolError("MCP Server 未运行")
        
        request_id = str(uuid.uuid4())
        request = {
            "jsonrpc": self.JSONRPC_VERSION,
            "id": request_id,
            "method": method,
        }
        if params:
            request["params"] = params
        
        # 创建响应队列
        response_queue: queue.Queue = queue.Queue()
        with self._lock:
            self._response_queues[request_id] = response_queue
        
        try:
            # 发送请求
            request_line = json.dumps(request) + "\n"
            if self.config.debug:
                print(f"📤 MCP 请求: {request_line.strip()[:200]}...")
            
            self._process.stdin.write(request_line)
            self._process.stdin.flush()
            
            # 等待响应
            try:
                response = response_queue.get(timeout=self.config.request_timeout)
            except queue.Empty:
                raise MCPProtocolError(f"请求超时: {method}")
            
            # 检查错误
            if "error" in response:
                error = response["error"]
                raise MCPProtocolError(f"MCP 错误 [{error.get('code')}]: {error.get('message')}")
            
            return response.get("result", {})
        finally:
            with self._lock:
                self._response_queues.pop(request_id, None)
    
    def _initialize_session(self):
        """初始化 MCP 会话"""
        # 发送 initialize 请求
        result = self._send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {
                "name": "CBETA-Gallica-Agent",
                "version": "1.0.0"
            }
        })
        
        if self.config.debug:
            print(f"🔗 MCP 初始化完成: {result}")
        
        # 发送 initialized 通知
        self._send_notification("notifications/initialized", {})
        
        # 获取可用工具列表
        tools_result = self._send_request("tools/list", {})
        for tool in tools_result.get("tools", []):
            self._tools[tool["name"]] = tool
        
        if self.config.debug:
            print(f"🔧 可用工具: {list(self._tools.keys())}")
    
    def _send_notification(self, method: str, params: Optional[Dict] = None):
        """发送通知（无需响应）"""
        if not self._process or not self._process.stdin:
            return
        
        notification = {
            "jsonrpc": self.JSONRPC_VERSION,
            "method": method,
        }
        if params:
            notification["params"] = params
        
        notification_line = json.dumps(notification) + "\n"
        self._process.stdin.write(notification_line)
        self._process.stdin.flush()
    
    def _call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        调用 MCP 工具
        
        Args:
            tool_name: 工具名称
            arguments: 工具参数
        
        Returns:
            工具返回结果
        """
        if self._use_fallback:
            raise MCPProtocolError("MCP 不可用")
        
        result = self._send_request("tools/call", {
            "name": tool_name,
            "arguments": arguments
        })
        
        # 解析内容
        content = result.get("content", [])
        if content and isinstance(content, list):
            # 通常返回 [{"type": "text", "text": "..."}]
            for item in content:
                if item.get("type") == "text":
                    try:
                        return json.loads(item["text"])
                    except json.JSONDecodeError:
                        return {"text": item["text"]}
        return result
    
    # ========== 与 GallicaClient 等价的公开接口 ==========
    
    def search(
        self,
        query: str,
        max_records: int = 10,
        start_record: int = 1,
        doc_type: str = None,
        language: str = None
    ) -> Dict[str, Any]:
        """
        SRU 搜索 Gallica 馆藏（优先 MCP，回退本地）
        """
        if self._use_fallback:
            result = self.fallback.search(query, max_records, start_record, doc_type, language)
            result["_source"] = "fallback"
            return result
        
        try:
            # 使用 MCP 的 natural_language_search
            result = self._call_tool("natural_language_search", {
                "query": query,
                "max_results": max_records,
                "start_record": start_record
            })
            result["_source"] = "mcp"
            return self._normalize_search_result(result)
        except Exception as e:
            print(f"⚠️ MCP search 失败，回退本地: {e}")
            result = self.fallback.search(query, max_records, start_record, doc_type, language)
            result["_source"] = "fallback"
            return result
    
    def search_dunhuang(
        self,
        keyword: str = "",
        max_records: int = 10
    ) -> Dict[str, Any]:
        """
        专门搜索敦煌相关文献（优先 MCP，回退本地）
        """
        if self._use_fallback:
            result = self.fallback.search_dunhuang(keyword, max_records)
            result["_source"] = "fallback"
            return result
        
        try:
            # 构建敦煌相关查询
            base_query = "Dunhuang OR Pelliot OR 敦煌"
            if keyword:
                base_query = f"({base_query}) AND ({keyword})"
            
            result = self._call_tool("natural_language_search", {
                "query": base_query,
                "max_results": max_records
            })
            result["_source"] = "mcp"
            return self._normalize_search_result(result)
        except Exception as e:
            print(f"⚠️ MCP search_dunhuang 失败，回退本地: {e}")
            result = self.fallback.search_dunhuang(keyword, max_records)
            result["_source"] = "fallback"
            return result
    
    def search_by_title(self, title: str, exact_match: bool = False, max_results: int = 10) -> Dict[str, Any]:
        """按标题搜索（MCP 专有）"""
        if self._use_fallback:
            # 回退：用通用搜索
            result = self.fallback.search(title, max_results)
            result["_source"] = "fallback"
            return result
        
        try:
            result = self._call_tool("search_by_title", {
                "title": title,
                "exact_match": exact_match,
                "max_results": max_results
            })
            result["_source"] = "mcp"
            return self._normalize_search_result(result)
        except Exception as e:
            print(f"⚠️ MCP search_by_title 失败，回退本地: {e}")
            result = self.fallback.search(title, max_results)
            result["_source"] = "fallback"
            return result
    
    def search_by_author(self, author: str, exact_match: bool = False, max_results: int = 10) -> Dict[str, Any]:
        """按作者搜索（MCP 专有）"""
        if self._use_fallback:
            result = self.fallback.search(author, max_results)
            result["_source"] = "fallback"
            return result
        
        try:
            result = self._call_tool("search_by_author", {
                "author": author,
                "exact_match": exact_match,
                "max_results": max_results
            })
            result["_source"] = "mcp"
            return self._normalize_search_result(result)
        except Exception as e:
            print(f"⚠️ MCP search_by_author 失败，回退本地: {e}")
            result = self.fallback.search(author, max_results)
            result["_source"] = "fallback"
            return result
    
    def search_by_subject(self, subject: str, exact_match: bool = False, max_results: int = 10) -> Dict[str, Any]:
        """按主题搜索（MCP 专有）"""
        if self._use_fallback:
            result = self.fallback.search(subject, max_results)
            result["_source"] = "fallback"
            return result
        
        try:
            result = self._call_tool("search_by_subject", {
                "subject": subject,
                "exact_match": exact_match,
                "max_results": max_results
            })
            result["_source"] = "mcp"
            return self._normalize_search_result(result)
        except Exception as e:
            print(f"⚠️ MCP search_by_subject 失败，回退本地: {e}")
            result = self.fallback.search(subject, max_results)
            result["_source"] = "fallback"
            return result
    
    def search_advanced(self, query: str, max_results: int = 10) -> Dict[str, Any]:
        """高级 CQL 搜索（MCP 专有）"""
        if self._use_fallback:
            result = self.fallback.search(query, max_results)
            result["_source"] = "fallback"
            return result
        
        try:
            result = self._call_tool("advanced_search", {
                "query": query,
                "max_results": max_results
            })
            result["_source"] = "mcp"
            return self._normalize_search_result(result)
        except Exception as e:
            print(f"⚠️ MCP advanced_search 失败，回退本地: {e}")
            result = self.fallback.search(query, max_results)
            result["_source"] = "fallback"
            return result
    
    def get_manifest(self, ark: str) -> Dict[str, Any]:
        """
        获取 IIIF Manifest（优先 MCP，回退本地）
        """
        if self._use_fallback:
            result = self.fallback.get_manifest(ark)
            result["_source"] = "fallback"
            return result
        
        try:
            result = self._call_tool("get_item_details", {"ark": ark})
            result["_source"] = "mcp"
            return self._normalize_manifest_result(result)
        except Exception as e:
            print(f"⚠️ MCP get_item_details 失败，回退本地: {e}")
            result = self.fallback.get_manifest(ark)
            result["_source"] = "fallback"
            return result
    
    def get_item_pages(self, ark: str, page: int = None, page_size: int = None) -> Dict[str, Any]:
        """获取文档页面列表（MCP 专有）"""
        if self._use_fallback:
            # 回退：用 get_manifest 获取页面
            manifest = self.fallback.get_manifest(ark)
            manifest["_source"] = "fallback"
            return manifest
        
        try:
            params = {"ark": ark}
            if page is not None:
                params["page"] = page
            if page_size is not None:
                params["page_size"] = page_size
            
            result = self._call_tool("get_item_pages", params)
            result["_source"] = "mcp"
            return result
        except Exception as e:
            print(f"⚠️ MCP get_item_pages 失败，回退本地: {e}")
            manifest = self.fallback.get_manifest(ark)
            manifest["_source"] = "fallback"
            return manifest
    
    def get_page_info(self, ark: str, page: str = "f1") -> Dict[str, Any]:
        """
        获取单页信息（优先 MCP，回退本地）
        """
        if self._use_fallback:
            result = self.fallback.get_page_info(ark, page)
            result["_source"] = "fallback"
            return result
        
        try:
            # 将 page 字符串转为数字（f1 -> 1）
            page_num = int(page.replace("f", "")) if page.startswith("f") else int(page)
            result = self._call_tool("get_page_image", {
                "ark": ark,
                "page": page_num
            })
            result["_source"] = "mcp"
            return self._normalize_page_result(result, ark, page)
        except Exception as e:
            print(f"⚠️ MCP get_page_image 失败，回退本地: {e}")
            result = self.fallback.get_page_info(ark, page)
            result["_source"] = "fallback"
            return result
    
    def get_page_text(self, ark: str, page: int, format: str = "plain") -> Dict[str, Any]:
        """获取页面 OCR 文本（MCP 专有，无回退）"""
        if self._use_fallback:
            return {
                "status": "error",
                "message": "本地客户端不支持获取页面文本",
                "_source": "fallback"
            }
        
        try:
            result = self._call_tool("get_page_text", {
                "ark": ark,
                "page": page,
                "format": format
            })
            result["_source"] = "mcp"
            return result
        except Exception as e:
            return {
                "status": "error",
                "message": str(e),
                "_source": "mcp"
            }
    
    def build_image_url(
        self,
        ark: str,
        page: str = "f1",
        region: str = "full",
        size: str = "full",
        rotation: int = 0,
        quality: str = "native",
        format: str = "jpg"
    ) -> str:
        """构造 IIIF 图像 URL（直接使用本地实现）"""
        return self.fallback.build_image_url(ark, page, region, size, rotation, quality, format)
    
    def get_gallica_url(self, ark: str) -> str:
        """获取 Gallica 在线阅读 URL（直接使用本地实现）"""
        return self.fallback.get_gallica_url(ark)
    
    # ========== 结果标准化 ==========
    
    def _normalize_search_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """将 MCP 搜索结果标准化为与 GallicaClient 一致的格式"""
        if "status" not in result:
            result["status"] = "success"
        # 兼容多种字段命名：sweet-bnf 使用 metadata.total_records（字符串）
        if "total_records" not in result:
            if "totalResults" in result:
                result["total_records"] = result["totalResults"]
            elif isinstance(result.get("metadata"), dict) and "total_records" in result["metadata"]:
                try:
                    result["total_records"] = int(result["metadata"]["total_records"])
                except (ValueError, TypeError):
                    result["total_records"] = result["metadata"]["total_records"]
        if "records" not in result and "results" in result:
            result["records"] = result["results"]
        return result
    
    def _normalize_manifest_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """将 MCP manifest 结果标准化"""
        if "status" not in result:
            result["status"] = "success"
        return result
    
    def _normalize_page_result(self, result: Dict[str, Any], ark: str, page: str) -> Dict[str, Any]:
        """将 MCP 页面结果标准化"""
        if "status" not in result:
            result["status"] = "success"
        if "ark" not in result:
            result["ark"] = ark
        if "page" not in result:
            result["page"] = page
        return result
    
    # ========== 生命周期管理 ==========
    
    def _switch_to_fallback(self, reason: str):
        """切换到本地回退"""
        if not self._use_fallback:
            print(f"ℹ️ Gallica MCP 切换至本地回退（{reason}）")
        self._use_fallback = True
        self.close()
    
    def close(self):
        """关闭 MCP 服务"""
        if self._closed:
            return
        self._closed = True
        self._running = False
        if self._process:
            try:
                if self._process.stdin:
                    self._process.stdin.close()
                self._process.terminate()
                self._process.wait(timeout=5)
            except Exception:
                try:
                    self._process.kill()
                except Exception:
                    pass
            self._process = None
        if self._reader_thread:
            self._reader_thread.join(timeout=1)
            self._reader_thread = None
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
    
    def __del__(self):
        self.close()
    
    @property
    def is_mcp_available(self) -> bool:
        """MCP 是否可用"""
        return self._initialized and not self._use_fallback
    
    @property
    def available_tools(self) -> List[str]:
        """获取可用的 MCP 工具列表"""
        return list(self._tools.keys())


# ========== 测试代码 ==========
if __name__ == "__main__":
    print("=" * 60)
    print("测试 Gallica MCP 客户端")
    print("=" * 60)
    
    # 测试配置
    config = MCPConfig(
        server_path=os.getenv("GALLICA_MCP_PATH", ""),
        debug=True
    )
    
    with GallicaMCPClient(config) as client:
        print(f"\nMCP 可用: {client.is_mcp_available}")
        print(f"可用工具: {client.available_tools}")
        
        # 测试搜索
        print("\n【1. 搜索敦煌文献】")
        result = client.search_dunhuang(max_records=3)
        print(f"来源: {result.get('_source')}")
        print(f"状态: {result.get('status')}")
        print(f"总记录数: {result.get('total_records')}")
        
        for rec in result.get('records', [])[:3]:
            print(f"  - {rec.get('title', '未知')[:50]}...")
    
    print("\n" + "=" * 60)
    print("测试完成！")

