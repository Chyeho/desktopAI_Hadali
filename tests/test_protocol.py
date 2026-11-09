"""单元测试：protocol 请求体与 SSE 事件模型

覆盖字段校验、事件名唯一、序列化 / 反序列化 roundtrip。
"""
import json

import pytest
from pydantic import ValidationError

from protocol.events import (
    EVENT_MODEL_MAP,
    EmotionEvent,
    ErrorEvent,
    EventName,
    StateEvent,
    StateValue,
    TextDeltaEvent,
    ToolCallEvent,
    ToolResultEvent,
    TurnEndEvent,
    TurnStartEvent,
)
from protocol.requests import ChatRequest, InterruptRequest, ModeRequest


class TestChatRequest:
    """ChatRequest：会话 ID 与输入校验"""

    def test_defaults(self):
        req = ChatRequest(text="你好")
        assert req.session_id == "default"
        assert req.mode is None

    def test_accepts_valid_session_id(self):
        assert ChatRequest(session_id="a-b_C9", text="x").session_id == "a-b_C9"

    @pytest.mark.parametrize("sid", ["", "a b", "../evil", "a/b", "x" * 65, "中文"])
    def test_rejects_invalid_session_id(self, sid):
        with pytest.raises(ValidationError):
            ChatRequest(session_id=sid, text="x")

    def test_rejects_empty_text(self):
        with pytest.raises(ValidationError):
            ChatRequest(text="")


class TestOtherRequests:
    """InterruptRequest / ModeRequest"""

    def test_interrupt_default_session(self):
        assert InterruptRequest().session_id == "default"

    def test_interrupt_rejects_bad_session(self):
        with pytest.raises(ValidationError):
            InterruptRequest(session_id="..")

    def test_mode_requires_value(self):
        with pytest.raises(ValidationError):
            ModeRequest(mode="")


class TestEvents:
    """事件模型：命名、序列化、取值约束"""

    def test_event_names_unique(self):
        values = [e.value for e in EventName]
        assert len(values) == len(set(values))

    def test_event_model_map_covers_all_names(self):
        assert set(EVENT_MODEL_MAP) == {e.value for e in EventName}

    def test_turn_start_serialization(self):
        ev = TurnStartEvent(seq=1, turn_id="t1", ts=1762646400000, mode="emotion")
        assert json.loads(ev.model_dump_json()) == {
            "seq": 1,
            "turn_id": "t1",
            "ts": 1762646400000,
            "mode": "emotion",
        }

    def test_state_value_coerced_to_enum(self):
        ev = StateEvent(seq=2, turn_id="t", ts=0, value="thinking")
        assert ev.value is StateValue.THINKING

    def test_state_rejects_unknown_value(self):
        with pytest.raises(ValidationError):
            StateEvent(seq=2, turn_id="t", ts=0, value="sleeping")

    def test_text_delta(self):
        ev = TextDeltaEvent(seq=4, turn_id="t", ts=1, text="你好")
        assert json.loads(ev.model_dump_json())["text"] == "你好"

    def test_emotion_optional_intensity(self):
        ev = EmotionEvent(seq=6, turn_id="t", ts=1, name="relaxed")
        assert ev.intensity is None

    def test_tool_events(self):
        call = ToolCallEvent(seq=7, turn_id="t", ts=1, name="get_weather", args={"city": "北京"})
        result = ToolResultEvent(seq=8, turn_id="t", ts=1, name="get_weather", ok=True, duration_ms=820.0)
        assert call.args["city"] == "北京"
        assert result.ok is True

    def test_error_event_roundtrip(self):
        ev = ErrorEvent(seq=3, turn_id="t", ts=1, code="INTERNAL", message="boom", retryable=True)
        again = EVENT_MODEL_MAP[EventName.ERROR.value].model_validate_json(ev.model_dump_json())
        assert again.code == "INTERNAL"
        assert again.retryable is True

    def test_turn_end_fields(self):
        ev = TurnEndEvent(seq=9, turn_id="t", ts=2, reply="hi", emotion="happy", latency_ms=12.5)
        payload = json.loads(ev.model_dump_json())
        assert payload["emotion"] == "happy"
        assert payload["latency_ms"] == 12.5

    def test_seq_must_be_positive(self):
        with pytest.raises(ValidationError):
            TextDeltaEvent(seq=0, turn_id="t", ts=1, text="x")
