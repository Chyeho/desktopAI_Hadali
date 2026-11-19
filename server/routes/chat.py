'''对话路由：POST /v1/chat（SSE）与 POST /v1/interrupt'''
import asyncio
import time
import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from core.tracing import TurnTracer
from protocol.events import (
    BaseEvent,
    EmotionEvent,
    ErrorCode,
    ErrorEvent,
    EventName,
    StateEvent,
    StateValue,
    TextDeltaEvent,
    TextDoneEvent,
    ToolCallEvent,
    ToolResultEvent,
    TurnEndEvent,
    TurnStartEvent,
)
from protocol.requests import ChatRequest, InterruptRequest
from server.security import verify_token
from server.services import Services, get_services

router = APIRouter(prefix="/v1", dependencies=[Depends(verify_token)])

SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


def _format_sse(event_name: str, event: BaseEvent) -> str:
    return f"event: {event_name}\ndata: {event.model_dump_json()}\n\n"


def _map_error(exc: Exception) -> str:
    '''异常 → 协议错误码'''
    name = type(exc).__name__.lower()
    if isinstance(exc, TimeoutError) or "timeout" in name:
        return ErrorCode.LLM_TIMEOUT.value
    if isinstance(exc, ValueError):
        return ErrorCode.BAD_REQUEST.value
    if "connection" in name or "connect" in name:
        return ErrorCode.LLM_ERROR.value
    return ErrorCode.INTERNAL.value


@router.post("/chat")
async def chat(req: ChatRequest, services: Services = Depends(get_services)):
    '''一轮对话：以 SSE 事件流返回思考状态、回复、情感、工具调用与指标'''
    turn_id = uuid.uuid4().hex
    mode = req.mode or services.current_mode
    seq = 0
    started = time.perf_counter()
    first_event_ms = None   # 请求进入 → 首个事件写出（由事件循环调度决定）

    def emit(event_name: EventName, model: type[BaseEvent], **fields) -> str:
        nonlocal seq, first_event_ms
        seq += 1
        if first_event_ms is None:
            first_event_ms = round((time.perf_counter() - started) * 1000, 3)
        event = model(seq=seq, turn_id=turn_id, ts=int(time.time() * 1000), **fields)
        return _format_sse(event_name.value, event)

    async def event_stream():
        tracer = TurnTracer(
            turn_id,
            req.session_id,
            mode=mode,
            user_text=req.text,
            turns_file=getattr(services, "turns_file", None),
        )
        try:
            yield emit(EventName.TURN_START, TurnStartEvent, mode=mode)
            yield emit(EventName.STATE, StateEvent, value=StateValue.THINKING)
            # Agent 仍是同步阻塞实现：放到工作线程执行，避免卡住事件循环
            async with services.lock(req.session_id):
                result = await asyncio.to_thread(
                    services.chat, req.session_id, req.text, req.mode
                )
            yield emit(EventName.STATE, StateEvent, value=StateValue.SPEAKING)
            yield emit(EventName.TEXT_DELTA, TextDeltaEvent, text=result["reply"])
            yield emit(EventName.TEXT_DONE, TextDoneEvent, text=result["reply"])
            yield emit(EventName.EMOTION, EmotionEvent, name=result["emotion"])
            # 本期在 agent 完成后补发工具事件（不改进 agent 主循环，见执行文档 6.5）
            for tc in result.get("tool_calls", []):
                yield emit(
                    EventName.TOOL_CALL,
                    ToolCallEvent,
                    name=tc["name"],
                    args=tc.get("args", {}),
                )
                yield emit(
                    EventName.TOOL_RESULT,
                    ToolResultEvent,
                    name=tc["name"],
                    ok=tc.get("ok", False),
                    duration_ms=tc.get("duration_ms", 0.0),
                )
            yield emit(
                EventName.TURN_END,
                TurnEndEvent,
                reply=result["reply"],
                emotion=result["emotion"],
                latency_ms=result.get("latency_ms", 0.0),
                first_event_ms=first_event_ms or 0.0,
            )
            tracer.finish_success(result)
        except Exception as exc:
            code = _map_error(exc)
            yield emit(
                EventName.ERROR,
                ErrorEvent,
                code=code,
                message=str(exc),
                retryable=code != ErrorCode.BAD_REQUEST.value,
            )
            tracer.finish_error(code, str(exc))
        # 成功与失败都收敛到 idle，保证客户端可恢复输入
        yield emit(EventName.STATE, StateEvent, value=StateValue.IDLE)

    return StreamingResponse(
        event_stream(), media_type="text/event-stream", headers=SSE_HEADERS
    )


@router.post("/interrupt")
async def interrupt(req: InterruptRequest):
    '''打断为尽力而为：client 侧停止 TTS/表情并丢弃后续事件

    server 内 agent 是同步阻塞调用，无法安全强杀工作线程；这里只做确认。
    '''
    return {"ok": True}
