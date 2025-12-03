"""
最小化 Gemini Batch API 验证脚本

用途：
- 不依赖本项目其它代码，只验证当前环境下 Gemini Batch API 是否可用；
- 创建一个简单的批处理任务，请模型各写一首关于「云」和「猫」的中文小诗。

前置条件：
- 已安装 google-genai：  pip install google-genai
- 已在环境变量中配置 GOOGLE_API_KEY 或 GEMINI_API_KEY
"""

import os
import time

from dotenv import load_dotenv
from google import genai


def main() -> None:
    # 1. 加载 .env 并初始化 Gemini 客户端（优先使用 GOOGLE_API_KEY，其次 GEMINI_API_KEY）
    #    注意：每次单独运行 Python 脚本都会启动一个新进程，不会自动继承 diagnose_env.py 里的 load_dotenv 结果，
    #    因此这里需要显式调用一次。
    load_dotenv(override=True)
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("未在环境变量中找到 GOOGLE_API_KEY 或 GEMINI_API_KEY，无法初始化 Gemini 客户端。")

    client = genai.Client(api_key=api_key)

    # 2. 按官方文档构造最小化 inline 请求列表
    inline_requests = [
        {
            "contents": [
                {
                    "parts": [
                        {"text": "请用中文写一首四句小诗，主题是“云”。"},
                    ]
                }
            ]
        },
        {
            "contents": [
                {
                    "parts": [
                        {"text": "请用中文写一首四句小诗，主题是“猫”。"},
                    ]
                }
            ]
        },
    ]

    # 3. 创建 Batch 任务
    # 模型名称请尽量与官方文档和你账号已开通的模型保持一致；
    # 若运行报 404/INVALID_ARGUMENT，可将 model 改为文档中当前推荐的 Batch 支持模型。
    job = client.batches.create(
        model="models/gemini-2.5-flash",
        src=inline_requests,
        config={
            "display_name": "minimal-batch-job",
        },
    )

    job_name = job.name
    print(f"📨 已创建 Batch 任务: {job_name}")
    print("⏳ 开始轮询任务状态...")

    # 4. 轮询状态直至任务结束
    terminal_states = {
        "JOB_STATE_SUCCEEDED",
        "JOB_STATE_FAILED",
        "JOB_STATE_CANCELLED",
        "JOB_STATE_EXPIRED",
    }

    while True:
        job = client.batches.get(name=job_name)
        state = job.state
        state_name = getattr(state, "name", str(state))
        print(f"当前状态: {state_name}")

        if state_name in terminal_states:
            break

        time.sleep(10)

    print(f"✅ 任务结束，最终状态: {state_name}")

    # 5. 输出每条 inline 响应结果
    dest = getattr(job, "dest", None)
    inlined = getattr(dest, "inlined_responses", []) if dest else []

    if not inlined:
        print("⚠️ 未找到任何 inline 响应（dest.inlined_responses 为空），请对照官方文档检查字段名是否有更新。")
        return

    for idx, item in enumerate(inlined, start=1):
        print(f"\n--- 响应 {idx} ---")
        if getattr(item, "error", None):
            print(f"❌ 错误: {item.error}")
        elif getattr(item, "response", None):
            # 对应 GenerateContentResponse 对象，直接读 text
            try:
                print(item.response.text)
            except Exception:
                # 回退打印原始对象，方便调试
                print(repr(item.response))
        else:
            print("⚠️ 无 response / error 字段内容。")


if __name__ == "__main__":
    main()


