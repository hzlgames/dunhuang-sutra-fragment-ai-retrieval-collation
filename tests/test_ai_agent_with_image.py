import sys
import os
from dotenv import load_dotenv

# 添加项目根目录到 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding='utf-8')

from src.ai_agent import CBETAAgent, AgentConfig

load_dotenv()

def test_agent_with_image():
    print("="*50)
    print("🧪 Testing CBETA AI Agent with Image Input")
    print("="*50)
    
    image_path = "input/test_fragment.png"
    if not os.path.exists(image_path):
        print(f"❌ Image not found: {image_path}")
        return

    print(f"🖼️ Processing image: {image_path}")
    
    # 配置 Agent
    config = AgentConfig(
        thinking_level="low", # 测试时用 low
        verbose=True,
        max_iterations=8 # 允许更多轮次以完成 OCR + 搜索
    )
    
    try:
        agent = CBETAAgent(config)
        # 传入图片路径，不传入 OCR 文本，让 AI 自行识别
        result = agent.analyze_and_locate(image_path=image_path)
        
        print("\n" + "="*50)
        print("✅ Final Answer:")
        print("="*50)
        
        if result:
            print(result.model_dump_json(indent=2))
            
            # 打印简要报告
            print("\n📊 Summary:")
            print(f"OCR Text: {result.ocr_result.recognized_text[:50]}...")
            print(f"Iterations: {result.search_iterations}")
            if result.scripture_locations:
                top_match = result.scripture_locations[0]
                print(f"Top Match: {top_match.work_title} (Confidence: {top_match.confidence})")
        else:
            print("❌ No result returned")
            
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_agent_with_image()
