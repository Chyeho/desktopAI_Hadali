"""单元测试：陪伴主图骨架与 runner agent/graph/main_graph.py、runner.py"""
import re

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool

from agent.chat_agent import HistoryStore
from agent.graph.main_graph import build_main_graph, route_after_perception
from agent.graph.runner import CompanionGraphAgent

TIME_SUFFIX_RE = re.compile(r" \[\d{4}-\d{2}-\d{2} \d{2}:\d{2}\]$")
TIME_PREFIX_RE = re.compile(r"^\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}\] ")
# 直接调用编译后的图时需要 thread_id（已挂 MemorySaver）
CFG = {"configurable": {"thread_id": "test-thread"}}


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

        result = graph.invoke({"messages": [HumanMessage(content="今天有点累")]}, CFG)

        assert result["route"] == "chat"
        last_content = result["messages"][-1].content
        assert last_content.startswith(llm.reply)
        assert TIME_SUFFIX_RE.search(last_content)
        assert [m.content for m in llm.calls[0]][0] == "测试提示词"

    def test_game_request_enters_game_subgraph(self):
        """游戏请求进入 game_subgraph，由占位节点给出陪伴式回应"""
        llm = _FakeLLM("[emotion:thinking]\n游戏还在准备中哦，先陪你聊聊天吧。")
        graph = build_main_graph(llm, system_prompt="")

        result = graph.invoke({"messages": [HumanMessage(content="来下盘五子棋")]}, CFG)

        assert result["route"] == "game"
        assert result["game_request"] == "来下盘五子棋"
        last = result["messages"][-1]
        assert last.content.startswith("游戏还在准备中哦，先陪你聊聊天吧。")
        assert last.additional_kwargs["emotion"] == "thinking"

    def test_system_prompt_not_written_to_state(self):
        llm = _FakeLLM()
        graph = build_main_graph(llm, system_prompt="测试提示词")

        result = graph.invoke({"messages": [HumanMessage(content="你好")]}, CFG)

        assert [m.type for m in result["messages"]] == ["human", "ai"]

    def test_plain_chat_not_routed_to_game(self):
        llm = _FakeLLM("[emotion:relaxed]\n那就先聊聊今天吧。")
        graph = build_main_graph(llm, system_prompt="陪伴提示词")

        result = graph.invoke({"messages": [HumanMessage(content="今天有点累")]}, CFG)

        assert result["route"] == "chat"
        assert result["game_request"] is None
        assert result["messages"][-1].additional_kwargs["emotion"] == "relaxed"
        # 普通聊天应使用陪伴提示词，而不是游戏占位提示词
        system_prompt = [m for m in llm.calls[0] if m.type == "system"][0].content
        assert system_prompt == "陪伴提示词"

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

        result = graph.invoke({"messages": [HumanMessage(content="帮我确认一下")]}, CFG)

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

        result = graph.invoke({"messages": [HumanMessage(content="试一下")]}, CFG)

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

    def test_reply_echoed_timestamp_is_removed(self):
        """模型自行复述时间戳时：reply 与历史正文都不应残留（只保留系统后缀）"""
        llm = _FakeLLM("现在是 [2026-11-21 14:30]，该吃饭啦。")
        agent = CompanionGraphAgent(llm)

        result = agent.chat("几点了")

        assert result["reply"] == "现在是，该吃饭啦。"
        stored = agent.messages[-1].content
        assert "现在是，该吃饭啦。" in stored
        assert len(re.findall(r"\[\d{4}-\d{2}-\d{2}", stored)) == 1
        assert TIME_SUFFIX_RE.search(stored)


