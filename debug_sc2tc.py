"""调试简繁转换 API"""
import requests

base_url = "https://cbdata.dila.edu.tw/stable"

test_text = "一切有为法"
print(f"测试文本: {test_text}")

# 测试简繁转换 API
url = f"{base_url}/chinese_tools/sc2tc"
print(f"\n请求 URL: {url}")
print(f"参数: q={test_text}")

try:
    response = requests.get(url, params={"q": test_text}, timeout=10, verify=False)
    print(f"\n状态码: {response.status_code}")
    print(f"Content-Type: {response.headers.get('Content-Type')}")
    print(f"响应内容: {response.text[:500]}")
    
    if response.status_code == 200:
        try:
            data = response.json()
            print(f"\nJSON 解析结果: {data}")
            print(f"result 字段: {data.get('result')}")
        except Exception as e:
            print(f"\nJSON 解析失败: {e}")
except Exception as e:
    print(f"\n请求失败: {e}")

