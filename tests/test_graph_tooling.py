"""单元测试：图引擎工具装配 agent/graph/tooling.py"""
import asyncio
import json

import pytest
from langchain_core.tools import tool

from agent.graph import tooling
from agent.graph.tooling import (
    BASE_TOOL_NAMES,
    OFFICE_TOOLS,
    _read_mcp_connections,
    _sanitize_tools,
    get_agent_tools,
    load_mcp_tools,
    mcp_config_path,
    select_tools_for,
)


@pytest.fixture(autouse=True)
def _reset_tool_cache(monkeypatch, tmp_path):
    """每个用例前后清空缓存，并把 MCP 配置指向不存在的文件，保证离线隔离"""
    monkeypatch.setenv(tooling.MCP_CONFIG_ENV, str(tmp_path / "absent.json"))
    tooling._agent_tools = None
    yield
    tooling._agent_tools = None


@tool("get_current_time")
def _fake_time() -> str:
    """假的时间工具，用于验证防御性剔除"""
    return "12:00"


@tool
def _fake_office() -> str:
    """假的办公工具，用于验证按需分组"""
    return "ok"


@tool("mcp_calc")
def _fake_mcp() -> str:
    """假的 MCP 工具，用于验证合并"""
    return "ok"


@tool("mcp_async_add")
async def _async_mcp_add(a: int, b: int) -> str:
    """异步 MCP 工具，用于验证同步包装"""
    return str(a + b)


class TestAgentTools:
    """默认工具列表"""

    def test_contains_weather_and_search(self):
        names = [t.name for t in get_agent_tools()]
        assert names == list(BASE_TOOL_NAMES)

    def test_no_time_tool(self):
        assert "get_current_time" not in [t.name for t in get_agent_tools()]

    def test_returns_copy(self):
        """调用方修改返回值不影响缓存"""
        tools = get_agent_tools()
        tools.clear()
        assert len(get_agent_tools()) == 2


class TestSanitizeTools:
    """防御性剔除已迁出的时间工具"""

    def test_time_tool_removed(self):
        kept = _sanitize_tools([_fake_time, _fake_office])
        assert [t.name for t in kept] == ["_fake_office"]


class TestSelectToolsFor:
    """按文本选择工具组"""

    def test_plain_chat_returns_general(self):
        assert len(select_tools_for("今天有点累")) == 2

    def test_office_keyword_appends_office_group(self):
        """本阶段 office 组为空，命中关键词也不改变工具数量"""
        assert OFFICE_TOOLS == []
        assert len(select_tools_for("帮我整理一份周报表格")) == 2

    def test_accepts_custom_tools(self):
        assert [t.name for t in select_tools_for("你好", [_fake_office])] == ["_fake_office"]


class _FakeMCPClient:
    """MCP 客户端桩：返回固定工具列表，记录连接与参数"""

    instances: list = []

    def __init__(self, connections, **kwargs):
        self.connections = connections
        self.kwargs = kwargs
        self.instances.append(self)

    async def get_tools(self, server_name=None):
        return [_fake_mcp]


class _BrokenMCPClient:
    """构造或加载即抛异常的 MCP 客户端桩"""

    def __init__(self, connections, **kwargs):
        raise RuntimeError("mcp boom")


def _write_config(tmp_path, payload) -> str:
    path = tmp_path / "mcp.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return str(path)


