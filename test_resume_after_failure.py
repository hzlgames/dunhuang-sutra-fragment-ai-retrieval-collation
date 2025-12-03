"""
简单验证：CBETAAgent 在“中途不输出最终结果”后，能否基于已有 session 继续思考并生成完整结果。

使用方式（在项目根目录）：

    python test_resume_after_failure.py

脚本会：
1. 创建一个新的 session_id；
2. 第一次运行：以 include_final_output=False 调用 analyze_and_locate，只执行工具轮并写入 rounds 记录，不生成最终 JSON；
3. 第二次运行：调用 resume_with_session(session_id=同一个)，基于已有 rounds 继续思考并生成 FinalAnswer；
4. 打印两次运行的关键信息，并检查 sessions/<session_id>.rounds.jsonl 是否存在且包含至少一条记录。
"""

from pathlib import Path

from src.ai_agent import AgentConfig, CBETAAgent


def main():
    image_path = Path("input/test0.png")
    if not image_path.exists():
        print("❌ 找不到测试图片 input/test0.png，请先确认该文件存在。")
        return

    print("🚀 初始化 CBETAAgent（低思考等级、轮数 2，加快测试）...")
    config = AgentConfig(thinking_level="low", max_tool_rounds=2, verbose=True)
    agent = CBETAAgent(config=config)

    # 1. 手动创建一个会话，用于模拟“第一次运行中断后后续续跑”
    session_id = agent.session_manager.create_session()
    print(f"🧾 创建测试会话 session_id = {session_id}")

    # 2. 第一次运行：只进行工具轮，不做最终结构化输出（模拟中途失败/中断）
    print("\n=== 第一次运行：仅进行工具轮，不生成最终 JSON（include_final_output=False） ===")
    result_first = agent.analyze_and_locate(
        image_path=str(image_path),
        resume_session_id=session_id,
        include_final_output=False,
    )

    if result_first is not None:
        print("⚠️ 第一次运行意外返回了 FinalAnswer，但本测试只关心 rounds 持久化与续跑能力。")

    rounds_file = Path("sessions") / f"{session_id}.rounds.jsonl"
    if not rounds_file.exists():
        print(f"❌ 未找到轮次记录文件：{rounds_file}")
        return

    rounds_lines = [ln for ln in rounds_file.read_text(encoding="utf-8").splitlines() if ln.strip()]
    print(f"✅ 轮次记录文件已生成，共 {len(rounds_lines)} 行。")

    # 3. 第二次运行：基于同一 session_id 继续思考，并生成最终结构化结果
    print("\n=== 第二次运行：基于已有 session 续跑，并生成 FinalAnswer ===")
    final_result = agent.resume_with_session(
        session_id=session_id,
        image_path=str(image_path),
        include_final_output=True,
    )

    if final_result is None:
        print("❌ 续跑后仍未能生成 FinalAnswer，断点续跑行为需要进一步排查。")
        return

    print("🎉 续跑成功生成 FinalAnswer，关键字段预览：")
    print(f"- session_id: {final_result.session_id}")
    print(f"- ocr_result.recognized_text 前 80 字: {final_result.ocr_result.recognized_text[:80]!r}")
    print(f"- scripture_locations 数量: {len(final_result.scripture_locations)}")


if __name__ == "__main__":
    main()


