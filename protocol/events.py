'''SSE 事件模型（协议 v1）

每条事件都带公共字段：seq（本轮从 1 递增）、turn_id、ts（Unix 毫秒）。
server 用 model_dump_json() 序列化；client 可按 EVENT_MODEL_MAP 反序列化。
'''
from enum import Enum

from pydantic import BaseModel, Field


class EventName(str, Enum):
    '''SSE 事件名（与 event: 行一一对应）'''
    TURN_START = "turn.start"
    STATE = "state"
    TEXT_DELTA = "text.delta"
    TEXT_DONE = "text.done"
    EMOTION = "emotion"
    TOOL_CALL = "tool.call"
    TOOL_RESULT = "tool.result"
    TURN_END = "turn.end"
    ERROR = "error"
    AUDIO_START = "audio.start"
    AUDIO_DELTA = "audio.delta"
    AUDIO_END = "audio.end"


class StateValue(str, Enum):
    '''state 事件的取值'''
    THINKING = "thinking"
    SPEAKING = "speaking"
    IDLE = "idle"


class ErrorCode(str, Enum):
    '''error 事件的错误码'''
    BAD_REQUEST = "BAD_REQUEST"
    UNAUTHORIZED = "UNAUTHORIZED"
    SESSION_BUSY = "SESSION_BUSY"
    LLM_TIMEOUT = "LLM_TIMEOUT"
    LLM_ERROR = "LLM_ERROR"
    TOOL_ERROR = "TOOL_ERROR"
    INTERRUPTED = "INTERRUPTED"
    INTERNAL = "INTERNAL"


class BaseEvent(BaseModel):
    '''所有事件的公共字段'''
    seq: int = Field(ge=1, description="本轮内从 1 递增")
    turn_id: str
    ts: int = Field(description="Unix 毫秒时间戳")


class TurnStartEvent(BaseEvent):
    mode: str


class StateEvent(BaseEvent):
    value: StateValue


class TextDeltaEvent(BaseEvent):
    text: str


class TextDoneEvent(BaseEvent):
    text: str


class EmotionEvent(BaseEvent):
    name: str
    intensity: float | None = None


class ToolCallEvent(BaseEvent):
    name: str
    args: dict


class ToolResultEvent(BaseEvent):
    name: str
    ok: bool
    duration_ms: float


class TurnEndEvent(BaseEvent):
    reply: str
    emotion: str
    latency_ms: float


class ErrorEvent(BaseEvent):
    code: str
    message: str
    retryable: bool


# ---- audio.* 本期只定义模型，不发送（未来 server 侧 TTS） ----

class AudioStartEvent(BaseEvent):
    format: str = "pcm_s16le"
    sample_rate: int = 24000


class AudioDeltaEvent(BaseEvent):
    data: str


class AudioEndEvent(BaseEvent):
    reason: str = "done"


# 事件名 → 事件模型（client 反序列化 / 协议测试共用）
EVENT_MODEL_MAP: dict[str, type[BaseEvent]] = {
    EventName.TURN_START.value: TurnStartEvent,
    EventName.STATE.value: StateEvent,
    EventName.TEXT_DELTA.value: TextDeltaEvent,
    EventName.TEXT_DONE.value: TextDoneEvent,
    EventName.EMOTION.value: EmotionEvent,
    EventName.TOOL_CALL.value: ToolCallEvent,
    EventName.TOOL_RESULT.value: ToolResultEvent,
    EventName.TURN_END.value: TurnEndEvent,
    EventName.ERROR.value: ErrorEvent,
    EventName.AUDIO_START.value: AudioStartEvent,
    EventName.AUDIO_DELTA.value: AudioDeltaEvent,
    EventName.AUDIO_END.value: AudioEndEvent,
}
