"""
调试脚本：检查 API 连接和配置 (已禁用 SSL 验证)
"""
import os
import requests
import httpx  # 需要安装: pip install httpx
from dotenv import load_dotenv
from openai import OpenAI
import urllib3

# 禁用这类安全警告，保持输出只有我们要的信息
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

load_dotenv()

print("=" * 60)
print("API 连接诊断 (SSL 验证已关闭)")
print("=" * 60)

# 1. 检查 API Key
api_key = os.getenv("GEMINI_API_KEY")
if api_key:
    print(f"✅ API Key 已配置 (长度: {len(api_key)})")
    print(f"   前10字符: {api_key[:10]}...")
else:
    print("❌ 未找到 GEMINI_API_KEY")
    exit(1)

# 2. 检查网络连接
base_url = "https://new.12ai.org/v1"
print(f"\n🌐 测试连接到: {base_url}")

try:
    # 修改点 1: 添加 verify=False 跳过证书验证
    response = requests.get(base_url, timeout=5, verify=False)
    print(f"✅ 服务器响应: {response.status_code}")
except requests.exceptions.Timeout:
    print("❌ 连接超时")
    exit(1)
except requests.exceptions.ConnectionError as e:
    print(f"❌ 连接错误: {e}")
    exit(1)
except Exception as e:
    print(f"⚠️  其他错误: {e}")

# 3. 测试简单的 API 调用（不带图片）
print(f"\n📡 测试 API 调用...")
try:
    # 修改点 2: 为 OpenAI 配置一个不验证 SSL 的 httpx 客户端
    http_client = httpx.Client(verify=False)
    
    client = OpenAI(
        api_key=api_key,
        base_url=base_url,
        http_client=http_client  # 注入自定义客户端
    )
    
    print("   发送测试请求...")
    response = client.chat.completions.create(
        model="gemini-3-pro-preview", # 如果报错模型不存在，尝试改为 gemini-1.5-pro
        messages=[
            {"role": "user", "content": "Hello, reply with 'OK' only."}
        ],
        max_tokens=9192,
        timeout=10.0
    )
    
    print(f"✅ API 调用成功!")
    print(f"   响应: {response.choices[0].message.content}")
    
except Exception as e:
    print(f"❌ API 调用失败: {type(e).__name__}")
    print(f"   错误详情: {e}")
    # import traceback
    # traceback.print_exc()

print("\n" + "=" * 60)