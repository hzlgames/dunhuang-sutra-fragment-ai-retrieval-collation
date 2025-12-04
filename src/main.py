import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Iterable, List

from dotenv import load_dotenv
load_dotenv()

from src.ai_agent import CBETAAgent, AgentConfig, StreamHandler
from src.schemas import FinalAnswer
from src.config import get_output_dir


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
        default=None,
        help="结果与日志输出目录，默认使用环境变量 OUTPUT_DIR 或 output/",
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

    # 片段关键信息：物质形态、题记、版式等
    if getattr(answer, "key_facts", None):
        lines.append("\n========== 片段关键信息 ==========")
        for idx, fact in enumerate(answer.key_facts, 1):
            lines.append(f"{idx}. {fact}")

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

            # 若模型已给出外部在线阅览链接（如 Gallica），直接展示
            if getattr(loc, "external_url", None):
                source_label = getattr(loc, "source", None) or "外部"
                lines.append(f"   {source_label}在线阅览: {loc.external_url}")
            else:
                # 默认假定为 CBETA 经文，附带可直接打开的 CBETA 在线阅览链接
                # 约定：work_id 如 T0001，卷号 loc.juan 可转为三位数字，例如 1 -> 001
                cbeta_url = None
                try:
                    juan_num = int(str(loc.juan).strip())
                    cbeta_url = f"https://cbetaonline.dila.edu.tw/zh/{loc.work_id}_{juan_num:03d}"
                except (ValueError, TypeError):
                    # 卷号无法转为整数时，只给一个按经号搜索的备用链接
                    cbeta_url = f"https://cbetaonline.dila.edu.tw/zh/search?keyword={loc.work_id}"

                lines.append(f"   在线阅览: {cbeta_url}")
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


def build_fragment_note(answer: FinalAnswer, image_name: str) -> str:
    """
    构造单张图片对应的“文献整理说明”，风格参考 `文献整理结果示例.txt`。
    - image_name：不含扩展名的文件名，直接作为编号使用（如：P.3801、Дх.00931）。
    """
    lines: List[str] = []

    # 编号行
    lines.append(image_name)

    # 文献内容
    lines.append("文献内容：")
    if answer.scripture_locations:
        for idx, loc in enumerate(answer.scripture_locations, 1):
            # 基本书目信息（CBETA / Gallica 共用骨架）
            base_parts: List[str] = []
            # (1) 经名
            base_parts.append(loc.work_title)
            # (2) 经号（如 CBETA T08, no. 235）
            if loc.canon and loc.work_id:
                # work_id 通常为 T0235/X0021 等，这里拆成藏经/编号两部分
                canon_code = loc.canon
                work_code = loc.work_id
                base_parts.append(f"CBETA，{canon_code}，no.{work_code.lstrip(canon_code)}")
            elif loc.work_id:
                base_parts.append(f"编号：{loc.work_id}")
            # (3) 译者/作者
            if loc.author:
                base_parts.append(f"{loc.author}译")

            # 组合主句
            main_sentence = "，".join(base_parts) if base_parts else loc.work_title

            # 完整度描述由 AI 在置信度理由中常会体现，这里简化引用
            completeness = ""
            if "首尾" in (loc.confidence_reason or ""):
                completeness = loc.confidence_reason

            # Gallica / 其他来源标记
            source_label = getattr(loc, "source", None)
            if source_label and source_label.lower() == "gallica":
                main_sentence += "（Gallica 写本）"

            # 输出一条文献内容说明
            content_line = f"（{idx}）{main_sentence}"
            if completeness:
                content_line += f"。{completeness}"
            lines.append(content_line)

            # 若有在线链接，继续在内容部分给出
            external_url = getattr(loc, "external_url", None)
            if external_url:
                if source_label and source_label.lower() == "gallica":
                    lines.append(f"    Gallica 在线阅览：{external_url}")
                else:
                    lines.append(f"    在线阅览：{external_url}")
    else:
        lines.append("（暂未能明确定位对应经文，需人工补充。）")

    # 物质形态：
    if answer.key_facts:
        for idx, fact in enumerate(answer.key_facts, 1):
            lines.append(f"{idx}. {fact}")
    else:
        lines.append("物质形态：（本工具暂无法从图像中精确判断装帧与残损情况，建议研究者根据原件补充，如“册子本，两张对开叶，首尾俱残”等。）")

    # 参考文献（可选）：尝试从 candidate_insights / next_actions 中抽取
    # refs: List[str] = []
    # for item in (answer.candidate_insights or []):
    #     if "《" in item and "》" in item:
    #         refs.append(item)
    # for item in (answer.next_actions or []):
    #     if "《" in item and "》" in item and item not in refs:
    #         refs.append(item)
    #
    # if refs:
    #     lines.append("参：")
    #     for idx, r in enumerate(refs, 1):
    #         lines.append(f"（{idx}）{r}")

    return "\n".join(lines)

def process_image(agent: CBETAAgent, image_path: Path, output_dir: Path, mirror_stdout: bool):
    print(f"\n📷 处理图片: {image_path.name}")
    
    # 创建以图片名称命名的子文件夹
    pic_output_dir = output_dir / image_path.stem
    pic_output_dir.mkdir(parents=True, exist_ok=True)
    
    log_path = pic_output_dir / f"{image_path.stem}_stream.jsonl"
    handler = build_stream_handler(log_path, mirror_stdout)
    try:
        result = agent.analyze_and_locate(image_path=str(image_path), stream_handler=handler)
    finally:
        if hasattr(handler, "close"):
            handler.close()  # type: ignore[attr-defined]

    if not result:
        print("❌ 本次未获取到结构化结果")
        return

    json_path = pic_output_dir / f"{image_path.stem}_result.json"
    json_path.write_text(result.model_dump_json(indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"💾 结构化结果已保存: {json_path}")

    report_path = pic_output_dir / f"{image_path.stem}_report.txt"
    report_path.write_text(summarize_final_answer(result), encoding="utf-8")
    print(f"📝 文本报告已保存: {report_path}")

    # 生成"文献整理说明"附带文档
    note_path = pic_output_dir / f"{image_path.stem}_note.txt"
    note_path.write_text(build_fragment_note(result, image_path.stem), encoding="utf-8")
    print(f"📄 文献整理说明已保存: {note_path}")


def main():
    args = parse_args()
    input_dir = Path(args.input)
    # 优先使用命令行参数，否则使用环境变量或默认值
    output_dir = Path(args.output) if args.output else get_output_dir()

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
