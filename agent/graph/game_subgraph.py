'''游戏占位子图：真正的 StateGraph，后续可把 game_notice 原地替换为真实五子棋

    START → game_notice → END

子图与主图共享 AgentState 与主图 checkpointer，不单独建命名空间。
'''
from typing import Any

from langchain_core.messages import BaseMessage, SystemMessage
from langgraph.graph import END, START, StateGraph

from agent.graph.agent_node import finalize_reply, invoke_llm, to_ai_message
from agent.graph.state import AgentState
from utils.time_utils import DEFAULT_TIME_FORMAT

# 游戏占位节点的系统提示词：不承诺实现，只做陪伴式说明
GAME_NOTICE_PROMPT = '''你是情感陪伴 AI 助手哈达莉。用户想和你玩一局游戏，但游戏功能还在开发中。
请用温柔、口语化的语气回应，说明游戏还在准备中，可以先陪用户聊聊天。
回复格式：第一行输出 [emotion:标签]（标签从 neutral、happy、sad、angry、surprised、shy、worried、excited、thinking、relaxed 中选择），
第二行开始输出正文；正文不超过 60 字，不要输出其他格式标记。'''


class GameNoticeNode:
    '''游戏占位节点：生成一句“游戏开发中”的陪伴式回应'''

    def __init__(self, llm: Any, time_format: str = DEFAULT_TIME_FORMAT):
        self.llm = llm
        self.time_format = time_format

    def __call__(self, state: AgentState) -> dict:
        messages: list[BaseMessage] = [
            SystemMessage(content=GAME_NOTICE_PROMPT),
            *list(state.get("messages") or []),
        ]
        ai_message = to_ai_message(invoke_llm(self.llm, messages))
        return {"messages": [finalize_reply(ai_message, self.time_format)]}


def build_game_subgraph(llm: Any, time_format: str = DEFAULT_TIME_FORMAT):
    '''构建游戏占位子图（不单独挂 checkpointer，由主图共享）'''
    builder = StateGraph(AgentState)
    builder.add_node("game_notice", GameNoticeNode(llm, time_format))
    builder.add_edge(START, "game_notice")
    builder.add_edge("game_notice", END)
    return builder.compile()
