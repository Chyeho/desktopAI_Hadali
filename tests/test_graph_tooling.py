"""单元测试：图引擎工具装配 agent/graph/tooling.py"""
from langchain_core.tools import tool

from agent.graph.tooling import (
    BASE_TOOL_NAMES,
    OFFICE_TOOLS,
    _sanitize_tools,
    get_agent_tools,
    select_tools_for,
)


@tool("get_current_time")
def _fake_time() -> str:
    """假的时间工具，用于验证防御性剔除"""
    return "12:00"


@tool
def _fake_office() -> str:
    """假的办公工具，用于验证按需分组"""
    return "ok"


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
