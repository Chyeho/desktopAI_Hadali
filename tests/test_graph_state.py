"""单元测试：陪伴主图状态定义 agent/graph/state.py"""
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph.message import add_messages

from backend.agent.graph.state import AgentState


class TestAgentState:
    """AgentState 的消息 reducer"""

    def test_add_messages_appends(self):
        """新消息按顺序追加，而不是覆盖"""
        existing = [HumanMessage(content="你好", id="h1")]
        merged = add_messages(existing, [AIMessage(content="在呢", id="a1")])

        assert [m.content for m in merged] == ["你好", "在呢"]

    def test_add_messages_updates_by_id(self):
        """相同 id 的消息原位更新，用于后续占位/重写场景"""
        existing = [HumanMessage(content="旧内容", id="h1")]
        merged = add_messages(existing, [HumanMessage(content="新内容", id="h1")])

        assert len(merged) == 1
        assert merged[0].content == "新内容"

    def test_optional_fields_can_be_omitted(self):
        """total=False 允许只提供部分字段"""
        state: AgentState = {"route": "chat"}
        assert state["route"] == "chat"
        assert "messages" not in state