class TestMcpTools:
    """MCP 可选加载与降级"""

    def test_missing_config_returns_empty(self, tmp_path):
        assert load_mcp_tools(str(tmp_path / "nope.json")) == []

    def test_invalid_json_returns_empty(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text("{not-json", encoding="utf-8")
        assert load_mcp_tools(str(path)) == []

    def test_empty_servers_returns_empty(self, tmp_path):
        path = _write_config(tmp_path, {"mcpServers": {}})
        assert load_mcp_tools(path) == []

    def test_merges_mcp_tools_into_agent_tools(self, monkeypatch, tmp_path):
        path = _write_config(tmp_path, {
            "mcpServers": {"calc": {"transport": "stdio", "command": "python"}}
        })
        monkeypatch.setenv(tooling.MCP_CONFIG_ENV, path)
        monkeypatch.setattr(tooling, "MultiServerMCPClient", _FakeMCPClient)
        _FakeMCPClient.instances.clear()

        names = [t.name for t in get_agent_tools()]

        assert names == [*BASE_TOOL_NAMES, "mcp_calc"]
        assert _FakeMCPClient.instances[-1].kwargs["tool_name_prefix"] is True

    def test_mcp_time_tool_sanitized(self, monkeypatch, tmp_path):
        path = _write_config(tmp_path, {"mcpServers": {"t": {"transport": "stdio"}}})

        class _TimeClient:
            def __init__(self, connections, **kwargs):
                pass

            async def get_tools(self, server_name=None):
                return [_fake_time]

        monkeypatch.setenv(tooling.MCP_CONFIG_ENV, path)
        monkeypatch.setattr(tooling, "MultiServerMCPClient", _TimeClient)

        assert [t.name for t in get_agent_tools()] == list(BASE_TOOL_NAMES)

    def test_client_failure_degrades(self, monkeypatch, tmp_path):
        path = _write_config(tmp_path, {"mcpServers": {"x": {"transport": "stdio"}}})
        monkeypatch.setenv(tooling.MCP_CONFIG_ENV, path)
        monkeypatch.setattr(tooling, "MultiServerMCPClient", _BrokenMCPClient)

        assert load_mcp_tools(path) == []
        assert [t.name for t in get_agent_tools()] == list(BASE_TOOL_NAMES)

    def test_missing_adapter_degrades(self, monkeypatch, tmp_path):
        path = _write_config(tmp_path, {"mcpServers": {"x": {"transport": "stdio"}}})
        monkeypatch.setattr(tooling, "MultiServerMCPClient", None)
        assert load_mcp_tools(path) == []

    def test_read_connections_accepts_plain_dict(self, tmp_path):
        path = _write_config(tmp_path, {"calc": {"transport": "stdio"}})
        assert _read_mcp_connections(path) == {"calc": {"transport": "stdio"}}

    def test_read_connections_supports_bom(self, tmp_path):
        """PowerShell / 记事本保存的 UTF-8 BOM 配置也能读取"""
        path = tmp_path / "bom.json"
        path.write_text(
            json.dumps({"mcpServers": {"calc": {"transport": "stdio"}}}),
            encoding="utf-8-sig",
        )
        assert _read_mcp_connections(str(path)) == {"calc": {"transport": "stdio"}}

    def test_async_mcp_tool_is_sync_callable(self, monkeypatch, tmp_path):
        """MCP 适配器返回 async-only 工具，加载后必须能被同步 ToolNode 调用"""
        path = _write_config(tmp_path, {"mcpServers": {"demo": {"transport": "stdio"}}})

        class _AsyncClient:
            def __init__(self, connections, **kwargs):
                pass

            async def get_tools(self, server_name=None):
                return [_async_mcp_add]

        monkeypatch.setattr(tooling, "MultiServerMCPClient", _AsyncClient)
        tools = load_mcp_tools(path)

        assert [t.name for t in tools] == ["mcp_async_add"]
        assert tools[0].invoke({"a": 2, "b": 3}) == "5"

    def test_partial_failure_keeps_healthy_servers(self, monkeypatch, tmp_path):
        """单个服务失败不影响其他服务（回归：TaskGroup 导致全量失败）"""
        path = _write_config(tmp_path, {"mcpServers": {
            "ok": {"transport": "stdio"},
            "bad": {"transport": "stdio"},
        }})

        class _MixedClient:
            def __init__(self, connections, **kwargs):
                pass

            async def get_tools(self, server_name=None):
                if server_name == "bad":
                    raise RuntimeError("spawn npx failed")
                return [_fake_mcp]

        monkeypatch.setattr(tooling, "MultiServerMCPClient", _MixedClient)
        tools = load_mcp_tools(path)

        assert [t.name for t in tools] == ["mcp_calc"]

    def test_describe_error_unwraps_exception_group(self):
        group = BaseExceptionGroup("boom", [RuntimeError("inner")])
        text = "\n".join(tooling._describe_error(group))
        assert "RuntimeError: inner" in text

    def test_timeout_env_override(self, monkeypatch):
        monkeypatch.setenv(tooling.MCP_TIMEOUT_ENV, "12.5")
        assert tooling._resolve_load_timeout() == 12.5
        monkeypatch.setenv(tooling.MCP_TIMEOUT_ENV, "abc")
        assert tooling._resolve_load_timeout() == tooling.MCP_LOAD_TIMEOUT

    def test_slow_server_times_out_without_failing_others(self, monkeypatch, tmp_path):
        """服务超时只跳过自身，其他服务仍可用"""
        path = _write_config(tmp_path, {"mcpServers": {
            "fast": {"transport": "stdio"},
            "slow": {"transport": "stdio"},
        }})

        class _SlowClient:
            def __init__(self, connections, **kwargs):
                pass

            async def get_tools(self, server_name=None):
                if server_name == "slow":
                    await asyncio.sleep(5)
                return [_fake_mcp]

        monkeypatch.setattr(tooling, "MultiServerMCPClient", _SlowClient)
        tools = load_mcp_tools(path, timeout=0.05)

        assert [t.name for t in tools] == ["mcp_calc"]

    def test_config_path_env_override(self, monkeypatch, tmp_path):
        target = tmp_path / "custom.json"
        monkeypatch.setenv(tooling.MCP_CONFIG_ENV, str(target))
        assert mcp_config_path() == str(target)

    def test_config_path_default_is_absolute(self, monkeypatch):
        monkeypatch.delenv(tooling.MCP_CONFIG_ENV, raising=False)
        assert mcp_config_path() == tooling.get_abs_path(tooling.DEFAULT_MCP_CONFIG_PATH)
