import sys
import os
import json

# 添加项目根目录到 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding='utf-8')

from src.cbeta_tools import CBETATools

def test_tools():
    tools = CBETATools()
    
    print("="*50)
    print("Testing search_full_text...")
    res = tools.search_full_text("一切有为法", rows=2)
    print(json.dumps(res, indent=2, ensure_ascii=False))
    
    print("\n"+"="*50)
    print("Testing search_advanced...")
    res = tools.search_advanced("法鼓", facet=True)
    # 只打印部分结果避免刷屏
    if res.get("status") == "success":
        print(f"Num found: {res.get('num_found')}")
        print("Facets keys:", list(res.get("facets", {}).keys()))
    else:
        print(res)
        
    print("\n"+"="*50)
    print("Testing search_similar...")
    # 使用一段较长的文本
    text = "如是我聞。一時佛在舍衛國祇樹給孤獨園。與大比丘眾千二百五十人俱。"
    res = tools.search_similar(text)
    print(json.dumps(res, indent=2, ensure_ascii=False)[:500] + "...")

if __name__ == "__main__":
    test_tools()
