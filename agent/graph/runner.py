'''陪伴主图运行时：对 server/core 暴露与 ChatAgent 相同的最小接口'''
import time
from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage

from agent.chat_agent import TurnResult
from agent.graph.main_graph import build_main_graph
from utils.logger_handler import logger


class CompanionGraphAgent:
    '''LangGraph 陪伴引擎

    与 ChatAgent 的差异：
    - 不做模式路由，mode_config 固定为 emotion；
    - 输出契约后续切换为「情绪标签前缀 + 纯文本」，本阶段 emotion 固定 neutral。
    '''

    mode_config = {"name": "emotion", "display_name": "情感陪伴"}

    def __init__(self, llm: Any = None, system_prompt: str | None = None,
                 graph: Any = None):
        self.graph = graph or build_main_graph(llm, system_prompt)
        # P1/P2 尚未接 checkpointer，先由 runner 持有消息列表；P4 改为 MemorySaver
        self.messages: list[BaseMessage] = []

    def set_mode(self, mode_name: str) -> None:
        '''单模式引擎：保留接口兼容，切换请求只记录日志'''
        logger.info(f"[graph.runner]单模式引擎，忽略模式切换请求：{mode_name}")

    def chat(self, user_input: str, session_id: str = "default") -> TurnResult:
        '''处理一轮用户输入，返回结构化回合结果'''
        started_at = time.perf_counter()

        self.messages.append(HumanMessage(content=user_input))
        state = {
            "messages": list(self.messages),
            "route": "chat",
            "game_request": None,
        }
        result = self.graph.invoke(state)
        self.messages = list(result.get("messages") or self.messages)

        last = self.messages[-1] if self.messages else None
        content = getattr(last, "content", "") if last is not None else ""
        reply = content if isinstance(content, str) else str(content)

        return {
            "emotion": "neutral",
            "reply": reply,
            "mode": self.mode_config["name"],
            "steps": 1,
            "tool_calls": [],
            "latency_ms": round((time.perf_counter() - started_at) * 1000, 2),
        }
