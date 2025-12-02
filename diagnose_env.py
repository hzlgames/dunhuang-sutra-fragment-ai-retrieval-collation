"""
环境变量诊断脚本
"""
import os
from dotenv import load_dotenv

print("=" * 70)
print("环境变量诊断")
print("=" * 70)

# 1. 检查 .env 文件是否存在
env_file = ".env"
if os.path.exists(env_file):
    print(f"\n✅ .env 文件存在")
    
    # 读取文件内容
    with open(env_file, "r", encoding="utf-8") as f:
        lines = f.readlines()
    
    print(f"   文件总行数: {len(lines)}")
    
    # 查找 GOOGLE_API_KEY
    for i, line in enumerate(lines, 1):
        if line.strip().startswith("GOOGLE_API_KEY="):
            print(f"\n📍 找到 GOOGLE_API_KEY 配置 (第 {i} 行):")
            key_value = line.strip().split("=", 1)[1]
            print(f"   原始值: {repr(key_value)}")
            print(f"   值长度: {len(key_value)}")
            print(f"   前10字符: {key_value[:10]}...")
            print(f"   是否为占位符: {key_value == 'your_google_api_key_here'}")
            
            # 检查是否包含隐藏字符
            if '\r' in key_value or '\n' in key_value:
                print("   ⚠️  包含换行符")
            if ' ' in key_value:
                print("   ⚠️  包含空格")
            break
    else:
        print("\n❌ 未找到 GOOGLE_API_KEY 配置")
else:
    print(f"\n❌ .env 文件不存在")

# 2. 加载环境变量前
print("\n" + "-" * 70)
print("加载环境变量前:")
google_key_before = os.getenv("GOOGLE_API_KEY")
print(f"   GOOGLE_API_KEY: {repr(google_key_before)}")

# 3. 加载环境变量
print("\n🔄 执行 load_dotenv()...")
result = load_dotenv(override=True)
print(f"   返回值: {result}")

# 4. 加载环境变量后
print("\n加载环境变量后:")
google_key_after = os.getenv("GOOGLE_API_KEY")
print(f"   GOOGLE_API_KEY: {repr(google_key_after)}")

if google_key_after:
    print(f"   长度: {len(google_key_after)}")
    print(f"   前10字符: {google_key_after[:10]}...")
    print(f"   后10字符: ...{google_key_after[-10:]}")
    
    # 检查是否是有效的 Google API Key 格式
    if google_key_after.startswith("AIza"):
        print("   ✅ 格式正确 (以 AIza 开头)")
    else:
        print(f"   ⚠️  格式可能不正确 (不以 AIza 开头，而是以 {google_key_after[:4]} 开头)")
    
    if len(google_key_after) == 39:
        print("   ✅ 长度正确 (39 字符)")
    else:
        print(f"   ⚠️  长度可能不正确 (应为 39 字符，实际为 {len(google_key_after)} 字符)")
else:
    print("   ❌ 未加载到值")

# 5. 检查 GEMINI_API_KEY
print("\n" + "-" * 70)
gemini_key = os.getenv("GEMINI_API_KEY")
if gemini_key:
    print(f"GEMINI_API_KEY (代理): {repr(gemini_key[:20])}... (长度: {len(gemini_key)})")
else:
    print("GEMINI_API_KEY: 未配置")

print("\n" + "=" * 70)
