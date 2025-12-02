"""
测试 Gemini-3-pro-preview 模型通过 Function Calling 访问URL的能力

验证点：
1. 模型能否理解需要访问URL
2. 模型能否正确调用 fetch_url 工具
3. 模型能否基于URL返回的内容进行推理
"""

import os
import requests
from google import genai
from google.genai import types

def fetch_url(url: str) -> str:
    """
    实际执行URL访问的工具函数
    
    Args:
        url: 要访问的URL地址
        
    Returns:
        返回URL的内容（前1000字符）
    """
    try:
        print(f"🌐 正在访问: {url}")
        response = requests.get(url, timeout=10, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        response.raise_for_status()
        content = response.text[:1000]  # 限制长度
        print(f"✅ 成功获取内容，长度: {len(response.text)} 字符")
        return content
    except Exception as e:
        error_msg = f"访问失败: {str(e)}"
        print(f"❌ {error_msg}")
        return error_msg


def main():
    # 检查API密钥
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        print("❌ 错误：未设置 GOOGLE_API_KEY 环境变量")
        return
    
    print("=" * 60)
    print("测试 Gemini 模型通过 Function Calling 访问URL的能力")
    print("=" * 60)
    
    # 初始化客户端
    client = genai.Client(api_key=api_key)
    
    # 定义工具声明
    tools = [
        {
            "function_declarations": [
                {
                    "name": "fetch_url",
                    "description": "访问指定的URL并获取其内容。适用于需要获取网页信息、API数据或其他在线资源的场景。",
                    "parameters": {
                        "type": "OBJECT",
                        "properties": {
                            "url": {
                                "type": "STRING",
                                "description": "要访问的完整URL地址，例如: https://example.com/api/data"
                            }
                        },
                        "required": ["url"]
                    }
                }
            ]
        }
    ]
    
    # 测试问题：引导模型访问URL
    test_query = """请帮我访问这个URL并告诉我内容概要：
https://httpbin.org/json

这是一个测试API，会返回JSON数据。请访问后告诉我返回了什么。"""
    
    print(f"\n📝 测试问题：\n{test_query}\n")
    
    # 初始化对话历史
    history = [
        types.Content(
            role="user",
            parts=[types.Part(text=test_query)]
        )
    ]
    
    # 配置生成参数
    config = types.GenerateContentConfig(
        temperature=1.0,
        tools=tools,
        tool_config=types.ToolConfig(
            function_calling_config=types.FunctionCallingConfig(
                mode="AUTO"  # 让模型自动决定是否调用工具
            )
        )
    )
    
    max_rounds = 3  # 最多3轮对话
    
    for round_num in range(1, max_rounds + 1):
        print(f"\n{'='*60}")
        print(f"第 {round_num} 轮")
        print(f"{'='*60}")
        
        # 调用模型
        response = client.models.generate_content(
            model="gemini-3-pro-preview",
            contents=history,
            config=config
        )
        
        if not response.candidates:
            print("⚠️ 模型无响应")
            break
        
        candidate = response.candidates[0]
        content = candidate.content
        
        # 添加到历史
        history.append(content)
        
        # 检查是否有工具调用
        has_tool_call = False
        tool_responses = []
        
        for part in content.parts:
            if part.function_call:
                has_tool_call = True
                fn = part.function_call
                print(f"\n🤖 模型调用工具: {fn.name}")
                print(f"   参数: {dict(fn.args)}")
                
                # 执行工具
                if fn.name == "fetch_url":
                    url = fn.args.get("url")
                    result = fetch_url(url)
                    tool_responses.append({
                        "name": fn.name,
                        "response": {"result": result}
                    })
            elif part.text:
                print(f"\n💬 模型回复:\n{part.text}")
        
        if has_tool_call:
            # 将工具结果返回给模型
            parts = []
            for tr in tool_responses:
                parts.append(types.Part.from_function_response(
                    name=tr["name"],
                    response=tr["response"]
                ))
            history.append(types.Content(role="user", parts=parts))
            print(f"\n✅ 工具结果已返回给模型")
        else:
            # 没有工具调用，对话结束
            print("\n✅ 对话完成（无工具调用）")
            break
    
    print("\n" + "="*60)
    print("测试结束")
    print("="*60)
    
    # 总结
    print("\n📊 测试总结：")
    print(f"   - 总轮数: {min(round_num, max_rounds)}")
    print(f"   - 模型是否调用了工具: {'是' if any('function_call' in str(c) for c in history) else '否'}")
    

if __name__ == "__main__":
    main()

