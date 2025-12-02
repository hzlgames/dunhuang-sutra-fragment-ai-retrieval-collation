import sys
import os
from dotenv import load_dotenv

# 添加项目根目录到 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.ai_agent import CBETAAgent, AgentConfig

load_dotenv()

def simple_test():
    print("="*60)
    print("简单测试：AI Agent 基本功能")
    print("="*60)
    
    # 使用简短的文本测试
    test_text = "如是我聞一時佛在舍衛國"
    
    print(f"\n输入文本: {test_text}")
    print("\n配置 Agent...")
    
    config = AgentConfig(
        thinking_level="low",
        verbose=True,
        max_iterations=3  # 限制为3轮以加快速度
    )
    
    try:
        print("\n初始化 Agent...")
        agent = CBETAAgent(config)
        
        print("\n开始分析...")
        result = agent.analyze_and_locate(ocr_text=test_text)
        
        if result:
            print("\n" + "="*60)
            print("测试成功！结果摘要:")
            print("="*60)
            print(f"识别文本: {result.ocr_result.recognized_text[:50]}...")
            print(f"搜索次数: {result.search_iterations}")
            print(f"使用工具: {', '.join(result.tools_used)}")
            
            if result.scripture_locations:
                print(f"\n找到 {len(result.scripture_locations)} 个可能的经文位置:")
                for i, loc in enumerate(result.scripture_locations[:3], 1):
                    print(f"\n{i}. {loc.work_title}")
                    print(f"   经号: {loc.work_id}")
                    print(f"   置信度: {loc.confidence:.2f}")
            
            print("\n✅ 测试通过")
            return True
        else:
            print("\n❌ 未返回结果")
            return False
            
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = simple_test()
    sys.exit(0 if success else 1)
