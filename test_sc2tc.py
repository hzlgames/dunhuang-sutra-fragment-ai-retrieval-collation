"""测试简繁转换功能"""
from src.cbeta_tools import CBETATools

t = CBETATools()

test_cases = [
    "一切有为法",
    "如梦幻泡影",
    "金刚经",
]

print("=" * 50)
print("简繁转换测试")
print("=" * 50)

for sc in test_cases:
    tc = t._convert_sc2tc(sc)
    print(f"简体: {sc}")
    print(f"繁体: {tc}")
    print(f"是否转换: {sc != tc}")
    print("-" * 30)

