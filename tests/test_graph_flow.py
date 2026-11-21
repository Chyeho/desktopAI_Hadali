"""单元测试：陪伴主图骨架与 runner agent/graph/main_graph.py、runner.py"""
from langchain_core.messages import AIMessage, HumanMessage

from agent.graph.main_graph import build_main_graph, route_after_perception
from agent.graph.runner import CompanionGraphAgent


class _FakeLLM:
    """最小模型桩：记录收到的消息并返回固定回复"""

    def __init__(self, reply: str = "我在呢，想聊什么都可以呀。"):
        self.reply = reply
        self.calls: list[list] = []

    def invoke(self, messages):
        self.calls.append(list(messages))
        return AIMessage(content=self.reply)


class TestMainGraph:
    """主图 chat 分支"""

    def test_chat_flow_returns_ai_message(self):
        llm = _FakeLLM()
        graph = build_main_graph(llm, system_prompt="测试提示词")

        result = graph.invoke({"messages": [HumanMessage(content="今天有点累")]})

        assert result["route"] == "chat"
        assert result["messages"][-1].content == llm.reply
        assert [m.content for m in llm.calls[0]][0] == "测试提示词"

    def test_game_request_still_answered_in_p1(self):
        """P1 游戏子图未接入，game 路由暂时由 agent 回复"""
        llm = _FakeLLM("游戏功能还在准备中哦。")
        graph = build_main_graph(llm, system_prompt="")

        result = graph.invoke({"messages": [HumanMessage(content="来下盘五子棋")]})

        assert result["route"] == "game"
        assert result["game_request"] == "来下盘五子棋"
        assert result["messages"][-1].content == "游戏功能还在准备中哦。"

    def test_system_prompt_not_written_to_state(self):
        llm = _FakeLLM()
        graph = build_main_graph(llm, system_prompt="测试提示词")

        result = graph.invoke({"messages": [HumanMessage(content="你好")]})

        assert [m.type for m in result["messages"]] == ["human", "ai"]

    def test_route_after_perception_defaults_to_chat(self):
        assert route_after_perception({}) == "chat"
        assert route_after_perception({"route": "game"}) == "game"


class TestCompanionGraphAgent:
    """runner 的 TurnResult 契约"""

    def test_chat_returns_turn_result(self):
        agent = CompanionGraphAgent(_FakeLLM("陪着你呢。"))

        result = agent.chat("你好")

        assert result["reply"] == "陪着你呢。"
        assert result["emotion"] == "neutral"
        assert result["mode"] == "emotion"
        assert result["steps"] == 1
        assert result["tool_calls"] == []
        assert result["latency_ms"] >= 0

    def test_multi_turn_keeps_context(self):
        llm = _FakeLLM("记得的。")
        agent = CompanionGraphAgent(llm)

        agent.chat("我叫小林")
        agent.chat("我叫什么")

        second_call = [m.content for m in llm.calls[1]]
        assert "我叫小林" in second_call
        assert "我叫什么" in second_call

    def test_set_mode_is_noop(self):
        agent = CompanionGraphAgent(_FakeLLM())
        agent.set_mode("office")
        assert agent.mode_config["name"] == "emotion"
