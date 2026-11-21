'''陪伴主图运行时：对 server/core 暴露与 ChatAgent 相同的最小接口

- chat()       : 一次性返回 TurnResult（内部仍会完整执行图）
- stream_chat(): 逐 token 产出 ("delta", 文本)，结束时产出 ("done", TurnResult)
- 时间注入    : 用户消息加前缀、AI 回复加后缀；对 UI 暴露的 reply 为干净文本
'''
import os
import time
from typing import Any, Iterator

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage

from agent.chat_agent import TurnResult
from agent.graph.emotion import EmotionStreamFilter, parse_emotion_tag
from agent.graph.main_graph import build_main_graph
from utils.logger_handler import logger
from utils.time_utils import DEFAULT_TIME_FORMAT, strip_reply_time, with_user_time


def _collect_turn_metrics(new_messages: list[BaseMessage]) -> dict:
    '''从本轮新增消息中统计模型调用轮数与工具调用记录'''
    steps = sum(1 for m in new_messages if isinstance(m, AIMessage))
    tool_messages = {
        getattr(m, "tool_call_id", None): m for m in new_messages if isinstance(m, ToolMessage)
    }
    records = []
    for message in new_messages:
        if not isinstance(message, AIMessage):
            continue
        for call in getattr(message, "tool_calls", None) or []:
            tool_message = tool_messages.get(call.get("id"))
            records.append({
                "name": call.get("name", ""),
                "args": call.get("args", {}) or {},
                "ok": getattr(tool_message, "status", None) != "error",
                "duration_ms": 0.0,
            })
    return {"steps": max(steps, 1), "tool_calls": records}


class CompanionGraphAgent:
    '''LangGraph 陪伴引擎

    与 ChatAgent 的差异：
    - 不做模式路由，mode_config 固定为 emotion；
    - 输出契约为「情绪标签前缀 + 纯文本」，标签解析后剥离。
    '''

    mode_config = {"name": "emotion", "display_name": "情感陪伴"}

    def __init__(self, llm: Any = None, system_prompt: str | None = None,
                 graph: Any = None, time_format: str | None = None):
        self.time_format = time_format or os.getenv("GRAPH_TIME_FORMAT") or DEFAULT_TIME_FORMAT
        self.graph = graph or build_main_graph(llm, system_prompt, time_format=self.time_format)
        # P2 尚未接 checkpointer，先由 runner 持有消息列表；P4 改为 MemorySaver
        self.messages: list[BaseMessage] = []

    def set_mode(self, mode_name: str) -> None:
        '''单模式引擎：保留接口兼容，切换请求只记录日志'''
        logger.info(f"[graph.runner]单模式引擎，忽略模式切换请求：{mode_name}")

    def _build_state(self, user_input: str) -> dict:
        '''构造本轮输入状态：用户消息加时间前缀'''
        self.messages.append(
            HumanMessage(content=with_user_time(user_input, fmt=self.time_format))
        )
        return {
            "messages": list(self.messages),
            "route": "chat",
            "game_request": None,
        }

    def _build_result(self, messages: list[BaseMessage], new_messages: list[BaseMessage],
                      started_at: float) -> TurnResult:
        '''把图执行结果转换为 TurnResult（reply 剥离时间后缀）'''
        last = messages[-1] if messages else None
        content = getattr(last, "content", "") if last is not None else ""
        content = content if isinstance(content, str) else str(content)
        emotion = (getattr(last, "additional_kwargs", None) or {}).get("emotion")
        if not emotion:
            emotion, _ = parse_emotion_tag(content)
        metrics = _collect_turn_metrics(new_messages)

        return {
            "emotion": emotion,
            "reply": strip_reply_time(content),
            "mode": self.mode_config["name"],
            "steps": metrics["steps"],
            "tool_calls": metrics["tool_calls"],
            "latency_ms": round((time.perf_counter() - started_at) * 1000, 2),
        }

    def chat(self, user_input: str, session_id: str = "default") -> TurnResult:
        '''处理一轮用户输入，返回结构化回合结果'''
        started_at = time.perf_counter()
        base_len = len(self.messages)
        state = self._build_state(user_input)

        result = self.graph.invoke(state)
        all_messages = list(result.get("messages") or self.messages)
        new_messages = all_messages[base_len:]
        self.messages = all_messages

        return self._build_result(all_messages, new_messages, started_at)

    def stream_chat(self, user_input: str,
                    session_id: str = "default") -> Iterator[tuple[str, Any]]:
        '''流式处理一轮用户输入

        产出：
            ("delta", str)        : 已过滤情绪标签的增量文本
            ("done", TurnResult)  : 本轮最终结果（reply 不含时间戳）
        '''
        started_at = time.perf_counter()
        base_len = len(self.messages)
        state = self._build_state(user_input)

        filter_ = EmotionStreamFilter()
        final_state: dict | None = None

        for mode, payload in self.graph.stream(state, stream_mode=["messages", "values"]):
            if mode == "messages":
                chunk, metadata = payload
                # 只转发 agent 节点的模型 token，避免把系统提示词等内部消息暴露给 UI
                if metadata.get("langgraph_node") != "agent":
                    continue
                content = chunk.content if isinstance(chunk.content, str) else ""
                delta = filter_.feed(content)
                if delta:
                    yield ("delta", delta)
            elif mode == "values":
                final_state = payload

        tail = filter_.flush()
        if tail:
            yield ("delta", tail)

        if final_state is None:
            logger.warning("[graph.runner]流式未拿到最终状态，回落一次性 invoke")
            final_state = self.graph.invoke(state)

        all_messages = list(final_state.get("messages") or self.messages)
        new_messages = all_messages[base_len:]
        self.messages = all_messages
        yield ("done", self._build_result(all_messages, new_messages, started_at))
