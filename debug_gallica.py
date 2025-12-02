"""调试 Gallica API"""
import requests

# 测试 SRU 搜索
url = "https://gallica.bnf.fr/SRU"
params = {
    "operation": "searchRetrieve",
    "version": "1.2",
    "query": 'gallica any "Dunhuang"',
    "maximumRecords": 3
}

print(f"请求 URL: {url}")
print(f"参数: {params}")

try:
    response = requests.get(url, params=params, timeout=30)
    print(f"\n状态码: {response.status_code}")
    print(f"Content-Type: {response.headers.get('Content-Type')}")
    print(f"\n响应内容 (前2000字符):\n{response.text[:2000]}")
except Exception as e:
    print(f"请求失败: {e}")

