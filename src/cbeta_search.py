import os
import time
from typing import List, Tuple, Dict, Any

from src.cbeta_tools import CBETATools


class CBETASearcher:
    """面向 CLI/脚本的轻量封装，内部统一复用 CBETATools。"""

    def __init__(self):
        self.tools = CBETATools()

    def _build_snippet(self, item: Dict[str, Any]) -> str:
        snippet = item.get('snippet')
        if not snippet:
            hits = item.get('term_hits', [])
            if isinstance(hits, list):
                snippet = " ... ".join(hits)
            else:
                snippet = str(hits)
        snippet = (snippet or "").replace('\n', '')
        return snippet

    def search(self, query, rows=20, start=0, around=15) -> Tuple[List[Dict[str, Any]], int]:
        """
        增强版搜索功能 (标准全文检索)
        """
        print(f"正在搜索 CBETA: {query} (Start={start}, Rows={rows})...")
        response = self.tools.search_full_text(
            query,
            rows=rows,
            start=start,
            around=around,
        )
        if response.get("status") != "success":
            print(f"API 请求失败: {response.get('message')}")
            return [], 0

        num_found = response.get("num_found", 0)
        raw_results = response.get("results", []) or []
        print(f"搜索成功! 共找到 {num_found} 条结果 (本次展示 {len(raw_results)} 条)")

        cleaned_results = []
        for item in raw_results:
            cleaned_results.append({
                'id': item.get('work', '未知'),
                'title': item.get('title', '无标题'),
                'juan': item.get('juan', ''),
                'author': item.get('byline', '未知作者'),
                'dynasty': item.get('time_dynasty', '未知朝代'),
                'category': item.get('category', ''),
                'snippet': self._build_snippet(item),
                'source': 'standard'
            })
        return cleaned_results, num_found

    def search_similar(self, query: str) -> List[Dict[str, Any]]:
        """
        相似文本搜索 (适用于 OCR 结果)
        """
        print(f"正在进行相似文本搜索: {query[:20]}...")
        response = self.tools.search_similar(query)
        normalized = []

        if isinstance(response, dict):
            raw_results = response.get("results", []) or []
            for item in raw_results:
                if isinstance(item, dict):
                    work_id = item.get('work') or item.get('id') or 'unknown'
                    title = item.get('title') or item.get('text') or f"未知來源 {work_id}"
                    snippet = self._build_snippet(item)
                    normalized.append({
                        'title': f"{title} (卷{item.get('juan', '')})".strip(),
                        'snippet': snippet,
                        'link': f"https://cbetaonline.dila.edu.tw/zh/{work_id}" if work_id != 'unknown' else "",
                        'source': 'similar'
                    })
                else:
                    normalized.append({
                        'title': '未知來源',
                        'snippet': str(item),
                        'link': '',
                        'source': 'similar'
                    })
        else:
            print("⚠️ 相似搜索返回格式异常，回退为空列表")

        print(f"相似搜索完成，找到 {len(normalized)} 个潜在匹配")
        return normalized

    def save_results_to_file(self, results, filename="cbeta_results.txt"):
        """保存搜索结果到文件"""
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(f"CBETA 搜索结果报告\n")
                f.write(f"生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("=" * 50 + "\n\n")
                
                for i, res in enumerate(results, 1):
                    f.write(f"结果 #{i}\n")
                    if res.get('source') == 'standard':
                        f.write(f"标题: {res['title']} (卷{res['juan']})\n")
                        f.write(f"作者: {res['author']}\n")
                        f.write(f"片段: {res['snippet']}\n")
                    else:
                        f.write(f"标题: {res['title']}\n")
                        f.write(f"片段: {res['snippet']}\n")
                        f.write(f"链接: {res['link']}\n")
                    f.write("-" * 30 + "\n")
            print(f"结果已保存至: {os.path.abspath(filename)}")
            return os.path.abspath(filename)
        except Exception as e:
            print(f"保存文件失败: {e}")
            return None

if __name__ == "__main__":
    searcher = CBETASearcher()
    
    # --- 测试案例 ---
    keyword = "一切有为法"
    print(f"测试关键词: {keyword}")
    
    # 1. 标准全文检索
    print("\n--- 1. 标准全文检索 ---")
    results_std, _ = searcher.search(keyword, rows=3)
    
    # 2. 相似文本搜索
    print("\n--- 2. 相似文本搜索 ---")
    results_sim = searcher.search_similar(keyword)
    
    # 合并结果并保存
    all_results = results_std + results_sim
    searcher.save_results_to_file(all_results, "cbeta_search_test.txt")