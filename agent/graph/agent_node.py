'''陪伴主图的 agent 节点

P1 阶段只生成纯文本回复（暂不绑定工具）；
P2 接入工具循环，P3 接入情绪标签与时间后缀。
'''
from typing import Any

from langchain_core.messages import BaseMessage, SystemMessage

from agent.graph.state import AgentState
from utils.logger_handler import logger
from utils.prompt_loader import load_prompt

# 陪伴主图专用提示词（与 legacy 的严格 JSON 提示词区分）
GRAPH_PROMPT_PATH = "prompts/graph_companion_prompt.txt"


def load_graph_prompt(path: str = GRAPH_PROMPT_PATH) -> str:
    '''加载陪伴主图提示词；失败时返回空串，不阻断对话'''
    try:
        return load_prompt(path)
    except Exception as e:
        logger.warning(f"[graph.agent]系统提示词加载失败（{path}）：{str(e)}")
        return ""


class AgentNode:
    '''陪伴 agent 节点：注入系统提示词后调用模型'''

    def __init__(self, llm: Any, system_prompt: str | None = None):
        self.llm = llm
        self.system_prompt = load_graph_prompt() if system_prompt is None else system_prompt

    def __call__(self, state: AgentState) -> dict:
        messages: list[BaseMessage] = list(state.get("messages") or [])
        if self.system_prompt:
            # 系统提示词每轮临时拼入，不写入 state，避免污染持久化的对话历史
            messages = [SystemMessage(content=self.system_prompt), *messages]

        ai_message = self.llm.invoke(messages)
        logger.info(f"[graph.agent]模型调用完成，当前消息数：{len(messages)}")
        return {"messages": [ai_message]}
