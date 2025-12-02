import sys
import os
import json
from dotenv import load_dotenv

# 添加项目根目录到 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding='utf-8')

from src.ai_agent import CBETAAgent, AgentConfig

load_dotenv()

def test_agent():
    print("="*50)
    print("🧪 Testing CBETA AI Agent")
    print("="*50)
    
    # 模拟一段 OCR 文本
    # 这是一段金刚经的片段
    ocr_text = """
    如是我聞。一時佛在舍衛國祇樹給孤獨園。與大比丘眾千二百五十人俱。
    爾時世尊食時。著衣持鉢。入舍衛大城乞食。於其城中。次第乞已。
    還至本處。飯食訖。收衣鉢。洗足已。敷座而坐。
    """
    
    print(f"📄 Input OCR Text:\n{ocr_text.strip()[:100]}...")
    
    # 配置 Agent
    config = AgentConfig(
        thinking_level="low", # 测试时用 low 以加快速度
        verbose=True,
        max_iterations=5
    )
    
    try:
        agent = CBETAAgent(config)
        result = agent.analyze_and_locate(ocr_text)
        
        print("\n" + "="*50)
        print("✅ Final Answer:")
        print("="*50)
        
        if result:
            print(result.model_dump_json(indent=2))
        else:
            print("❌ No result returned")
            
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_agent()
