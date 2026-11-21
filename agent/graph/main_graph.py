'''情感陪伴主图

拓扑（P2）：
    START → perception_gate → agent ⇄ tools → END

P5 再把 game 路由指向游戏子图。
'''
from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from agent.graph.agent_node import AgentNode
from agent.graph.perception import perception_node
from agent.graph.state import AgentState
from agent.graph.tooling import get_agent_tools
from utils.time_utils import DEFAULT_TIME_FORMAT


def route_after_perception(state: AgentState) -> str:
    '''感知门控后的条件边：返回 chat / game'''
    return state.get("route") or "chat"


def build_main_graph(llm: Any, system_prompt: str | None = None,
                     tools: list | None = None,
                     time_format: str = DEFAULT_TIME_FORMAT):
    '''构建并编译陪伴主图

    参数：
        llm          : 已配置好的聊天模型（支持 bind_tools / invoke，可选 stream）
        system_prompt: 可选，覆盖默认提示词文件
        tools        : 可选，覆盖默认 agent_tools（测试注入用）
        time_format  : AI 回复时间后缀格式
    '''
    agent_tools = get_agent_tools() if tools is None else list(tools)

    builder = StateGraph(AgentState)

    builder.add_node("perception_gate", perception_node)
    builder.add_node("agent", AgentNode(llm, system_prompt, agent_tools, time_format))
    # 工具异常由 ToolNode 转 ToolMessage，不中断图
    builder.add_node("tools", ToolNode(agent_tools, handle_tool_errors=True))

    builder.add_edge(START, "perception_gate")
    # P2 游戏子图尚未实现，game 暂时也交给 agent 回复
    builder.add_conditional_edges(
        "perception_gate",
        route_after_perception,
        {"chat": "agent", "game": "agent"},
    )
    # 有 tool_calls → tools → agent；无 tool_calls → END
    builder.add_conditional_edges("agent", tools_condition, {"tools": "tools", END: END})
    builder.add_edge("tools", "agent")

    return builder.compile()
