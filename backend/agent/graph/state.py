'''陪伴主图的共享状态定义

messages 使用 add_messages reducer：节点返回的新消息会追加到已有列表，
并支持按消息 id 原位更新（后续流式占位/重写场景可直接复用）。
'''
from typing import Annotated, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict, total=False):
    '''主图与游戏子图共享的状态'''

    # 对话消息（持续累积）
    messages: Annotated[list[AnyMessage], add_messages]
    # 感知门控结果：chat 走陪伴 agent，game 走游戏子图
    route: str
    # 游戏请求原文（进入游戏子图时使用）
    game_request: str | None
    # 以下字段仅占位，本阶段不写业务逻辑
    emotion_state: str | None
    task_brief: str | None
