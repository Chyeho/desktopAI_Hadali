"""单元测试：core/tracing.py 回合指标

覆盖成功 / 失败字段、用户原文不落全文、追加写入与写入失败容错。
"""
import json

from backend.core.tracing import SUMMARY_MAX_LEN, TurnTracer


def _result(**overrides):
    base = {
        "emotion": "happy",
        "reply": "你好呀",
        "mode": "emotion",
        "steps": 2,
        "tool_calls": [
            {"name": "get_current_time", "args": {}, "ok": True, "duration_ms": 1.5}
        ],
        "latency_ms": 12.0,
    }
    base.update(overrides)
    return base


def _read(path):
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


class TestSuccessRecord:
    """finish_success：成功回合"""

    def test_writes_all_fields(self, tmp_path):
        f = tmp_path / "turns.jsonl"
        tracer = TurnTracer("turn-1", "default", mode="emotion", user_text="你好", turns_file=str(f))
        record = tracer.finish_success(_result())

        lines = _read(f)
        assert len(lines) == 1
        rec = lines[0]
        for key in ("ts", "turn_id", "session_id", "mode", "text_len", "text_summary",
                    "latency_ms", "ok", "emotion", "reply_len", "steps", "tool_calls"):
            assert key in rec
        assert rec["turn_id"] == "turn-1"
        assert rec["session_id"] == "default"
        assert rec["ok"] is True
        assert rec["emotion"] == "happy"
        assert rec["reply_len"] == 3
        assert rec["steps"] == 2
        assert rec["tool_calls"] == [
            {"name": "get_current_time", "ok": True, "duration_ms": 1.5}
        ]
        assert record["turn_id"] == "turn-1"

    def test_appends_multiple_lines(self, tmp_path):
        f = tmp_path / "turns.jsonl"
        tracer = TurnTracer("t", "default", turns_file=str(f))
        tracer.finish_success(_result())
        tracer.finish_success(_result())
        assert len(_read(f)) == 2


class TestErrorRecord:
    """finish_error：失败回合"""

    def test_writes_error_fields(self, tmp_path):
        f = tmp_path / "turns.jsonl"
        tracer = TurnTracer("t2", "work", mode="office", user_text="查询", turns_file=str(f))
        tracer.finish_error("LLM_TIMEOUT", "超时")

        rec = _read(f)[0]
        assert rec["ok"] is False
        assert rec["error_code"] == "LLM_TIMEOUT"
        assert rec["error_message"] == "超时"
        assert rec["session_id"] == "work"

    def test_error_message_truncated(self, tmp_path):
        f = tmp_path / "turns.jsonl"
        tracer = TurnTracer("t3", "default", turns_file=str(f))
        tracer.finish_error("INTERNAL", "x" * 500)
        assert len(_read(f)[0]["error_message"]) == 200


class TestPrivacyAndResilience:
    """用户原文只留长度与截断摘要；写入失败不影响主流程"""

    def test_long_text_truncated(self, tmp_path):
        f = tmp_path / "turns.jsonl"
        text = "啊" * 100
        tracer = TurnTracer("t4", "default", user_text=text, turns_file=str(f))
        tracer.finish_error("INTERNAL", "x")

        rec = _read(f)[0]
        assert rec["text_len"] == 100
        assert rec["text_summary"].endswith("…")
        assert len(rec["text_summary"]) == SUMMARY_MAX_LEN + 1
        assert rec["text_summary"] != text

    def test_write_failure_does_not_raise(self, tmp_path):
        # 传入目录路径，写入必然失败，但不应抛出异常
        tracer = TurnTracer("t5", "default", turns_file=str(tmp_path))
        tracer.finish_success(_result())
