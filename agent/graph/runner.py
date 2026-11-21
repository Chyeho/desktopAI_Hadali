'''陪伴主图运行时：对 server/core 暴露与 ChatAgent 相同的最小接口

- chat()       : 一次性返回 TurnResult（内部仍会完整执行图）
- stream_chat(): 逐 token 产出 ("delta", 文本)，结束时产出 ("done", TurnResult)
- 时间注入    : 用户消息加前缀、AI 回复加后缀；对 UI 暴露的 reply 为干净文本
- 多轮上下文  : MemorySaver + thread_id=session_id；JSON 历史镜像用于重启恢复
'''
import os
import time
from typing import Any, Iterator

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from agent.chat_agent import HistoryStore, TurnResult
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
                 graph: Any = None, time_format: str | None = None,
                 history_file: str | None = None):
        self.time_format = time_format or os.getenv("GRAPH_TIME_FORMAT") or DEFAULT_TIME_FORMAT
        self.graph = graph or build_main_graph(llm, system_prompt, time_format=self.time_format)
        # JSON 历史镜像：用于进程重启后恢复；为空时纯内存运行
        self.history = HistoryStore(file_path=history_file) if history_file else None
        # 当前线程的消息镜像（与 checkpointer 内容保持一致，便于调试与统计）
        self.messages: list[BaseMessage] = []
        # 已完成历史注入的 thread_id，避免重复注入
        self._restored_threads: set[str] = set()

    def set_mode(self, mode_name: str) -> None:
        '''单模式引擎：保留接口兼容，切换请求只记录日志'''
        logger.info(f"[graph.runner]单模式引擎，忽略模式切换请求：{mode_name}")

    @staticmethod
    def _config(session_id: str) -> dict:
        '''LangGraph 运行配置：thread_id 即会话 ID'''
        return {"configurable": {"thread_id": session_id}}

    def _prepare_turn(self, session_id: str, user_input: str) -> tuple[dict, int]:
        '''构造本轮输入状态：首次注入 JSON 历史，用户消息加时间前缀

        返回 (state, base_len)；base_len 用于从最终消息列表中切出本轮新增消息。
        '''
        prior: list[BaseMessage] = []
        if session_id not in self._restored_threads:
            self._restored_threads.add(session_id)
            if self.history is not None:
                prior = [
                    m for m in self.history.messages if not isinstance(m, SystemMessage)
                ]
            self.messages = list(prior)
            if prior:
                logger.info(f"[graph.runner]会话 {session_id} 从 JSON 恢复 {len(prior)} 条历史")

        human = HumanMessage(content=with_user_time(user_input, fmt=self.time_format))
        base_len = len(self.messages) + 1
        state = {
            "messages": [*prior, human],
            "route": "chat",
            "game_request": None,
        }
        return state, base_len

    def _mirror_history(self, messages: list[BaseMessage]) -> None:
        '''把图状态镜像到 JSON 文件（裁剪由 HistoryStore 负责）'''
        self.messages = list(messages)
        if self.history is None:
            return
        try:
            self.history.replace(self.messages)
        except Exception as e:
            logger.error(f"[graph.runner]历史镜像写入失败：{str(e)}")

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
        state, base_len = self._prepare_turn(session_id, user_input)

        result = self.graph.invoke(state, self._config(session_id))
        all_messages = list(result.get("messages") or self.messages)
        new_messages = all_messages[base_len:]
        self._mirror_history(all_messages)

        return self._build_result(all_messages, new_messages, started_at)

    def stream_chat(self, user_input: str,
                    session_id: str = "default") -> Iterator[tuple[str, Any]]:
        '''流式处理一轮用户输入

        产出：
            ("delta", str)        : 已过滤情绪标签的增量文本
            ("done", TurnResult)  : 本轮最终结果（reply 不含时间戳）
        '''
        started_at = time.perf_counter()
        state, base_len = self._prepare_turn(session_id, user_input)
        config = self._config(session_id)

        filter_ = EmotionStreamFilter()
        final_state: dict | None = None

        for mode, payload in self.graph.stream(
            state, config, stream_mode=["messages", "values"]
        ):
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
            final_state = self.graph.invoke(state, config)

        all_messages = list(final_state.get("messages") or self.messages)
        new_messages = all_messages[base_len:]
        self._mirror_history(all_messages)
        yield ("done", self._build_result(all_messages, new_messages, started_at))
