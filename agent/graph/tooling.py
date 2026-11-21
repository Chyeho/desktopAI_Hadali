'''图引擎的工具装配

- 通用工具：天气、搜索，从 ToolManager 注册表取对象（时间能力已迁至 utils，不在注册表）
- MCP 工具：P7 接入，本阶段为空
- 工具分组：general 默认挂载；office 预留给“办公按需加载”，本阶段为空
'''
from langchain_core.tools import BaseTool

from agent.tool_manager import ToolManager
from utils.logger_handler import logger

# 通用工具白名单（名称与 tools/ 下 @tool 函数名一致）
BASE_TOOL_NAMES = ("get_weather", "web_search")
# 已迁出的时间工具名：若后续误注册，构造时剔除
TIME_TOOL_NAME = "get_current_time"
# 办公工具组（预留，后续按需挂载文件/表格等轻量工具）
OFFICE_TOOLS: list[BaseTool] = []
# 命中这些关键词时才考虑挂载 office 工具组
OFFICE_KEYWORDS = ("文档", "表格", "excel", "word", "ppt", "文件", "整理", "报告", "周报")

_agent_tools: list[BaseTool] | None = None


def _sanitize_tools(tools: list[BaseTool]) -> list[BaseTool]:
    '''防御性校验：剔除已被迁出的时间工具'''
    kept: list[BaseTool] = []
    for tool in tools:
        if tool.name == TIME_TOOL_NAME:
            logger.warning(f"[graph.tooling]检测到已迁出的时间工具 {TIME_TOOL_NAME}，已剔除")
            continue
        kept.append(tool)
    return kept


def get_agent_tools() -> list[BaseTool]:
    '''返回 agent 可用的通用工具列表（惰性构建并缓存）'''
    global _agent_tools
    if _agent_tools is None:
        tools = ToolManager().get_tools(list(BASE_TOOL_NAMES))
        _agent_tools = _sanitize_tools(tools)
        logger.info(f"[graph.tooling]agent_tools：{[t.name for t in _agent_tools]}")
    return list(_agent_tools)


def select_tools_for(text: str, tools: list[BaseTool] | None = None) -> list[BaseTool]:
    '''按用户文本选择本轮可用工具

    本阶段 office 组为空，行为等价于 general；后续 office 工具就绪后，
    命中办公关键词会追加挂载。
    '''
    selected = list(get_agent_tools() if tools is None else tools)
    lowered = (text or "").lower()
    if any(keyword in lowered for keyword in OFFICE_KEYWORDS):
        selected.extend(OFFICE_TOOLS)
    return selected
