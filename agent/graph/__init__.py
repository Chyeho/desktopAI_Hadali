'''LangGraph 情感陪伴主图

对外入口：
- CompanionGraphAgent（runner.py）：对 server/core 提供与 ChatAgent 相同的最小接口
- build_main_graph（main_graph.py）：构建并编译主图
'''
from agent.graph.runner import CompanionGraphAgent
from agent.graph.main_graph import build_main_graph

__all__ = ["CompanionGraphAgent", "build_main_graph"]
