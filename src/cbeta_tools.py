import requests
import urllib3
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter
from typing import List, Dict, Any, Optional
import json

# 禁用 SSL 不安全警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class CBETATools:
    def __init__(self):
        self.base_url = "https://cbdata.dila.edu.tw/stable"
        self.session = self._init_session()

    def _init_session(self):
        session = requests.Session()
        retries = Retry(total=3, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])
        session.mount('https://', HTTPAdapter(max_retries=retries))
        session.verify = False
        return session

    def _convert_sc2tc(self, text: str) -> str:
        """简繁转换辅助函数"""
        try:
            url = f"{self.base_url}/chinese_tools/sc2tc"
            response = self.session.get(url, params={"q": text}, timeout=5)
            if response.status_code == 200:
                content_type = response.headers.get("Content-Type", "")
                if "application/json" in content_type:
                    # JSON 格式响应
                    data = response.json()
                    return data.get('result', text)
                else:
                    # 纯文本格式响应
                    result = response.text.strip()
                    if result:
                        return result
        except Exception:
            pass
        return text

    def search_full_text(
        self,
        query: str,
        rows: int = 20,
        start: int = 0,
        around: int = 15,
        canon: str = None,
        category: str = None,
        dynasty: str = None
    ) -> Dict[str, Any]:
        """
        全文检索工具
        Args:
            query: 搜索关键词
            rows: 返回数量
            start: 起始偏移
            around: KWIC 上下文字数
            canon: 限制藏经 (如 'T')
            category: 限制部类
            dynasty: 限制朝代
        """
        query_tc = self._convert_sc2tc(query)
        params = {
            "q": query_tc,
            "rows": rows,
            "start": start,
            "around": around,
            "fields": "work,title,juan,term_hits,byline,time_dynasty,category,canon"
        }
        if canon: params["canon"] = canon
        if category: params["category"] = category
        if dynasty: params["dynasty"] = dynasty

        try:
            response = self.session.get(f"{self.base_url}/search", params=params, timeout=15)
            response.raise_for_status()
            data = response.json()
            return {
                "status": "success",
                "num_found": data.get("num_found", 0),
                "results": data.get("results", [])
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def search_advanced(self, query: str, facet: bool = True, around: int = 15, rows: int = 20) -> Dict[str, Any]:
        """
        高级检索工具 (All in One)
        Args:
            query: 支持高级语法的查询串
            facet: 是否返回统计信息
            around: KWIC 上下文字数
            rows: 返回数量
        """
        query_tc = self._convert_sc2tc(query)
        params = {
            "q": query_tc,
            "facet": 1 if facet else 0,
            "around": around,
            "rows": rows
        }
        
        try:
            response = self.session.get(f"{self.base_url}/search/all_in_one", params=params, timeout=20)
            response.raise_for_status()
            data = response.json()
            # all_in_one 的 results 是列表，num_found 在顶层
            return {
                "status": "success",
                "num_found": data.get("num_found", 0),
                "total_term_hits": data.get("total_term_hits", 0),
                "results": data.get("results", []),
                "facets": data.get("facet", {}) if facet else {}
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def search_similar(self, text: str, score_min: int = 16) -> Dict[str, Any]:
        """
        相似文本搜索工具
        Args:
            text: 文本片段
            score_min: 最低分数
        """
        text_tc = self._convert_sc2tc(text)
        # 注意：search/similar 返回的是 HTML 还是 JSON？
        # 根据之前的经验，search/similar 返回 HTML。
        # 但文档中提到 API 返回标准 JSON。
        # 让我们再次确认。之前的 cbeta_search.py 中发现它返回 HTML。
        # 如果是 HTML，我们需要解析。
        # 但为了工具调用的稳定性，我们应该尽量寻找 JSON 接口。
        # 之前的 cbeta_search.py 中我们改用了 search 接口来模拟 similar。
        # 这里我们先尝试调用 API，如果返回 HTML，则回退到 search 接口或解析 HTML。
        # 鉴于 AI Agent 需要结构化数据，我们这里先实现一个基于 search 的模拟 similar，
        # 或者如果必须用 similar 端点，则需要集成 BeautifulSoup。
        
        # 策略：先尝试请求，如果 Content-Type 是 json 则直接解析，否则用 soup。
        
        params = {"q": text_tc, "score_min": score_min}
        try:
            response = self.session.get(f"{self.base_url}/search/similar", params=params, timeout=20)
            
            if "application/json" in response.headers.get("Content-Type", ""):
                return response.json()
            else:
                # 解析 HTML (简单版)
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(response.text, 'html.parser')
                results = []
                # 尝试提取结果 (根据之前的经验)
                items = soup.find_all('div', class_='result_item') or soup.find_all('li')
                for item in items[:10]:
                    results.append({
                        "text": item.get_text(strip=True),
                        # 更多解析逻辑...
                    })
                return {
                    "status": "success", 
                    "note": "Parsed from HTML",
                    "results": results
                }
        except Exception as e:
             # 回退策略：使用 search 接口
            return self.search_full_text(text_tc, rows=5)

    # ========== 扩展工具 ==========

    def search_title(
        self,
        query: str,
        rows: int = 20
    ) -> Dict[str, Any]:
        """
        佛典标题搜索：仅搜索经名（佛典标题），适合快速查找特定经典。
        Args:
            query: 经名关键词（如"金刚经"、"阿含"）
            rows: 返回数量
        Returns:
            匹配的佛典列表，含经号、经名、作译者等
        """
        query_tc = self._convert_sc2tc(query)
        params = {"q": query_tc, "rows": rows}
        try:
            response = self.session.get(
                f"{self.base_url}/search/title",
                params=params,
                timeout=15
            )
            response.raise_for_status()
            data = response.json()
            return {
                "status": "success",
                "num_found": data.get("num_found", 0),
                "results": data.get("results", [])
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def search_kwic(
        self,
        work: str,
        juan: int,
        query: str,
        around: int = 15,
        include_notes: bool = True
    ) -> Dict[str, Any]:
        """
        单卷 KWIC 检索：针对特定佛典的特定卷进行检索，回传前后文。
        适用场景：已知经号和卷号，需精确定位关键词位置。
        Args:
            work: 佛典编号（如 T0001、X0087）
            juan: 卷号（如 1、2、3）
            query: 关键词，多词用逗号分隔
            around: 前后文字数
            include_notes: 是否包含夹注
        Returns:
            该卷中所有匹配位置及前后文
        """
        query_tc = self._convert_sc2tc(query)
        params = {
            "work": work,
            "juan": juan,
            "q": query_tc,
            "around": around,
            "note": 1 if include_notes else 0
        }
        try:
            response = self.session.get(
                f"{self.base_url}/search/kwic",
                params=params,
                timeout=15
            )
            response.raise_for_status()
            data = response.json()
            return {
                "status": "success",
                "work": work,
                "juan": juan,
                "num_found": data.get("num_found", 0),
                "results": data.get("results", [])
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def search_toc(
        self,
        query: str,
        rows: int = 20
    ) -> Dict[str, Any]:
        """
        目录搜索：搜索经名、部类目录或佛典内目次。
        适用场景：查找某部经的结构、或按部类浏览。
        Args:
            query: 搜索词（如"阿含"、"般若"）
            rows: 返回数量
        Returns:
            匹配结果，含类型(catalog/work/toc)
        """
        query_tc = self._convert_sc2tc(query)
        params = {"q": query_tc, "rows": rows}
        try:
            response = self.session.get(
                f"{self.base_url}/search/toc",
                params=params,
                timeout=15
            )
            response.raise_for_status()
            data = response.json()
            return {
                "status": "success",
                "num_found": data.get("num_found", 0),
                "results": data.get("results", [])
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def search_notes(
        self,
        query: str,
        facet: bool = False,
        rows: int = 20
    ) -> Dict[str, Any]:
        """
        注解检索：专门搜索校勘条目、注解或夹注。
        适用场景：查找某词在注解/校勘中的出现，或研究版本差异。
        支持高级语法：AND(空格)、OR(|)、NOT(!)、NEAR/n
        Args:
            query: 搜索词（支持扩展语法）
            facet: 是否返回分类统计
            rows: 返回数量
        Returns:
            注解匹配结果，含 note_place(foot/inline) 和 highlight
        """
        query_tc = self._convert_sc2tc(query)
        params = {
            "q": query_tc,
            "facet": 1 if facet else 0,
            "rows": rows
        }
        try:
            response = self.session.get(
                f"{self.base_url}/search/notes",
                params=params,
                timeout=15
            )
            response.raise_for_status()
            data = response.json()
            return {
                "status": "success",
                "num_found": data.get("num_found", 0),
                "results": data.get("results", []),
                "facets": data.get("facets", {}) if facet else {}
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def search_variants(
        self,
        query: str,
        scope: str = None
    ) -> Dict[str, Any]:
        """
        异体字查询：列出关键词的异体字变化。
        适用场景：OCR 结果可能有异体字，用此工具获取所有变体再搜索。
        Args:
            query: 原始词（如"著衣持鉢"）
            scope: 可选 "title" 仅列出佛典题名中的异体字
        Returns:
            异体字变化列表
        """
        query_tc = self._convert_sc2tc(query)
        params = {"q": query_tc}
        if scope:
            params["scope"] = scope
        try:
            response = self.session.get(
                f"{self.base_url}/search/variants",
                params=params,
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            return {
                "status": "success",
                "original": query_tc,
                "variants": data.get("results", data) if isinstance(data, dict) else data
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def get_facet_stats(
        self,
        query: str,
        facet_type: str = None
    ) -> Dict[str, Any]:
        """
        统计面向：获取关键词在不同维度下的统计数据。
        适用场景：了解某词在各藏经/部类/朝代/作者中的分布。
        Args:
            query: 搜索词
            facet_type: 维度类型，可选值：
                - None: 返回所有维度
                - "canon": 按藏经统计
                - "category": 按部类统计
                - "creator": 按作译者统计
                - "dynasty": 按朝代统计
                - "work": 按佛典统计
        Returns:
            各维度的统计数据
        """
        query_tc = self._convert_sc2tc(query)
        params = {"q": query_tc}
        endpoint = f"{self.base_url}/search/facet"
        if facet_type:
            endpoint = f"{endpoint}/{facet_type}"
        try:
            response = self.session.get(endpoint, params=params, timeout=15)
            response.raise_for_status()
            data = response.json()
            return {
                "status": "success",
                "query": query_tc,
                "facet_type": facet_type or "all",
                "stats": data
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}
