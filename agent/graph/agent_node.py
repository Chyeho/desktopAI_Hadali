'''陪伴主图的 agent 节点

- 每轮按用户文本选择工具（select_tools_for），bind_tools 后调用模型；
- 模型请求工具时原样返回 AIMessage（由 ToolNode 执行），否则视为最终回复；
- 情绪标签解析与时间后缀在 P3 接入。
'''
from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from agent.graph.state import AgentState
from agent.graph.tooling import get_agent_tools, select_tools_for
from utils.logger_handler import logger
from utils.prompt_loader import load_prompt
from utils.time_utils import strip_user_time

# 陪伴主图专用提示词（与 legacy 的严格 JSON 提示词区分）
GRAPH_PROMPT_PATH = "prompts/graph_companion_prompt.txt"


def load_graph_prompt(path: str = GRAPH_PROMPT_PATH) -> str:
    '''加载陪伴主图提示词；失败时返回空串，不阻断对话'''
    try:
        return load_prompt(path)
    except Exception as e:
        logger.warning(f"[graph.agent]系统提示词加载失败（{path}）：{str(e)}")
        return ""


def _last_user_text(messages: list[BaseMessage]) -> str:
    '''取最近一条用户消息文本（剥离时间前缀），用于工具分组'''
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            content = message.content if isinstance(message.content, str) else str(message.content)
            return strip_user_time(content)
    return ""


class AgentNode:
    '''陪伴 agent 节点：注入系统提示词、绑定工具并调用模型'''

    def __init__(self, llm: Any, system_prompt: str | None = None,
                 tools: list | None = None):
        self.llm = llm
        self.system_prompt = load_graph_prompt() if system_prompt is None else system_prompt
        self.tools = get_agent_tools() if tools is None else list(tools)

    def __call__(self, state: AgentState) -> dict:
        messages: list[BaseMessage] = list(state.get("messages") or [])
        if self.system_prompt:
            # 系统提示词每轮临时拼入，不写入 state，避免污染持久化的对话历史
            messages = [SystemMessage(content=self.system_prompt), *messages]

        tools = select_tools_for(_last_user_text(messages), self.tools)
        llm_with_tools = self.llm.bind_tools(tools) if tools else self.llm
        ai_message = llm_with_tools.invoke(messages)

        logger.info(
            f"[graph.agent]模型调用完成，工具：{[t.name for t in tools]}，"
            f"请求工具：{bool(getattr(ai_message, 'tool_calls', None))}"
        )
        return {"messages": [ai_message]}
