'''工具管理器：加载全部工具，根据 agent 模式的工具白名单过滤输出可用工具

- tools/common/ 下的公共工具在此注册，所有 agent 模式均可通过白名单调用；
- 后续各模式独有工具（如 tools/office/）也在全量注册表中登记，
  由各模式配置的 allowed_tools 白名单决定是否可用。
'''
from langchain_core.tools import BaseTool

from tools.common.get_time import get_current_time
from tools.common.weather import get_weather
from tools.common.web_search import web_search
from utils.logger_handler import logger

# 全量工具注册表：工具名（@tool 函数名）→ langchain BaseTool
# 后续新增工具时在此登记即可
ALL_TOOLS: dict[str, BaseTool] = {
    get_current_time.name: get_current_time,
    get_weather.name: get_weather,
    web_search.name: web_search,
}


class ToolManager:
    '''根据模式白名单提供可用工具'''

    def __init__(self):
        self._all_tools: dict[str, BaseTool] = dict(ALL_TOOLS)
        logger.info(f"[ToolManager]已注册工具：{list(self._all_tools.keys())}")

    def get_tools(self, allowed_tools: list[str]) -> list[BaseTool]:
        '''按白名单返回工具列表（用于 llm.bind_tools 绑定）'''
        tools = [self._all_tools[name] for name in allowed_tools if name in self._all_tools]
        missing = [name for name in allowed_tools if name not in self._all_tools]
        if missing:
            logger.warning(f"[ToolManager]白名单中存在未注册工具，已忽略：{missing}")
        return tools

    def get_tool_map(self, allowed_tools: list[str]) -> dict[str, BaseTool]:
        '''按白名单返回 {工具名: 工具对象}，用于工具调用循环中按名执行'''
        return {tool.name: tool for tool in self.get_tools(allowed_tools)}
