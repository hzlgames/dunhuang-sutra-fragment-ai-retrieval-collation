import json
from pathlib import Path

from src.ai_agent import SessionManager, build_round_history_contents


def test_round_save_and_load(tmp_path):
    manager = SessionManager(storage_dir=str(tmp_path))
    session_id = "test-session"
    record_a = {
        "round_index": 2,
        "timestamp": "2025-12-03T00:00:00Z",
        "summary": "候选 A",
        "tool_calls": [],
        "notes": [],
    }
    record_b = {
        "round_index": 1,
        "timestamp": "2025-12-02T00:00:00Z",
        "summary": "候选 B",
        "tool_calls": [],
        "notes": [],
    }

    manager.save_round(session_id, record_a)
    manager.save_round(session_id, record_b)

    loaded = manager.load_rounds(session_id)
    assert loaded[0]["round_index"] == 1
    assert loaded[1]["round_index"] == 2
    assert loaded[0]["summary"] == "候选 B"
    assert loaded[1]["summary"] == "候选 A"

    persisted_file = Path(tmp_path) / f"{session_id}.rounds.jsonl"
    assert persisted_file.exists()
    lines = list(persisted_file.read_text(encoding="utf-8").splitlines())
    assert len(lines) == 2
    assert json.loads(lines[0])["summary"] in {"候选 A", "候选 B"}


def test_build_round_history_contents_includes_tool_calls():
    rounds = [
        {
            "round_index": 1,
            "summary": "首次 OCR 摘要",
            "tool_calls": [
                {
                    "name": "search_similar",
                    "args": {"query": "法华经"},
                    "result_summary": "命中 T0269",
                    "status": "success",
                }
            ],
            "notes": ["机器人建议扩展搜索"],
        }
    ]

    contents = build_round_history_contents(rounds)
    assert contents
    text = "".join(part.text or "" for part in contents[0].parts)
    assert "历史第 1 轮摘要" in text
    assert "工具调用:" in text
    assert "search_similar" in text

