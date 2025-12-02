import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Iterable, List

from dotenv import load_dotenv
load_dotenv()

from src.ai_agent import CBETAAgent, AgentConfig, StreamHandler
from src.schemas import FinalAnswer


def parse_args():
    parser = argparse.ArgumentParser(
        description="利用 Gemini 官方 API + CBETA 工具完成 OCR → 推理 → 考证的全流程调试。"
    )
    parser.add_argument(
        "--input",
        default="input",
        help="待处理图片目录，默认 input/",
    )
    parser.add_argument(
        "--output",
        default="output",
        help="结果与日志输出目录，默认 output/",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="关闭控制台流式输出，仅写入日志文件。",
    )
    return parser.parse_args()


def iter_images(input_dir: Path) -> Iterable[Path]:
    supported = {".png", ".jpg", ".jpeg"}
    for path in sorted(input_dir.iterdir()):
        if path.suffix.lower() in supported:
            yield path


def build_stream_handler(log_path: Path, mirror_stdout: bool) -> StreamHandler:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_file = log_path.open("w", encoding="utf-8")

    def handler(event_type: str, payload):
        entry = {
            "ts": datetime.now().isoformat(),
            "event": event_type,
            "payload": payload,
        }
        log_file.write(json.dumps(entry, ensure_ascii=False) + "\n")
        log_file.flush()

        if not mirror_stdout:
            return

        text = (payload or {}).get("text", "")
        if event_type == "thought":
            print(f"🧠 {text.strip()}")
        elif event_type == "text":
            print(f"💬 {text.strip()}")
        elif event_type == "tool_call":
            print(f"🛠️  调用 {payload.get('name')}，参数: {payload.get('args')}")
        elif event_type == "tool_result":
            summary = payload.get("summary", "")
            print(f"✅ 工具 {payload.get('name')} 完成: {summary}")
        elif event_type == "error":
            print(f"⚠️ {payload.get('message')}")

    def close():
        log_file.close()

    handler.close = close  # type: ignore[attr-defined]
    return handler


def summarize_final_answer(answer: FinalAnswer) -> str:
    lines: List[str] = []

    lines.append("========== OCR 摘要 ==========")
    lines.append(answer.ocr_result.recognized_text.strip() or "(空)")
    if answer.ocr_notes:
        lines.append("\n逐列/逐句说明：")
        for idx, note in enumerate(answer.ocr_notes, 1):
            lines.append(f"  {idx}. {note}")
    if answer.ocr_result.uncertain_chars:
        lines.append(f"\n不确定字符：{', '.join(answer.ocr_result.uncertain_chars)}")
    if answer.ocr_result.word_segmentation:
        lines.append(f"分词片段：{', '.join(answer.ocr_result.word_segmentation)}")

    lines.append("\n========== 候选经文（按置信度） ==========")
    if answer.scripture_locations:
        for idx, loc in enumerate(answer.scripture_locations, 1):
            lines.append(f"{idx}. {loc.work_title} ({loc.work_id})")
            lines.append(
                f"   卷: {loc.juan} | 藏经: {loc.canon or '未知'} | 朝代: {loc.dynasty or '未知'} | 作译者: {loc.author or '未知'}"
            )
            lines.append(
                f"   置信度: {loc.confidence:.2f} | 依据: {loc.confidence_reason}"
            )
            lines.append(f"   匹配片段: {loc.snippet}")
    else:
        lines.append("暂无可信候选，请手动继续搜索。")

    if answer.candidate_insights:
        lines.append("\n补充洞察：")
        for idx, insight in enumerate(answer.candidate_insights, 1):
            lines.append(f"  - {insight}")

    lines.append("\n========== 校对提示 ==========")
    if answer.verification_points:
        for idx, point in enumerate(answer.verification_points, 1):
            lines.append(f"{idx}. {point}")
    else:
        lines.append("暂无特别提示，可依据上方候选继续人工核对。")

    lines.append("\n========== 建议的下一步 ==========")
    if answer.next_actions:
        for idx, action in enumerate(answer.next_actions, 1):
            lines.append(f"{idx}. {action}")
    else:
        lines.append("未提供具体建议。")

    lines.append("\n========== 推理与工具 ==========")
    lines.append(answer.reasoning.strip() or "(无)")
    lines.append(f"\n搜索迭代次数: {answer.search_iterations}")
    lines.append(f"使用工具: {', '.join(answer.tools_used) if answer.tools_used else '无'}")
    lines.append(f"会话 ID: {answer.session_id or 'N/A'}")

    return "\n".join(lines)


def process_image(agent: CBETAAgent, image_path: Path, output_dir: Path, mirror_stdout: bool):
    print(f"\n📷 处理图片: {image_path.name}")
    log_path = output_dir / f"{image_path.stem}_stream.jsonl"
    handler = build_stream_handler(log_path, mirror_stdout)
    try:
        result = agent.analyze_and_locate(image_path=str(image_path), stream_handler=handler)
    finally:
        if hasattr(handler, "close"):
            handler.close()  # type: ignore[attr-defined]

    if not result:
        print("❌ 本次未获取到结构化结果")
        return

    json_path = output_dir / f"{image_path.stem}_result.json"
    json_path.write_text(result.model_dump_json(indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"💾 结构化结果已保存: {json_path}")

    report_path = output_dir / f"{image_path.stem}_report.txt"
    report_path.write_text(summarize_final_answer(result), encoding="utf-8")
    print(f"📝 文本报告已保存: {report_path}")


def main():
    args = parse_args()
    input_dir = Path(args.input)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    images = list(iter_images(input_dir))
    if not images:
        print(f"⚠️ 未在 {input_dir} 找到图片（支持 PNG/JPG/JPEG）。")
        return

    config = AgentConfig(verbose=not args.quiet)
    agent = CBETAAgent(config=config)

    for image_path in images:
        process_image(agent, image_path, output_dir, mirror_stdout=not args.quiet)

    print("\n✅ 全部图片处理完成。")


if __name__ == "__main__":
    main()
