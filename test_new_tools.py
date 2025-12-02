"""测试新扩展的 CBETA 工具"""
from src.cbeta_tools import CBETATools

tools = CBETATools()

print("=" * 60)
print("测试新扩展的 CBETA 工具")
print("=" * 60)

# 1. 经名搜索
print("\n【1. search_title - 经名搜索】")
result = tools.search_title("金刚经")
print(f"状态: {result['status']}")
if result['status'] == 'success':
    print(f"找到: {result['num_found']} 条")
    for r in result['results'][:3]:
        print(f"  - {r.get('title', r)} ({r.get('work', 'N/A')})")

# 2. 目录搜索
print("\n【2. search_toc - 目录搜索】")
result = tools.search_toc("阿含")
print(f"状态: {result['status']}")
if result['status'] == 'success':
    print(f"找到: {result['num_found']} 条")
    for r in result['results'][:3]:
        print(f"  - {r.get('title', r.get('text', r))}")

# 3. 异体字查询
print("\n【3. search_variants - 异体字查询】")
result = tools.search_variants("著衣持鉢")
print(f"状态: {result['status']}")
if result['status'] == 'success':
    print(f"原词: {result.get('original')}")
    variants = result.get('variants', [])
    if isinstance(variants, list):
        print(f"变体数: {len(variants)}")
        for v in variants[:5]:
            print(f"  - {v}")
    else:
        print(f"变体: {variants}")

# 4. 统计分析
print("\n【4. get_facet_stats - 统计分析 (按朝代)】")
result = tools.get_facet_stats("般若波罗蜜", "dynasty")
print(f"状态: {result['status']}")
if result['status'] == 'success':
    stats = result.get('stats', {})
    if isinstance(stats, dict):
        for k, v in list(stats.items())[:5]:
            print(f"  - {k}: {v}")
    else:
        print(f"统计: {str(stats)[:200]}")

# 5. 注解搜索
print("\n【5. search_notes - 注解搜索】")
result = tools.search_notes("舍利弗", rows=5)
print(f"状态: {result['status']}")
if result['status'] == 'success':
    print(f"找到: {result['num_found']} 条")
    for r in result['results'][:2]:
        print(f"  - {str(r)[:100]}...")

print("\n" + "=" * 60)
print("测试完成！")
print("=" * 60)

