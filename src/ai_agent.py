import os
import json
import textwrap
import time
import uuid
from typing import List, Dict, Any, Optional, Generator, Callable
from datetime import datetime
from pathlib import Path
from pydantic import BaseModel, Field
from google import genai
from google.genai import types

from src.cbeta_tools import CBETATools
from src.gallica_client import GallicaClient
from src.gallica_mcp import GallicaMCPClient, MCPConfig
from src.schemas import FinalAnswer, ScriptureLocation, OCRResult

StreamHandler = Callable[[str, Dict[str, Any]], None]

class AgentConfig(BaseModel):
    """Agent 配置"""
    thinking_level: str = "high"  # "low" or "high"
    max_tool_rounds: int = 5  # 最多工具调用轮数（不含最终结构化输出轮）
    retry_interval: int = 10  # 重试间隔秒数
    normal_retries: int = 3  # 普通轮重试次数
    final_retries: int = 5  # 最终结构化输出轮重试次数
    timeout_seconds: int = 120
    model_name: str = "gemini-3-pro-preview"
    verbose: bool = True  # 是否开启可视化输出
    # Gallica MCP 配置
    gallica_mcp_enabled: bool = True  # 是否启用 Gallica MCP
    gallica_mcp_path: str = ""  # sweet-bnf 项目路径（留空则从环境变量读取）

class SessionManager:
    """会话管理器"""
    def __init__(self, storage_dir: str = "sessions"):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(exist_ok=True)

    def create_session(self) -> str:
        """创建新会话"""
        session_id = str(uuid.uuid4())
        self.save_session(session_id, [])
        return session_id

    def save_session(self, session_id: str, history: List[Dict]):
        """保存会话历史"""
        file_path = self.storage_dir / f"{session_id}.json"
        data = {
            "session_id": session_id,
            "updated_at": datetime.now().isoformat(),
            "history_count": len(history)  # 简化：只保存数量，不保存完整历史
        }
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load_session(self, session_id: str) -> List[Dict]:
        """加载会话历史"""
        # 简化版：不实际加载历史
        return []

    def _rounds_path(self, session_id: str) -> Path:
        return self.storage_dir / f"{session_id}.rounds.jsonl"

    def save_round(self, session_id: str, payload: Dict[str, Any]):
        """将单轮摘要写入 JSONL 文件"""
        file_path = self._rounds_path(session_id)
        try:
            with open(file_path, "a", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False)
                f.write("\n")
        except OSError as exc:
            print(f"⚠️ 保存轮次记录失败: {exc}")

    def load_rounds(self, session_id: str) -> List[Dict[str, Any]]:
        """读取指定会话的轮次记录"""
        file_path = self._rounds_path(session_id)
        rounds: List[Dict[str, Any]] = []
        if not file_path.exists():
            return rounds

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rounds.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        except OSError as exc:
            print(f"⚠️ 读取轮次记录失败: {exc}")
            return rounds

        return sorted(rounds, key=lambda record: record.get("round_index", 0))


def build_round_history_contents(round_records: List[Dict[str, Any]]) -> List[types.Content]:
    """将轮次记录转换为 Gemini 可用的历史消息"""
    contents: List[types.Content] = []
    for record in round_records:
        round_index = record.get("round_index", "?")
        segments: List[str] = []
        summary = (record.get("summary") or "").strip()
        segments.append(
            f"【历史第 {round_index} 轮摘要】{summary or '未提供摘要'}"
        )

        tool_calls = record.get("tool_calls") or []
        if tool_calls:
            tools_desc = []
            for call in tool_calls:
                name = call.get("name", "unknown")
                args = call.get("args", {})
                try:
                    args_str = json.dumps(args, ensure_ascii=False)
                except (TypeError, ValueError):
                    args_str = str(args)

                result_summary = call.get("result_summary", "")
                tools_desc.append(f"{name}({args_str}) → {result_summary}")
            segments.append("工具调用: " + " | ".join(tools_desc))

        notes = record.get("notes") or []
        for note in notes:
            segments.append(f"备注: {note}")

        contents.append(types.Content(role="user", parts=[types.Part(text="\n".join(segments))]))

    return contents

