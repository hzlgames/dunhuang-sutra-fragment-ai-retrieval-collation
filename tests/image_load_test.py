import os
import sys
from pathlib import Path
from src.ai_agent import CBETAAgent, AgentConfig

# Ensure project root is in sys.path
src_path = os.path.join(Path(__file__).resolve().parents[1], 'src')
sys.path.insert(0, src_path)

def test_image_load():
    print("=== 测试图片加载与上传 ===")
    image_path = os.path.join(os.path.dirname(__file__), '..', 'input', 'test_fragment.png')
    image_path = os.path.abspath(image_path)
    print(f"图片路径: {image_path}")
    if not os.path.exists(image_path):
        print("❌ 图片不存在！")
        return
    config = AgentConfig(thinking_level="low", max_iterations=2, verbose=True)
    agent = CBETAAgent(config)
    try:
        result = agent.analyze_and_locate(image_path=image_path)
        if result:
            print("✅ 获得结构化结果:")
            print(result)
        else:
            print("⚠️ 未返回结构化结果")
    except Exception as e:
        # 捕获 Gemini 空输出错误并提供调试信息
        print(f"❌ 运行出错: {e}")
        import traceback
        traceback.print_exc()
        print("\n调试提示：检查 image_path 是否正确，确保模型支持图像输入，或尝试使用 OCR 文本代替图像进行测试。")

if __name__ == "__main__":
    test_image_load()
