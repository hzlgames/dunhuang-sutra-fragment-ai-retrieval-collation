from pathlib import Path

from dotenv import load_dotenv
from src.ai_agent import CBETAAgent, AgentConfig

load_dotenv()


def verify():
    print("Starting verification with official Gemini API...")
    config = AgentConfig(verbose=True)
    agent = CBETAAgent(config)
    image_path = Path("input") / "unknown_fragment.png"

    if not image_path.exists():
        print(f"Image not found: {image_path}")
        return

    result = agent.analyze_and_locate(image_path=str(image_path))
    if not result:
        print("No structured result returned.")
        return

    print("\n" + "=" * 50)
    print("FINAL RESULT:")
    print("=" * 50)
    print(result.model_dump_json(indent=2, ensure_ascii=False))
    print("=" * 50)


if __name__ == "__main__":
    verify()
