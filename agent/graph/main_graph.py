'''情感陪伴主图

拓扑（P1 最小骨架）：
    START → perception_gate → agent → END

P2 在 agent 与 END 之间接入 tools 循环，P5 把 game 路由指向游戏子图。
'''
from typing import Any

from langgraph.graph import END, START, StateGraph

from agent.graph.agent_node import AgentNode
from agent.graph.perception import perception_node
from agent.graph.state import AgentState


def route_after_perception(state: AgentState) -> str:
    '''感知门控后的条件边：返回 chat / game'''
    return state.get("route") or "chat"


def build_main_graph(llm: Any, system_prompt: str | None = None):
    '''构建并编译陪伴主图

    参数：
        llm          : 已配置好的聊天模型（支持 invoke）
        system_prompt: 可选，覆盖默认提示词文件
    '''
    builder = StateGraph(AgentState)

    builder.add_node("perception_gate", perception_node)
    builder.add_node("agent", AgentNode(llm, system_prompt))

    builder.add_edge(START, "perception_gate")
    # P1 游戏子图尚未实现，game 暂时也交给 agent 回复
    builder.add_conditional_edges(
        "perception_gate",
        route_after_perception,
        {"chat": "agent", "game": "agent"},
    )
    builder.add_edge("agent", END)

    return builder.compile()