class CBETAAgent:
    def __init__(self, config: Optional[AgentConfig] = None):
        """
        初始化 CBETA 智能代理，加载 Gemini Client、工具映射与会话管理器。
        参数保持与 test_gemini3 一致（model=gemini-3-pro-preview、temperature=1.0、默认 high 思考等级）。
        """
        self.config = config or AgentConfig()
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY 未配置，无法初始化 CBETAAgent。")

        self.client = genai.Client(api_key=api_key)
        self.session_manager = SessionManager()
        self.cbeta_tools = CBETATools()
        
        # 初始化 Gallica 客户端（优先 MCP，回退本地）
        self.gallica_fallback = GallicaClient()
        mcp_config = MCPConfig(
            server_path=self.config.gallica_mcp_path or os.getenv("GALLICA_MCP_PATH", ""),
            enabled=self.config.gallica_mcp_enabled,
        )
        self.gallica_client = GallicaMCPClient(config=mcp_config, fallback=self.gallica_fallback)
        
        if self.config.verbose:
            if self.gallica_client.is_mcp_available:
                print(f"🔗 Gallica MCP 已连接，可用工具: {self.gallica_client.available_tools}")
            else:
                print("ℹ️ Gallica 使用本地回退模式")

        self.tools_map = {
            # ===== CBETA 工具 =====
            "search_full_text": self.cbeta_tools.search_full_text,
            "search_advanced": self.cbeta_tools.search_advanced,
            "search_similar": self.cbeta_tools.search_similar,
            "search_title": self.cbeta_tools.search_title,
            "search_kwic": self.cbeta_tools.search_kwic,
            "search_toc": self.cbeta_tools.search_toc,
            "search_notes": self.cbeta_tools.search_notes,
            "search_variants": self.cbeta_tools.search_variants,
            "get_facet_stats": self.cbeta_tools.get_facet_stats,
            # ===== Gallica 工具（通过 MCP 或回退） =====
            "search_gallica": self.gallica_client.search,
            "search_gallica_dunhuang": self.gallica_client.search_dunhuang,
            "search_gallica_by_title": self.gallica_client.search_by_title,
            "search_gallica_by_author": self.gallica_client.search_by_author,
            "search_gallica_by_subject": self.gallica_client.search_by_subject,
            "search_gallica_advanced": self.gallica_client.search_advanced,
            "get_gallica_manifest": self.gallica_client.get_manifest,
            "get_gallica_pages": self.gallica_client.get_item_pages,
            "get_gallica_page": self.gallica_client.get_page_info,
            "get_gallica_page_text": self.gallica_client.get_page_text,
        }
        self.tools_declarations = self._init_tools_declarations()

    def _call_with_retry(self, func, *args, max_retries: int = 3, retry_interval: int = 30, **kwargs):
        """
        通用重试包装，适用于 Gemini API 调用。
        Args:
            func: 要调用的函数
            max_retries: 最大重试次数（默认3次）
            retry_interval: 重试间隔秒数（默认30秒）
        """
        attempt = 0
        while attempt <= max_retries:
            try:
                return func(*args, **kwargs)
            except Exception as e:
                attempt += 1
                if attempt > max_retries:
                    print(f"❌ API 调用失败，已达最大重试次数 ({max_retries}): {e}")
                    raise
                print(f"❌ API 调用失败 (尝试 {attempt}/{max_retries}): {e}")
                print(f"⏳ 等待 {retry_interval}s 后重试...")
                time.sleep(retry_interval)
        raise RuntimeError("API 调用全部重试失败")

    def _emit_event(self, event_type: str, payload: Dict[str, Any], handler: Optional[StreamHandler]):
        """统一的流式事件分发。"""
        if handler:
            handler(event_type, payload)
            return
        if not self.config.verbose:
            return

        if event_type == "thought":
            print(f"\n🧠 思考片段: {payload.get('text', '').strip()}")
        elif event_type == "tool_call":
            print(f"\n🤖 准备调用工具 {payload.get('name')}: {payload.get('args')}")
        elif event_type == "tool_result":
            status = payload.get("status", "success")
            print(f"📥 工具 {payload.get('name')} 完成 ({status})")
            if "summary" in payload:
                print(f"   摘要: {payload['summary']}")
        elif event_type == "text":
            print(f"💬 输出片段: {payload.get('text', '').strip()}")
        elif event_type == "error":
            print(f"⚠️  {payload.get('message')}")

    def _collect_parts_from_chunk(
        self,
        chunk: types.GenerateContentResponse,
        stream_handler: Optional[StreamHandler],
    ) -> List[types.Part]:
        """分析单个流式 chunk，返回其新增 parts。"""
        collected: List[types.Part] = []
        if not chunk.candidates:
            return collected

        candidate = chunk.candidates[0]
        content = candidate.content
        if not content or not content.parts:
            return collected

        for part in content.parts:
            collected.append(part)
            if getattr(part, "thought", False):
                self._emit_event("thought", {"text": part.text or ""}, stream_handler)
            elif part.function_call:
                raw_args = part.function_call.args or {}
                if hasattr(raw_args, "items"):
                    args_view = {k: v for k, v in raw_args.items()}
                else:
                    args_view = raw_args
                self._emit_event(
                    "tool_call",
                    {"name": part.function_call.name, "args": args_view},
                    stream_handler,
                )
            elif part.text:
                self._emit_event("text", {"text": part.text}, stream_handler)
        return collected

    def _consume_stream(
        self,
        stream: Generator[types.GenerateContentResponse, None, None],
        stream_handler: Optional[StreamHandler],
    ) -> Optional[types.GenerateContentResponse]:
        """消费 generate_content_stream 迭代器，聚合 parts 并广播事件。"""
        aggregated_parts: List[types.Part] = []
        last_chunk: Optional[types.GenerateContentResponse] = None

        for chunk in stream:
            last_chunk = chunk
            aggregated_parts.extend(
                self._collect_parts_from_chunk(chunk, stream_handler)
            )

        if not last_chunk:
            return None

        response = last_chunk.model_copy(deep=True)
        if response.candidates and response.candidates[0].content:
            response.candidates[0].content.parts = aggregated_parts
        elif response.candidates:
            response.candidates[0].content = types.Content(
                role="model", parts=aggregated_parts
            )
        return response

    def _generate_with_stream(
        self,
        *,
        contents: List[types.Content],
        config: types.GenerateContentConfig,
        stream_handler: Optional[StreamHandler],
    ) -> Optional[types.GenerateContentResponse]:
        stream = self.client.models.generate_content_stream(
            model=self.config.model_name,
            contents=contents,
            config=config,
        )
        return self._consume_stream(stream, stream_handler)


    def _init_tools_declarations(self) -> List[Dict]:
        """定义 Gemini 工具声明"""
        return [
            {
                "function_declarations": [
                    # ===== 核心检索工具 =====
                    {
                        "name": "search_full_text",
                        "description": "【全文检索】在 CBETA 全库进行关键词搜索。返回匹配的经卷列表及上下文片段。适用场景：已知关键词，需要找出所有出处。",
                        "parameters": {
                            "type": "OBJECT",
                            "properties": {
                                "query": {"type": "STRING", "description": "搜索关键词（简繁皆可，系统自动转换）"},
                                "rows": {"type": "INTEGER", "description": "返回数量（默认20）"},
                                "canon": {"type": "STRING", "description": "限制藏经版本：T=大正藏, X=卍续藏, J=嘉兴藏, H=正史佛教资料, A=赵城金藏 等"},
                                "category": {"type": "STRING", "description": "限制部类（如：阿含部类、般若部类、华严部类）"},
                                "dynasty": {"type": "STRING", "description": "限制朝代（如：唐、宋、隋）"}
                            },
                            "required": ["query"]
                        }
                    },
                    {
                        "name": "search_advanced",
                        "description": "【高级检索】支持复杂布尔语法的整合检索，同时返回 KWIC 前后文和分类统计。语法：空格=AND, |=OR, !=NOT, NEAR/n=邻近。适用场景：需要精确组合多个条件。",
                        "parameters": {
                            "type": "OBJECT",
                            "properties": {
                                "query": {"type": "STRING", "description": "高级查询串。示例：'\"法鼓\" \"聖嚴\"'(AND), '\"波羅蜜\"|\"波羅密\"'(OR), '\"法鼓\" NEAR/7 \"迦葉\"'(邻近7字内)"},
                                "facet": {"type": "BOOLEAN", "description": "是否返回藏经/部类/朝代/作者统计（默认true）"},
                                "around": {"type": "INTEGER", "description": "KWIC 上下文字数（默认15）"}
                            },
                            "required": ["query"]
                        }
                    },
                    {
                        "name": "search_similar",
                        "description": "【相似文本搜索】基于 Smith-Waterman 算法查找相似段落。适用场景：输入 OCR 识别的长文本（6-50字），找出 CBETA 中相似的经文段落。对 OCR 错字有一定容错。",
                        "parameters": {
                            "type": "OBJECT",
                            "properties": {
                                "text": {"type": "STRING", "description": "文本片段（建议6-50字，不含标点）"},
                                "score_min": {"type": "INTEGER", "description": "最低匹配分数（默认16，越高越严格）"}
                            },
                            "required": ["text"]
                        }
                    },
                    # ===== 精确定位工具 =====
                    {
                        "name": "search_title",
                        "description": "【经名搜索】仅搜索佛典标题（经名），快速查找特定经典。适用场景：知道经名但不确定完整名称或经号。",
                        "parameters": {
                            "type": "OBJECT",
                            "properties": {
                                "query": {"type": "STRING", "description": "经名关键词（如：金刚经、阿含、华严）"},
                                "rows": {"type": "INTEGER", "description": "返回数量（默认20）"}
                            },
                            "required": ["query"]
                        }
                    },
                    {
                        "name": "search_kwic",
                        "description": "【单卷精确检索】针对特定佛典的特定卷进行 KWIC 检索，返回所有匹配位置及前后文。适用场景：已知经号和卷号，需要精确定位关键词在该卷中的位置。",
                        "parameters": {
                            "type": "OBJECT",
                            "properties": {
                                "work": {"type": "STRING", "description": "佛典编号（如：T0001, T0235, X0087）"},
                                "juan": {"type": "INTEGER", "description": "卷号（如：1, 2, 3）"},
                                "query": {"type": "STRING", "description": "关键词，多词用逗号分隔"},
                                "around": {"type": "INTEGER", "description": "前后文字数（默认15）"},
                                "include_notes": {"type": "BOOLEAN", "description": "是否包含夹注（默认true）"}
                            },
                            "required": ["work", "juan", "query"]
                        }
                    },
                    {
                        "name": "search_toc",
                        "description": "【目录搜索】搜索经名、部类目录或佛典内目次结构。适用场景：查找某部经的章节结构，或按部类浏览。返回类型：catalog(部类目录)、work(佛典标题)、toc(内部目次)。",
                        "parameters": {
                            "type": "OBJECT",
                            "properties": {
                                "query": {"type": "STRING", "description": "搜索词（如：阿含、般若、涅槃）"},
                                "rows": {"type": "INTEGER", "description": "返回数量（默认20）"}
                            },
                            "required": ["query"]
                        }
                    },
                    # ===== 辅助研究工具 =====
                    {
                        "name": "search_notes",
                        "description": "【注解检索】专门搜索校勘条目、注解或夹注。支持高级语法。适用场景：查找某词在校勘/注解中的出现，研究版本差异。",
                        "parameters": {
                            "type": "OBJECT",
                            "properties": {
                                "query": {"type": "STRING", "description": "搜索词（支持 AND/OR/NOT/NEAR 语法）"},
                                "facet": {"type": "BOOLEAN", "description": "是否返回分类统计（默认false）"},
                                "rows": {"type": "INTEGER", "description": "返回数量（默认20）"}
                            },
                            "required": ["query"]
                        }
                    },
                    {
                        "name": "search_variants",
                        "description": "【异体字查询】列出关键词的所有异体字变化。适用场景：OCR 结果可能有异体字（如：著/着、鉢/钵），先用此工具获取变体再搜索可提高召回率。",
                        "parameters": {
                            "type": "OBJECT",
                            "properties": {
                                "query": {"type": "STRING", "description": "原始词（如：著衣持鉢）"},
                                "scope": {"type": "STRING", "description": "可选 'title' 仅列出佛典题名中的异体字"}
                            },
                            "required": ["query"]
                        }
                    },
                    {
                        "name": "get_facet_stats",
                        "description": "【统计分析】获取关键词在不同维度下的分布统计。适用场景：了解某词在各藏经/部类/朝代/作者中的使用频率分布。",
                        "parameters": {
                            "type": "OBJECT",
                            "properties": {
                                "query": {"type": "STRING", "description": "搜索词"},
                                "facet_type": {"type": "STRING", "description": "维度类型：canon(藏经)、category(部类)、creator(作译者)、dynasty(朝代)、work(佛典)。留空返回所有维度。"}
                            },
                            "required": ["query"]
                        }
                    },
                    # ===== Gallica 工具（法国国家图书馆敦煌文献） =====
                    {
                        "name": "search_gallica",
                        "description": "【Gallica 搜索】在法国国家图书馆 (BnF) Gallica 馆藏中搜索文献。适用场景：CBETA 缺少的敦煌写本、Pelliot 藏品、西域出土文献等。可与 CBETA 结果交叉验证。",
                        "parameters": {
                            "type": "OBJECT",
                            "properties": {
                                "query": {"type": "STRING", "description": "搜索关键词（如：Dunhuang、敦煌、Pelliot、经名等）"},
                                "max_records": {"type": "INTEGER", "description": "最大返回数量（默认10）"},
                                "doc_type": {"type": "STRING", "description": "限制文档类型：manuscrit(手稿)、image(图像)"},
                                "language": {"type": "STRING", "description": "限制语言：chi(中文)、san(梵文)、tib(藏文)"}
                            },
                            "required": ["query"]
                        }
                    },
                    {
                        "name": "search_gallica_dunhuang",
                        "description": "【Gallica 敦煌专搜】专门搜索 Gallica 中的敦煌相关文献（自动包含 Dunhuang、Pelliot、敦煌等关键词）。适用场景：快速查找法国馆藏的敦煌写本，用于与 CBETA 版本比对。",
                        "parameters": {
                            "type": "OBJECT",
                            "properties": {
                                "keyword": {"type": "STRING", "description": "额外关键词（可选，如经名、人名）"},
                                "max_records": {"type": "INTEGER", "description": "最大返回数量（默认10）"}
                            },
                            "required": []
                        }
                    },
                    {
                        "name": "search_gallica_by_title",
                        "description": "【Gallica 题名搜索】基于 MCP 的 search_by_title，适合按题名精确定位法国馆藏写本。",
                        "parameters": {
                            "type": "OBJECT",
                            "properties": {
                                "title": {"type": "STRING", "description": "文献题名"},
                                "exact_match": {"type": "BOOLEAN", "description": "是否要求完全匹配（默认 false）"},
                                "max_results": {"type": "INTEGER", "description": "最大返回数量（默认10）"}
                            },
                            "required": ["title"]
                        }
                    },
                    {
                        "name": "search_gallica_by_author",
                        "description": "【Gallica 作者搜索】使用 MCP 的 search_by_author，查找特定作者或收藏者的写本。",
                        "parameters": {
                            "type": "OBJECT",
                            "properties": {
                                "author": {"type": "STRING", "description": "作者或藏者姓名"},
                                "exact_match": {"type": "BOOLEAN", "description": "是否完全匹配（默认 false）"},
                                "max_results": {"type": "INTEGER", "description": "最大返回数量（默认10）"}
                            },
                            "required": ["author"]
                        }
                    },
                    {
                        "name": "search_gallica_by_subject",
                        "description": "【Gallica 主题搜索】基于 MCP 的 search_by_subject，可用于按主题/关键词聚焦敦煌分类。",
                        "parameters": {
                            "type": "OBJECT",
                            "properties": {
                                "subject": {"type": "STRING", "description": "主题关键词"},
                                "exact_match": {"type": "BOOLEAN", "description": "是否完全匹配（默认 false）"},
                                "max_results": {"type": "INTEGER", "description": "最大返回数量（默认10）"}
                            },
                            "required": ["subject"]
                        }
                    },
                    {
                        "name": "search_gallica_advanced",
                        "description": "【Gallica 高级搜索】对应 MCP 的 advanced_search，支持 Gallica CQL 语法组合多个字段。",
                        "parameters": {
                            "type": "OBJECT",
                            "properties": {
                                "query": {"type": "STRING", "description": "CQL 查询字符串"},
                                "max_results": {"type": "INTEGER", "description": "最大返回数量（默认10）"}
                            },
                            "required": ["query"]
                        }
                    },
                    {
                        "name": "get_gallica_manifest",
                        "description": "【Gallica 文档结构】获取指定 Gallica 文档的 IIIF Manifest，包含页面列表、元数据、图像链接。适用场景：已知 ARK ID，需要了解文档有多少页、获取高清图像链接。",
                        "parameters": {
                            "type": "OBJECT",
                            "properties": {
                                "ark": {"type": "STRING", "description": "ARK 标识符（如 ark:/12148/btv1b8304226d 或短 ID btv1b8304226d）"}
                            },
                            "required": ["ark"]
                        }
                    },
                    {
                        "name": "get_gallica_pages",
                        "description": "【Gallica 页面枚举】调用 MCP get_item_pages，支持分页获取某份写本的页面列表。",
                        "parameters": {
                            "type": "OBJECT",
                            "properties": {
                                "ark": {"type": "STRING", "description": "ARK 标识符"},
                                "page": {"type": "INTEGER", "description": "指定页码（可选）"},
                                "page_size": {"type": "INTEGER", "description": "返回页数（可选）"}
                            },
                            "required": ["ark"]
                        }
                    },
                    {
                        "name": "get_gallica_page",
                        "description": "【Gallica 单页信息】获取 Gallica 文档某一页的详细信息，包括分辨率、图像 URL、缩略图。适用场景：需要查看或比对特定页面的高清图像。",
                        "parameters": {
                            "type": "OBJECT",
                            "properties": {
                                "ark": {"type": "STRING", "description": "ARK 标识符"},
                                "page": {"type": "STRING", "description": "页码（如 f1、f2，默认 f1）"}
                            },
                            "required": ["ark"]
                        }
                    },
                    {
                        "name": "get_gallica_page_text",
                        "description": "【Gallica 页面文本】调用 MCP get_page_text，直接获取 ALTO/Plain OCR 内容，快速比对写本文字。",
                        "parameters": {
                            "type": "OBJECT",
                            "properties": {
                                "ark": {"type": "STRING", "description": "ARK 标识符"},
                                "page": {"type": "INTEGER", "description": "页码数字（如 1 代表 f1）"},
                                "format": {"type": "STRING", "description": "文本格式 plain/alto/tei（默认 plain）"}
                            },
                            "required": ["ark", "page"]
                        }
                    }
                ]
            }
        ]

    def _build_prompt(self, ocr_text: str = None, image_path: str = None) -> str:
        if ocr_text:
            base_prompt = f"""你是一位佛教文献考证专家。现在有一段古籍文字：

{ocr_text}

"""
        else:
            base_prompt = """你是一位佛教文献考证专家。请分析这张图片中的古籍文字，找出其在 CBETA 中的出处。

"""

        return base_prompt + """## 核心目标
**优先考证出处；OCR 仅需提炼可辨认片段，并清晰标注不确定字符。**

## 工作流

### 1. 快速 OCR 摘要
- 逐列或逐句记录可读文字（示例："列1：淨土中… "）
- 用 `[?]` 或 `[unclear]` 标记模糊字，不要强猜
- 提炼关键字/短语，便于后续搜索

### 2. 并行搜索策略（可同时调用多个工具）
**CBETA 工具（主线程）：**
- `search_similar`：用于 6-50 字长片段（含不确定位也可）
- `search_full_text`：用于高置信度关键词组合
- `search_title` / `search_toc`：探索可能经名或章节
- `search_variants`：获取异体字以扩大发现

**Gallica 工具（敦煌分身）—— 当 CBETA 结果不足或需跨版本比对时：**
- `search_gallica_dunhuang`：快速查找法国国家图书馆的敦煌写本
- `search_gallica`：按关键词搜索 Pelliot 藏品、西域出土文献
- `get_gallica_manifest`：获取文档结构与高清图像链接
- `get_gallica_page`：获取单页图像 URL，用于多模态比对

**子任务分工示例：**
- 主线程：继续 CBETA 深挖，用 `search_kwic` 精确定位
- Gallica 分身：同时搜索敦煌写本，返回候选 ARK 与图像链接
- 图像比对分身（可选）：获取 Gallica 页面缩略图，与原图对照

### 3. 精确定位与交叉验证
- 对高置信度候选，使用 `search_kwic` 等获取上下文
- 汇总证据：匹配字句、卷次、作译者、朝代
- **CBETA vs Gallica 对照**：在 `candidate_insights` 中记录两者差异（可选）
- 指出仍需人工确认的差异或疑点

### 4. 结构化输出（便于人工校对）
最终 JSON 中请确保：
- `ocr_result.recognized_text`：合并后的全文；`uncertain_chars`：列出所有标记
- `ocr_notes`：列表，逐列/逐句描述 OCR 摘要（含不确定说明）
- `scripture_locations`：至多 5 条候选，含匹配片段、置信度、证据：
  - 对 **CBETA** 候选：可设置 `source="CBETA"`，`work_id`/`canon`/`juan` 等字段准确完整，`external_url` 可留空（系统会自动生成 CBETA 在线链接）。
  - 对 **Gallica** 候选：允许将写本视作“藏卷”加入 `scripture_locations`，并设置：
    - `source="Gallica"`
    - 若已知 ARK 与页码，尽量填入 `external_url` 为可直接打开的 Gallica 在线阅读链接（例如 `https://gallica.bnf.fr/ark:/12148/btv1b8304226d/f3.item`）
- `key_facts`：片段关键信息列表，每项一句，直接基于图像与正文可见内容（**不**依赖外部文献），例如：
  - 物质形态：册子本/单叶/对开叶，页数或叶数，装订情况，残损位置（首/尾/左右上下）。
  - 题记与尾题：首题、尾题、署名、题记中的时间与人物。
  - 版式与标记：有无科分标题、行数栏数、朱笔圈点/删除、杂写、插图等。
- `candidate_insights`：逐条概述候选为何值得关注，**包括 Gallica 证据**，以及需人工核对的点
- `verification_points`：列出人工校对要点（疑难字、需查卷、**Gallica ARK/页码**、建议的 KWIC 位置等）
- `next_actions`：给实地研究者的后续建议（如"去查 T1753 卷2 KWIC 0258a25"、**"查阅 Gallica ark:/12148/xxx f3 页"**）
- `tools_used`、`search_iterations`、`session_id`：保持完整，可用于追踪

## 置信度评分建议
- **0.8-1.0**：多处关键字连续匹配，卷次/作译者一致，**Gallica 有对应写本佐证**
- **0.6-0.8**：主要字句吻合，少量 OCR 或版本出入
- **0.4-0.6**：仅部分关键词匹配
- **0.0-0.4**：证据不足，仅用作线索

## 注意事项
- 任何模糊字必须标注 `[?]`，并在 `ocr_notes` 中说明
- 每轮思考时给出"为何调用某工具"与"得到的人工可读结论"
- **当调用 Gallica 工具时，说明与 CBETA 的对照意图**
- 若 Gallica 返回图像链接，在 `next_actions` 中附上供人工查看
- 结果要像"人工校对笔记"：短句、要点、可直接引用

请开始分析并调用工具。"""

    def _execute_functions(
        self,
        response,
        stream_handler: Optional[StreamHandler],
    ) -> Generator[Dict, None, None]:
        """执行工具调用并可视化反馈"""
        if not response.candidates or not response.candidates[0].content.parts:
            return

        for part in response.candidates[0].content.parts:
            if part.function_call:
                fn = part.function_call
                
                # --- 可视化反馈 ---
                if self.config.verbose:
                    print(f"\n🤖 AI 决定调用工具: {fn.name}")
                    print(f"   参数: {fn.args}")
                
                # 执行实际函数
                if fn.name in self.tools_map:
                    try:
                        args = {k: v for k, v in (fn.args or {}).items()}
                        result = self.tools_map[fn.name](**args)

                        if self.config.verbose:
                            print(f"   ✅ 工具执行完成")
                            res_str = str(result)
                            print(f"   结果摘要: {res_str[:100]}..." if len(res_str) > 100 else f"   结果: {res_str}")

                        summary = self._shorten_text(str(result), width=120)
                        record = {
                            "name": fn.name,
                            "args": self._serialize_args(args),
                            "result_summary": summary,
                            "status": "success",
                        }

                        self._emit_event(
                            "tool_result",
                            {"name": fn.name, "status": "success", "summary": summary},
                            stream_handler,
                        )

                        yield {
                            "function_response": {
                                "name": fn.name,
                                "response": {"result": result}
                            },
                            "tool_record": record,
                        }
                    except Exception as e:
                        print(f"   ❌ 工具执行失败: {e}")
                        summary = self._shorten_text(str(e), width=120)
                        record = {
                            "name": fn.name,
                            "args": self._serialize_args({k: v for k, v in (fn.args or {}).items()}),
                            "result_summary": summary,
                            "status": "error",
                        }
                        self._emit_event(
                            "tool_result",
                            {
                                "name": fn.name,
                                "status": "error",
                                "summary": summary,
                            },
                            stream_handler,
                        )
                        yield {
                            "function_response": {
                                "name": fn.name,
                                "response": {"error": str(e)}
                            },
                            "tool_record": record,
                        }
                else:
                    print(f"   ⚠️ 未知工具: {fn.name}")
                    self._emit_event(
                        "error",
                        {"message": f"未知工具: {fn.name}"},
                        stream_handler,
                    )

    def _serialize_args(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """将工具参数转换为 JSON 友好的形式"""
        def convert(value: Any) -> Any:
            if isinstance(value, (str, int, float, bool)) or value is None:
                return value
            if isinstance(value, dict):
                return {k: convert(v) for k, v in value.items()}
            if isinstance(value, (list, tuple)):
                return [convert(v) for v in value]
            return str(value)

        return {k: convert(v) for k, v in args.items()}

    def _shorten_text(self, text: str, width: int) -> str:
        cleaned = " ".join(str(text).split())
        if not cleaned:
            return ""
        return textwrap.shorten(cleaned, width=width, placeholder="...")

    def _extract_round_text_summary(self, parts: List[types.Part]) -> str:
        texts = []
        for part in parts:
            if part.text and not part.function_call:
                cleaned = " ".join(part.text.split())
                if cleaned:
                    texts.append(cleaned)
        if not texts:
            return ""
        joined = " ".join(texts)
        return self._shorten_text(joined, width=600)

    def _persist_round_summary(
        self,
        session_id: str,
        round_index: int,
        summary: str,
        tool_calls: List[Dict[str, Any]],
        notes: List[str],
    ):
        payload = {
            "round_index": round_index,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "summary": summary,
            "tool_calls": tool_calls,
            "notes": notes,
        }
        self.session_manager.save_round(session_id, payload)

    def _build_history_from_rounds(self, session_id: str) -> List[types.Content]:
        rounds = self.session_manager.load_rounds(session_id)
        if not rounds:
            return []
        return build_round_history_contents(rounds)

    def _force_structured_output(
        self,
        history: List[types.Content],
        session_id: str,
    ) -> Optional[FinalAnswer]:
        """
        强制生成结构化输出（最终轮），使用更多重试次数。
        """
        if self.config.verbose:
            print("\n🔄 【最终轮】强制生成结构化答案...")
        
        final_prompt = """请根据上述所有分析，输出最终的结构化 JSON 答案。

即使信息不完整，也请尽量填写：
- ocr_result.recognized_text: 识别出的文字（不确定的用[?]标注）
- scripture_locations: 可能的经文出处列表（按置信度排序）
- reasoning: 你的推理过程摘要

请严格按照 JSON Schema 输出。"""
        
        history.append(types.Content(role="user", parts=[types.Part(text=final_prompt)]))
        
        # 使用官方推荐的 structured output 配置：
        # - response_mime_type 固定为 application/json
        # - response_schema 传入 Pydantic 生成的 JSON Schema
        final_config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=FinalAnswer.model_json_schema(),
        )
        
        try:
            final_resp = self._call_with_retry(
                self.client.models.generate_content,
                model=self.config.model_name,
                contents=history,
                config=final_config,
                max_retries=self.config.final_retries,
                retry_interval=self.config.retry_interval,
            )
            
            if final_resp.text:
                result = FinalAnswer.model_validate_json(final_resp.text)
                # 填充 session_id
                result.session_id = session_id
                return result
        except Exception as e:
            print(f"❌ 最终结构化输出失败: {e}")
        
        return None

    def analyze_and_locate(
        self,
        ocr_text: str = None,
        image_path: str = None,
        stream_handler: Optional[StreamHandler] = None,
        resume_session_id: Optional[str] = None,
        include_final_output: bool = True,
    ) -> FinalAnswer:
        """
        主流程：分析并定位经文出处。
        
        流程说明：
        - 最多进行 max_tool_rounds 轮工具调用（默认5轮）
        - AI 可随时选择不调用工具，提前结束
        - 可选择跳过最终结构化输出，仅依靠轮次存档
        - 普通轮重试 normal_retries 次，最终轮重试 final_retries 次
        """
        history: List[types.Content] = []
        if resume_session_id:
            session_id = resume_session_id
            history.extend(self._build_history_from_rounds(session_id))
            if self.config.verbose:
                print(f"🔄 继续会话: {session_id}")
        else:
            session_id = self.session_manager.create_session()
            if self.config.verbose:
                print(f"🔵 开始新会话: {session_id}")
                print(f"   最多工具调用轮数: {self.config.max_tool_rounds}")
        prompt = self._build_prompt(ocr_text, image_path)
        
        # 如果有图片，加载图片
        if image_path:
            try:
                from PIL import Image
                img = Image.open(image_path)
                if self.config.verbose:
                    print(f"🖼️ 已加载图片: {image_path}")
                mime_type = Image.MIME.get(img.format, "image/png")
                with open(image_path, "rb") as f:
                    image_bytes = f.read()
                image_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
                contents = [prompt, image_part]
            except Exception as e:
                print(f"❌ 加载图片失败: {e}")
                contents = [prompt]
        else:
            contents = [prompt]
        
        # 初始对话历史
        parts = []
        for content in contents:
            if isinstance(content, str):
                parts.append(types.Part(text=content))
            elif isinstance(content, types.Part):
                parts.append(content)
            else:
                raise TypeError("Unsupported content type for Gemini request.")

        history.append(types.Content(role="user", parts=parts))
        
        tool_round = 0  # 工具调用轮数计数
        successful_rounds = 0
        
        # 工具调用阶段（最多 max_tool_rounds 轮）
        while tool_round < self.config.max_tool_rounds:
            tool_round += 1
            if self.config.verbose:
                print(f"\n🔄 第 {tool_round}/{self.config.max_tool_rounds} 轮思考...")
            
            generate_config = types.GenerateContentConfig(
                temperature=1.0,
                max_output_tokens=8192,
                thinking_config=types.ThinkingConfig(
                    thinking_level=self.config.thinking_level,
                    include_thoughts=True
                ),
                tools=self.tools_declarations,
                tool_config=types.ToolConfig(
                    function_calling_config=types.FunctionCallingConfig(
                        mode="AUTO"
                    )
                ),
            )
            
            try:
                response = self._call_with_retry(
                    self._generate_with_stream,
                    contents=history,
                    config=generate_config,
                    stream_handler=stream_handler,
                    max_retries=self.config.normal_retries,
                    retry_interval=self.config.retry_interval,
                )
            except Exception as e:
                print(f"❌ 第 {tool_round} 轮 API 调用失败: {e}")
                break  # 跳出循环，进入最终结构化输出

            # 处理响应
            if not response or not response.candidates:
                print("⚠️ 无响应候选")
                break
                
            candidate = response.candidates[0]
            content = candidate.content
            round_summary = self._extract_round_text_summary(content.parts)
            tool_records: List[Dict[str, Any]] = []
            json_result: Optional[FinalAnswer] = None
            should_break = False
            
            successful_rounds += 1

            # 将模型响应加入历史
            history.append(content)
            
            # 检查工具调用
            has_tool_call = any(part.function_call for part in content.parts)
            
            if has_tool_call:
                # 执行工具
                tool_outputs = list(self._execute_functions(response, stream_handler))
                
                parts = []
                for output in tool_outputs:
                    parts.append(types.Part.from_function_response(
                        name=output["function_response"]["name"],
                        response=output["function_response"]["response"]
                    ))
                    if "tool_record" in output:
                        tool_records.append(output["tool_record"])
                
                history.append(types.Content(role="user", parts=parts))
            else:
                # AI 选择不调用工具，尝试从回复中提取 JSON
                text_response = "".join([p.text for p in content.parts if p.text])
                
                if self.config.verbose:
                    print(f"\n📝 AI 回复（第 {tool_round} 轮无工具调用）")
                
                if "{" in text_response and "}" in text_response:
                    try:
                        start = text_response.find("{")
                        end = text_response.rfind("}") + 1
                        json_str = text_response[start:end]
                        result = FinalAnswer.model_validate_json(json_str)
                        result.session_id = session_id
                        json_result = result
                    except Exception as e:
                        if self.config.verbose:
                            print(f"   JSON 解析失败: {e}，进入最终结构化输出轮...")
                
                if not json_result:
                    should_break = True

            notes: List[str] = []
            if not round_summary:
                notes.append("本轮未产生文本摘要")
            if not has_tool_call:
                notes.append("本轮未调用工具")
            if json_result:
                notes.append("提前生成结构化结果，结束本轮")

            self._persist_round_summary(
                session_id,
                round_index=tool_round,
                summary=round_summary,
                tool_calls=tool_records,
                notes=notes,
            )

            if json_result:
                self.session_manager.save_session(session_id, history)
                return json_result
            if should_break:
                break
        
        # ===== 最终结构化输出轮（不计入工具调用轮数） =====
        if self.config.verbose:
            print(f"\n📊 工具调用阶段结束（共 {tool_round} 轮）")
        
        if successful_rounds == 0:
            if self.config.verbose:
                print("⚠️ 所有工具调用轮均未成功，跳过最终结构化输出。")
            self.session_manager.save_session(session_id, history)
            return None

        if not include_final_output:
            if self.config.verbose:
                print("⚠️ 已配置跳过最终结构化输出（仅保留轮次存档）。")
            self.session_manager.save_session(session_id, history)
            return None

        if self.config.verbose:
            print("📊 进入最终结构化输出（结构化 JSON）...")

        result = self._force_structured_output(history, session_id)
        
        # 保存会话
        self.session_manager.save_session(session_id, history)
        
        return result

    def resume_with_session(
        self,
        session_id: str,
        ocr_text: str = None,
        image_path: str = None,
        stream_handler: Optional[StreamHandler] = None,
        include_final_output: bool = True,
    ) -> FinalAnswer:
        """
        从已有会话的轮次存档重建上下文，继续或重新发起思考。
        """
        return self.analyze_and_locate(
            ocr_text=ocr_text,
            image_path=image_path,
            stream_handler=stream_handler,
            resume_session_id=session_id,
            include_final_output=include_final_output,
        )
