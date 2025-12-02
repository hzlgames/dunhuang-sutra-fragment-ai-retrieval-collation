"""调试 search_advanced (all_in_one) API 返回格式"""
import requests

url = "https://cbdata.dila.edu.tw/stable/search/all_in_one"
params = {"q": "日出眾闇", "facet": 1, "rows": 3}

print(f"请求 URL: {url}")
print(f"参数: {params}")

response = requests.get(url, params=params, timeout=20, verify=False)
print(f"\n状态码: {response.status_code}")
print(f"Content-Type: {response.headers.get('Content-Type')}")

data = response.json()
print(f"\n顶层键: {list(data.keys())}")

if "results" in data:
    results = data["results"]
    print(f"\nresults 类型: {type(results)}")
    if isinstance(results, dict):
        print(f"results 键: {list(results.keys())}")
    elif isinstance(results, list):
        print(f"results 是列表，长度: {len(results)}")
        if results:
            print(f"第一个元素: {results[0]}")

