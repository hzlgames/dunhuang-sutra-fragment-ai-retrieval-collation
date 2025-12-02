from src.cbeta_search import CBETASearcher

s = CBETASearcher()
queries = [
    "一切有为法",
    "如梦幻泡影",
    "一切有为法 如梦幻泡影",
    "一切有為法"  # Traditional Chinese
]

for q in queries:
    print(f"Testing query: '{q}'")
    results, num_found = s.search(q)  # 正确解包元组
    print(f"Found {len(results)} results (total: {num_found})")
    if results:
        print(f"Top: {results[0].get('title')} ({results[0].get('id')})")
    print("-" * 20)
