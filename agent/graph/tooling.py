'''图引擎的工具装配

- 通用工具：天气、搜索，从 ToolManager 注册表取对象（时间能力已迁至 utils，不在注册表）
- MCP 工具：按 config/mcp_servers.json 可选加载，未配置/异常/超时一律降级为空
- 工具分组：general 默认挂载；office 预留给“办公按需加载”，本阶段为空
'''
import asyncio
import json
import os
import threading
from typing import Any

from langchain_core.tools import BaseTool

from agent.tool_manager import ToolManager
from utils.logger_handler import logger
from utils.path_tool import get_abs_path

try:
    from langchain_mcp_adapters.client import MultiServerMCPClient
except Exception:  # 适配器缺失时不阻断启动，MCP 直接降级
    MultiServerMCPClient = None

# 通用工具白名单（名称与 tools/ 下 @tool 函数名一致）
BASE_TOOL_NAMES = ("get_weather", "web_search")
# 已迁出的时间工具名：若后续误注册，构造时剔除
TIME_TOOL_NAME = "get_current_time"
# 办公工具组（预留，后续按需挂载文件/表格等轻量工具）
OFFICE_TOOLS: list[BaseTool] = []
# 命中这些关键词时才考虑挂载 office 工具组
OFFICE_KEYWORDS = ("文档", "表格", "excel", "word", "ppt", "文件", "整理", "报告", "周报")

# MCP 配置：环境变量可覆盖默认路径；真实配置不入库，示例见 config/mcp_servers.example.json
MCP_CONFIG_ENV = "MCP_CONFIG_PATH"
DEFAULT_MCP_CONFIG_PATH = "config/mcp_servers.json"
MCP_LOAD_TIMEOUT = 10.0

_agent_tools: list[BaseTool] | None = None


def mcp_config_path() -> str:
    '''MCP 配置文件绝对路径：MCP_CONFIG_PATH > config/mcp_servers.json'''
    raw = os.getenv(MCP_CONFIG_ENV) or DEFAULT_MCP_CONFIG_PATH
    return raw if os.path.isabs(raw) else get_abs_path(raw)


def _read_mcp_connections(path: str) -> dict:
    '''解析 MCP 配置：兼容 {"mcpServers": {...}} 与直接 connections 两种写法'''
    with open(path, "r", encoding="utf-8") as f:
        config = json.load(f)
    if not isinstance(config, dict):
        raise ValueError("根节点必须是 JSON 对象")
    connections = config.get("mcpServers", config)
    if not isinstance(connections, dict):
        raise ValueError("mcpServers 必须是 JSON 对象")
    return connections


def _run_coro(coro_factory, timeout: float) -> list[BaseTool]:
    '''在独立线程跑异步加载：避免调用方已有事件循环时 asyncio.run 报错'''
    box: dict[str, Any] = {}

    def worker():
        try:
            box["result"] = asyncio.run(coro_factory())
        except BaseException as exc:  # 异常需回传调用线程
            box["error"] = exc

    thread = threading.Thread(target=worker, name="mcp-load", daemon=True)
    thread.start()
    thread.join(timeout)
    if thread.is_alive():
        raise TimeoutError(f"MCP 工具加载超时（{timeout}s）")
    if "error" in box:
        raise box["error"]
    return box.get("result") or []


def load_mcp_tools(config_path: str = None, timeout: float = None) -> list[BaseTool]:
    '''加载 MCP 工具（可选能力）

    任何失败都只告警并返回空列表，保证未配置 MCP 时正常启动。
    '''
    if MultiServerMCPClient is None:
        logger.warning("[graph.tooling]未安装 langchain-mcp-adapters，跳过 MCP 工具")
        return []

    path = config_path or mcp_config_path()
    if not os.path.exists(path):
        logger.info(f"[graph.tooling]未配置 MCP（{path}），跳过")
        return []

    try:
        connections = _read_mcp_connections(path)
    except Exception as e:
        logger.warning(f"[graph.tooling]MCP 配置读取失败：{str(e)}，已跳过")
        return []
    if not connections:
        logger.warning(f"[graph.tooling]MCP 配置为空（{path}），跳过")
        return []

    try:
        client = MultiServerMCPClient(connections, tool_name_prefix=True)
        tools = _run_coro(client.get_tools, timeout or MCP_LOAD_TIMEOUT)
    except Exception as e:
        logger.warning(f"[graph.tooling]MCP 工具加载失败：{str(e)}，已跳过")
        return []

    logger.info(f"[graph.tooling]MCP 工具：{[t.name for t in tools]}")
    return list(tools)


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
        tools.extend(load_mcp_tools())
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
