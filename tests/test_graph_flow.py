"""单元测试：陪伴主图骨架与 runner agent/graph/main_graph.py、runner.py"""
import re

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool

from agent.graph.main_graph import build_main_graph, route_after_perception
from agent.graph.runner import CompanionGraphAgent

TIME_SUFFIX_RE = re.compile(r" \[\d{4}-\d{2}-\d{2} \d{2}:\d{2}\]$")
TIME_PREFIX_RE = re.compile(r"^\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}\] ")


class _FakeLLM:
    """最小模型桩：记录收到的消息并返回固定回复"""

    def __init__(self, reply: str = "我在呢，想聊什么都可以呀。"):
        self.reply = reply
        self.calls: list[list] = []
        self.bound_tools: list = []

    def bind_tools(self, tools):
        self.bound_tools = list(tools)
        return self

    def invoke(self, messages):
        self.calls.append(list(messages))
        return AIMessage(content=self.reply)


class _ScriptedLLM:
    """按脚本依次返回 AIMessage，用于验证工具循环"""

    def __init__(self, responses: list[AIMessage]):
        self.responses = list(responses)
        self.calls: list[list] = []

    def bind_tools(self, tools):
        return self

    def invoke(self, messages):
        self.calls.append(list(messages))
        return self.responses.pop(0)


@tool
def _fake_echo(text: str = "") -> str:
    """测试用本地工具：原样返回文本（不依赖网络）"""
    return f"echo:{text}"


class _StreamingLLM(GenericFakeChatModel):
    """支持 bind_tools 的流式假模型，用于验证 token 流"""

    def bind_tools(self, tools, **kwargs):
        return self


def _build_streaming_agent(reply: str) -> CompanionGraphAgent:
    llm = _StreamingLLM(messages=iter([AIMessage(content=reply)]))
    return CompanionGraphAgent(llm, system_prompt="")


class TestMainGraph:
    """主图 chat 分支"""

    def test_chat_flow_returns_ai_message(self):
        llm = _FakeLLM()
        graph = build_main_graph(llm, system_prompt="测试提示词")

        result = graph.invoke({"messages": [HumanMessage(content="今天有点累")]})

        assert result["route"] == "chat"
        last_content = result["messages"][-1].content
        assert last_content.startswith(llm.reply)
        assert TIME_SUFFIX_RE.search(last_content)
        assert [m.content for m in llm.calls[0]][0] == "测试提示词"

    def test_game_request_still_answered_in_p1(self):
        """P1 游戏子图未接入，game 路由暂时由 agent 回复"""
        llm = _FakeLLM("游戏功能还在准备中哦。")
        graph = build_main_graph(llm, system_prompt="")

        result = graph.invoke({"messages": [HumanMessage(content="来下盘五子棋")]})

        assert result["route"] == "game"
        assert result["game_request"] == "来下盘五子棋"
        assert result["messages"][-1].content.startswith("游戏功能还在准备中哦。")

    def test_system_prompt_not_written_to_state(self):
        llm = _FakeLLM()
        graph = build_main_graph(llm, system_prompt="测试提示词")

        result = graph.invoke({"messages": [HumanMessage(content="你好")]})

        assert [m.type for m in result["messages"]] == ["human", "ai"]

    def test_route_after_perception_defaults_to_chat(self):
        assert route_after_perception({}) == "chat"
        assert route_after_perception({"route": "game"}) == "game"


class TestToolLoop:
    """agent ⇄ tools 循环"""

    def test_tool_call_executes_and_returns_final_reply(self):
        llm = _ScriptedLLM([
            AIMessage(content="", tool_calls=[
                {"name": "_fake_echo", "args": {"text": "hi"}, "id": "c1"},
            ]),
            AIMessage(content="已经帮你确认好啦。"),
        ])
        graph = build_main_graph(llm, system_prompt="", tools=[_fake_echo])

        result = graph.invoke({"messages": [HumanMessage(content="帮我确认一下")]})

        tool_messages = [m for m in result["messages"] if isinstance(m, ToolMessage)]
        assert len(tool_messages) == 1
        assert tool_messages[0].content == "echo:hi"
        assert result["messages"][-1].content.startswith("已经帮你确认好啦。")
        assert len(llm.calls) == 2

    def test_tool_error_becomes_tool_message(self):
        @tool
        def _boom() -> str:
            """总是抛异常的工具"""
            raise RuntimeError("boom")

        llm = _ScriptedLLM([
            AIMessage(content="", tool_calls=[{"name": "_boom", "args": {}, "id": "c1"}]),
            AIMessage(content="刚才工具出了点问题，我们换个方式试试。"),
        ])
        graph = build_main_graph(llm, system_prompt="", tools=[_boom])

        result = graph.invoke({"messages": [HumanMessage(content="试一下")]})

        tool_messages = [m for m in result["messages"] if isinstance(m, ToolMessage)]
        assert len(tool_messages) == 1
        assert result["messages"][-1].content.startswith("刚才工具出了点问题，我们换个方式试试。")


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

    def test_tool_turn_metrics(self):
        llm = _ScriptedLLM([
            AIMessage(content="", tool_calls=[
                {"name": "_fake_echo", "args": {"text": "hi"}, "id": "c1"},
            ]),
            AIMessage(content="好的。"),
        ])
        graph = build_main_graph(llm, system_prompt="", tools=[_fake_echo])
        agent = CompanionGraphAgent(graph=graph)

        result = agent.chat("试一下工具")

        assert result["steps"] == 2
        assert result["tool_calls"][0]["name"] == "_fake_echo"
        assert result["tool_calls"][0]["ok"] is True

    def test_multi_turn_keeps_context(self):
        llm = _FakeLLM("记得的。")
        agent = CompanionGraphAgent(llm)

        agent.chat("我叫小林")
        agent.chat("我叫什么")

        second_call = [m.content for m in llm.calls[1]]
        assert any("我叫小林" in content for content in second_call)
        assert any("我叫什么" in content for content in second_call)

    def test_user_message_gets_time_prefix(self):
        llm = _FakeLLM()
        agent = CompanionGraphAgent(llm)

        agent.chat("你好")

        human_contents = [
            m.content for m in llm.calls[0] if isinstance(m, HumanMessage)
        ]
        assert TIME_PREFIX_RE.search(human_contents[-1])

    def test_set_mode_is_noop(self):
        agent = CompanionGraphAgent(_FakeLLM())
        agent.set_mode("office")
        assert agent.mode_config["name"] == "emotion"


class TestStreamChat:
    """stream_chat：逐 token 输出且过滤情绪标签"""

    def test_stream_yields_clean_deltas(self):
        agent = _build_streaming_agent("[emotion:happy]\n今天也要开心呀")

        events = list(agent.stream_chat("你好"))
        deltas = [payload for kind, payload in events if kind == "delta"]
        done = [payload for kind, payload in events if kind == "done"][0]

        assert "".join(deltas) == "今天也要开心呀"
        assert all("[" not in delta for delta in deltas)
        assert done["emotion"] == "happy"
        assert done["reply"] == "今天也要开心呀"
        assert TIME_SUFFIX_RE.search(agent.messages[-1].content)

    def test_stream_without_tag(self):
        agent = _build_streaming_agent("就陪你聊聊吧")

        events = list(agent.stream_chat("在吗"))
        deltas = [payload for kind, payload in events if kind == "delta"]
        done = [payload for kind, payload in events if kind == "done"][0]

        assert "".join(deltas) == "就陪你聊聊吧"
        assert done["emotion"] == "neutral"
        assert done["reply"] == "就陪你聊聊吧"
