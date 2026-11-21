"""单元测试：工具管理 agent/tool_manager.py

覆盖 ALL_TOOLS 注册表与 ToolManager 的白名单过滤逻辑。
"""
from agent.tool_manager import ALL_TOOLS, ToolManager


class TestAllTools:
    """ALL_TOOLS：全量工具注册表"""

    def test_registered_tools(self):
        """应注册天气与搜索两个公共工具"""
        assert "get_weather" in ALL_TOOLS
        assert "web_search" in ALL_TOOLS

    def test_time_tool_removed(self):
        """时间能力已迁至 utils/time_utils.py，不再作为工具注册"""
        assert "get_current_time" not in ALL_TOOLS

    def test_tool_count(self):
        assert len(ALL_TOOLS) == 2


class TestToolManagerGetTools:
    """ToolManager.get_tools：按白名单返回工具列表"""

    def setup_method(self):
        self.tm = ToolManager()

    def test_returns_all_whitelisted(self):
        tools = self.tm.get_tools(["get_weather", "web_search"])
        assert len(tools) == 2

    def test_partial_whitelist(self):
        tools = self.tm.get_tools(["get_weather"])
        assert len(tools) == 1
        assert tools[0].name == "get_weather"

    def test_empty_whitelist(self):
        tools = self.tm.get_tools([])
        assert tools == []

    def test_unknown_tool_ignored(self):
        """白名单中未注册的工具应被忽略，不抛异常"""
        tools = self.tm.get_tools(["get_weather", "nonexistent_tool"])
        assert len(tools) == 1
        assert tools[0].name == "get_weather"

    def test_all_unknown_returns_empty(self):
        tools = self.tm.get_tools(["foo", "bar"])
        assert tools == []


class TestToolManagerGetToolMap:
    """ToolManager.get_tool_map：返回 {工具名: 工具对象}"""

    def setup_method(self):
        self.tm = ToolManager()

    def test_returns_dict(self):
        tool_map = self.tm.get_tool_map(["get_weather", "web_search"])
        assert isinstance(tool_map, dict)
        assert "get_weather" in tool_map
        assert "web_search" in tool_map

    def test_keys_match_whitelist(self):
        tool_map = self.tm.get_tool_map(["web_search"])
        assert set(tool_map.keys()) == {"web_search"}

    def test_empty_whitelist(self):
        assert self.tm.get_tool_map([]) == {}