class TestHistoryMirror:
    """JSON 历史镜像与跨实例恢复"""

    def test_restore_from_json(self, tmp_path):
        history_file = str(tmp_path / "history.json")
        agent1 = CompanionGraphAgent(_FakeLLM("记住啦。"), history_file=history_file)
        agent1.chat("我叫小林")

        llm2 = _FakeLLM("你叫小林呀。")
        agent2 = CompanionGraphAgent(llm2, history_file=history_file)
        agent2.chat("我叫什么")

        contents = [m.content for m in llm2.calls[0]]
        assert any("我叫小林" in content for content in contents)
        assert any("我叫什么" in content for content in contents)

    def test_json_keeps_time_prefix_and_suffix(self, tmp_path):
        history_file = tmp_path / "history.json"
        agent = CompanionGraphAgent(_FakeLLM("记住啦。"), history_file=str(history_file))
        agent.chat("我叫小林")

        raw = history_file.read_text(encoding="utf-8")
        assert re.search(r"\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}\] 我叫小林", raw)
        assert re.search(r"记住啦。 \[\d{4}-\d{2}-\d{2} \d{2}:\d{2}\]", raw)

    def test_restore_drops_orphan_tool_messages(self, tmp_path):
        """历史里残留 ToolMessage / 带 tool_calls 的 AIMessage 时，恢复后不应注入模型

        回归：第二次启动报 "Messages with role 'tool' must be a response to a
        preceding message with 'tool_calls'"。
        """
        history_file = str(tmp_path / "history.json")
        store = HistoryStore(file_path=history_file)
        store.messages = [
            HumanMessage(content="[2026-11-21 10:00] 今天天气怎么样"),
            AIMessage(content="", tool_calls=[{
                "name": "get_weather", "args": {"city": "北京"}, "id": "call_1",
            }]),
            ToolMessage(content="晴，25 度", tool_call_id="call_1"),
            AIMessage(content="今天北京晴，25 度 [2026-11-21 10:00]"),
        ]
        store.save()

        llm = _FakeLLM("记得天气。")
        agent = CompanionGraphAgent(llm, history_file=history_file)
        agent.chat("那明天呢")

        sent = llm.calls[0]
        assert not any(isinstance(m, ToolMessage) for m in sent)
        assert not any(
            isinstance(m, AIMessage) and getattr(m, "tool_calls", None) for m in sent
        )
        # 纯对话内容仍保留
        assert any("今天天气怎么样" in str(m.content) for m in sent)
        assert any("今天北京晴" in str(m.content) for m in sent)

    def test_mirror_strips_tool_messages(self, tmp_path):
        """镜像写入前剥离工具中间消息，避免下次启动产生非法序列"""
        history_file = str(tmp_path / "history.json")
        agent = CompanionGraphAgent(_FakeLLM("好的。"), history_file=history_file)
        agent._mirror_history([
            HumanMessage(content="查天气"),
            AIMessage(content="", tool_calls=[{
                "name": "get_weather", "args": {}, "id": "call_1",
            }]),
            ToolMessage(content="晴", tool_call_id="call_1"),
            AIMessage(content="今天晴"),
        ])

        saved = HistoryStore(file_path=history_file).messages
        assert [type(m).__name__ for m in saved] == ["HumanMessage", "AIMessage"]
        assert saved[-1].content == "今天晴"


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

    def test_game_route_turn_result(self):
        """游戏占位子图：TurnResult 情绪与正文均正确（子图回复走一次性下发的降级路径）"""
        llm = _FakeLLM("[emotion:thinking]\n游戏还没做好，先陪你聊聊吧")
        agent = CompanionGraphAgent(llm, system_prompt="")

        result = agent.chat("来下盘五子棋")

        assert result["emotion"] == "thinking"
        assert result["reply"] == "游戏还没做好，先陪你聊聊吧"
        assert TIME_SUFFIX_RE.search(agent.messages[-1].content)

    def test_stream_without_tag(self):
        agent = _build_streaming_agent("就陪你聊聊吧")

        events = list(agent.stream_chat("在吗"))
        deltas = [payload for kind, payload in events if kind == "delta"]
        done = [payload for kind, payload in events if kind == "done"][0]

        assert "".join(deltas) == "就陪你聊聊吧"
        assert done["emotion"] == "neutral"
        assert done["reply"] == "就陪你聊聊吧"
