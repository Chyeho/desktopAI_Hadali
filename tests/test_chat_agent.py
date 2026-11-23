"""单元测试：AI 对话核心 agent/chat_agent.py

覆盖：
- HistoryStore：加载/保存/裁剪/system prompt 管理/异常容错
- parse_reply_json：JSON 解析与各类容错回退
- ChatAgent.set_mode：模式切换（mock 工厂）
- ChatAgent.chat：工具调用循环（mock 模型）
"""
import json
import os
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.tools import tool

from agent.chat_agent import MAX_TOOL_STEPS, ChatAgent, parse_reply_json
from agent.history import HISTORY_WINDOW, HistoryStore


# =====================================================================
# HistoryStore
# =====================================================================

class TestHistoryStoreLoad:
    """HistoryStore._load：历史消息加载"""

    def test_new_file_returns_empty(self, tmp_path):
        """文件不存在时返回空列表"""
        store = HistoryStore(file_path=str(tmp_path / "history.json"))
        assert store.messages == []

    def test_empty_file_returns_empty(self, tmp_path):
        """文件存在但为空时返回空列表"""
        f = tmp_path / "history.json"
        f.write_text("", encoding="utf-8")
        store = HistoryStore(file_path=str(f))
        assert store.messages == []

    def test_corrupt_file_returns_empty(self, tmp_path):
        """文件内容损坏（非法 JSON）时返回空列表，不抛异常"""
        f = tmp_path / "history.json"
        f.write_text("{这不是合法json", encoding="utf-8")
        store = HistoryStore(file_path=str(f))
        assert store.messages == []

    def test_load_existing_messages(self, tmp_path):
        """正常加载已保存的消息"""
        f = tmp_path / "history.json"
        store1 = HistoryStore(file_path=str(f))
        store1.append(HumanMessage(content="你好"))
        store1.save()

        store2 = HistoryStore(file_path=str(f))
        assert len(store2.messages) == 1
        assert store2.messages[0].content == "你好"

    def test_creates_directory(self, tmp_path):
        """目标目录不存在时自动创建"""
        nested = tmp_path / "a" / "b" / "history.json"
        store = HistoryStore(file_path=str(nested))
        assert os.path.isdir(str(nested.parent))


class TestHistoryStoreSave:
    """HistoryStore.save：持久化"""

    def test_save_roundtrip(self, tmp_path):
        """保存后重新加载，消息应一致"""
        f = tmp_path / "history.json"
        store = HistoryStore(file_path=str(f))
        store.append(SystemMessage(content="system"))
        store.append(HumanMessage(content="hello"))
        store.append(AIMessage(content="hi"))
        store.save()

        store2 = HistoryStore(file_path=str(f))
        assert len(store2.messages) == 3
        assert store2.messages[0].content == "system"
        assert store2.messages[1].content == "hello"
        assert store2.messages[2].content == "hi"

    def test_save_preserves_tool_messages(self, tmp_path):
        """保存/加载应保留 ToolMessage 的 tool_call_id"""
        f = tmp_path / "history.json"
        store = HistoryStore(file_path=str(f))
        store.append(HumanMessage(content="几点了"))
        store.append(ToolMessage(content="12:00", tool_call_id="tc1", name="get_current_time"))
        store.save()

        store2 = HistoryStore(file_path=str(f))
        tm = store2.messages[-1]
        assert isinstance(tm, ToolMessage)
        assert tm.content == "12:00"
        assert tm.tool_call_id == "tc1"


class TestHistoryStoreTrim:
    """HistoryStore._trim：历史裁剪"""

    def test_trim_keeps_system_and_recent(self, tmp_path):
        """裁剪后保留 system 消息 + 最近 HISTORY_WINDOW 条非 system 消息"""
        f = tmp_path / "history.json"
        store = HistoryStore(file_path=str(f))
        store.set_system_prompt("sys")
        for i in range(HISTORY_WINDOW + 5):
            store.append(HumanMessage(content=f"msg-{i}"))

        system_count = sum(1 for m in store.messages if isinstance(m, SystemMessage))
        other_count = sum(1 for m in store.messages if not isinstance(m, SystemMessage))
        assert system_count == 1
        assert other_count == HISTORY_WINDOW

    def test_no_trim_when_under_limit(self, tmp_path):
        """未超限时不应裁剪"""
        f = tmp_path / "history.json"
        store = HistoryStore(file_path=str(f))
        for i in range(5):
            store.append(HumanMessage(content=f"m{i}"))
        assert len(store.messages) == 5

    def test_trim_keeps_latest_messages(self, tmp_path):
        """裁剪后保留的是最新的消息"""
        f = tmp_path / "history.json"
        store = HistoryStore(file_path=str(f))
        for i in range(HISTORY_WINDOW + 2):
            store.append(HumanMessage(content=f"msg-{i}"))
        others = [m for m in store.messages if not isinstance(m, SystemMessage)]
        assert others[0].content == "msg-2"
        assert others[-1].content == f"msg-{HISTORY_WINDOW + 1}"


class TestHistoryStoreReplace:
    """HistoryStore.replace：整体替换（图引擎 JSON 镜像）"""

    def test_replace_trims_and_saves(self, tmp_path):
        f = tmp_path / "history.json"
        store = HistoryStore(file_path=str(f))
        messages = [HumanMessage(content=f"m{i}") for i in range(HISTORY_WINDOW + 3)]

        store.replace(messages)

        assert len(store.messages) == HISTORY_WINDOW
        assert store.messages[-1].content == f"m{HISTORY_WINDOW + 2}"
        reloaded = HistoryStore(file_path=str(f))
        assert len(reloaded.messages) == HISTORY_WINDOW


class TestHistoryStoreSystemPrompt:
    """HistoryStore.set_system_prompt / clear"""

    def test_set_system_prompt_replaces_old(self, tmp_path):
        f = tmp_path / "history.json"
        store = HistoryStore(file_path=str(f))
        store.set_system_prompt("prompt-A")
        store.set_system_prompt("prompt-B")
        system_msgs = [m for m in store.messages if isinstance(m, SystemMessage)]
        assert len(system_msgs) == 1
        assert system_msgs[0].content == "prompt-B"

    def test_set_system_prompt_at_index_zero(self, tmp_path):
        f = tmp_path / "history.json"
        store = HistoryStore(file_path=str(f))
        store.append(HumanMessage(content="hi"))
        store.set_system_prompt("sys")
        assert isinstance(store.messages[0], SystemMessage)

    def test_clear_empties_messages(self, tmp_path):
        f = tmp_path / "history.json"
        store = HistoryStore(file_path=str(f))
        store.append(HumanMessage(content="x"))
        store.clear()
        assert store.messages == []

    def test_clear_persists_empty(self, tmp_path):
        """clear 后文件应为空列表"""
        f = tmp_path / "history.json"
        store = HistoryStore(file_path=str(f))
        store.append(HumanMessage(content="x"))
        store.clear()
        store2 = HistoryStore(file_path=str(f))
        assert store2.messages == []


# =====================================================================
# parse_reply_json
# =====================================================================

class TestParseReplyJson:
    """parse_reply_json：大模型回复 JSON 解析"""

    def test_standard_json(self):
        content = '{"emotion": "happy", "reply": "你好呀"}'
        emotion, reply = parse_reply_json(content)
        assert emotion == "happy"
        assert reply == "你好呀"

    def test_json_in_markdown_fence(self):
        content = '```json\n{"emotion": "sad", "reply": "我很难过"}\n```'
        emotion, reply = parse_reply_json(content)
        assert emotion == "sad"
        assert reply == "我很难过"

    def test_json_in_plain_fence(self):
        content = '```\n{"emotion": "angry", "reply": "生气了"}\n```'
        emotion, reply = parse_reply_json(content)
        assert emotion == "angry"
        assert reply == "生气了"

    def test_json_with_extra_text(self):
        """JSON 外夹带额外文字，应截取 { 到 }"""
        content = '好的，这是我的回复：{"emotion": "relaxed", "reply": "放松一下"} 希望你喜欢'
        emotion, reply = parse_reply_json(content)
        assert emotion == "relaxed"
        assert reply == "放松一下"

    def test_empty_content(self):
        emotion, reply = parse_reply_json("")
        assert emotion == "neutral"
        assert reply == ""

    def test_none_content(self):
        emotion, reply = parse_reply_json(None)
        assert emotion == "neutral"
        assert reply == ""

    def test_invalid_json_falls_back(self):
        """非法 JSON 应回退为 neutral + 原文"""
        content = "这不是JSON，就是普通文字"
        emotion, reply = parse_reply_json(content)
        assert emotion == "neutral"
        assert reply == content

    def test_missing_emotion_defaults_neutral(self):
        content = '{"reply": "没有情感标签"}'
        emotion, reply = parse_reply_json(content)
        assert emotion == "neutral"
        assert reply == "没有情感标签"

    def test_missing_reply_falls_back_to_original(self):
        """reply 为空时回退使用原文"""
        content = '{"emotion": "happy"}'
        emotion, reply = parse_reply_json(content)
        assert emotion == "happy"
        assert reply == content

    def test_empty_reply_string_falls_back(self):
        """reply 显式为空字符串时回退使用原文"""
        content = '{"emotion": "shy", "reply": ""}'
        emotion, reply = parse_reply_json(content)
        assert emotion == "shy"
        assert reply == content

    def test_empty_emotion_defaults_neutral(self):
        content = '{"emotion": "", "reply": "内容"}'
        emotion, reply = parse_reply_json(content)
        assert emotion == "neutral"
        assert reply == "内容"

    def test_whitespace_stripped(self):
        content = '  {"emotion": "  surprised  ", "reply": "  哇  "}  '
        emotion, reply = parse_reply_json(content)
        assert emotion == "surprised"
        assert reply == "哇"


# =====================================================================
# ChatAgent.set_mode（mock 工厂）
# =====================================================================

class _FakeFactory:
    """模拟模型工厂：返回 MagicMock 作为 LLM"""

    def __init__(self):
        self.last_params = None

    def generator(self, **gen_params):
        self.last_params = gen_params
        llm = MagicMock()
        llm.bind_tools.return_value = llm  # bind_tools 返回自身
        return llm


@tool
def _fake_echo(text: str = "") -> str:
    """测试用本地工具：原样返回文本（不依赖网络）"""
    return f"echo:{text}"


class _StubToolManager:
    """工具管理器桩：返回本地假工具，避免真实天气/搜索请求

    时间工具已迁至 utils/time_utils.py，legacy 模式不再提供本地时间工具，
    因此工具循环测试改用离线假工具。
    """

    def get_tools(self, allowed_tools):
        return [_fake_echo]


@pytest.fixture
def patched_history(tmp_path, monkeypatch):
    """将 HistoryStore 默认路径重定向到临时文件，隔离真实 chat_history/default.json

    ChatAgent.__init__ 内部调用 HistoryStore()（默认路径指向真实历史文件），
    通过 monkeypatch 替换 HistoryStore 为使用临时文件的子类，避免污染真实数据。
    返回临时文件路径，供需要直接访问的测试使用。
    """
    temp_file = str(tmp_path / "history.json")

    class _TempHistoryStore(HistoryStore):
        def __init__(self, file_path=None):
            super().__init__(file_path=temp_file)

    monkeypatch.setattr("agent.chat_agent.HistoryStore", _TempHistoryStore)
    return temp_file


class TestChatAgentSetMode:
    """ChatAgent.set_mode：模式切换逻辑"""

    def test_init_loads_default_mode(self, patched_history):
        agent = ChatAgent(model_factory=_FakeFactory())
        assert agent.mode_config["name"] == "emotion"

    def test_switch_to_office(self, patched_history):
        agent = ChatAgent(model_factory=_FakeFactory())
        agent.set_mode("office")
        assert agent.mode_config["name"] == "office"
        assert agent.mode_config["allowed_tools"] == []

    def test_unknown_mode_raises(self, patched_history):
        agent = ChatAgent(model_factory=_FakeFactory())
        with pytest.raises(ValueError, match="未知的 agent 模式"):
            agent.set_mode("nonexistent_mode")

    def test_factory_receives_mode_params(self, patched_history):
        """工厂应收到对应模式的 model_params"""
        fake = _FakeFactory()
        agent = ChatAgent(model_factory=fake)
        assert fake.last_params == agent.mode_config["model_params"]

    def test_office_tools_empty_no_bind_tools(self, patched_history):
        """office 模式无工具时，llm_with_tools 等于 llm 本身"""
        fake = _FakeFactory()
        agent = ChatAgent(model_factory=fake)
        agent.set_mode("office")
        assert agent.llm_with_tools is agent.llm

    def test_emotion_tools_bound(self, patched_history):
        """emotion 模式有工具时调用 bind_tools"""
        fake = _FakeFactory()
        agent = ChatAgent(model_factory=fake)
        agent.llm.bind_tools.assert_called_once()

    def test_system_prompt_loaded_into_history(self, patched_history):
        agent = ChatAgent(model_factory=_FakeFactory())
        system_msgs = [m for m in agent.history.messages
                       if isinstance(m, SystemMessage)]
        assert len(system_msgs) == 1
        assert len(system_msgs[0].content) > 0


# =====================================================================
# ChatAgent.chat（mock 模型，测试工具调用循环）
# =====================================================================

class TestChatAgentChat:
    """ChatAgent.chat：对话主流程"""

    def test_direct_reply_no_tools(self, patched_history):
        """模型直接回复（不调用工具）"""
        agent = ChatAgent(model_factory=_FakeFactory())
        # mock 模型：第一次调用返回最终回复
        agent.llm_with_tools.invoke = MagicMock(
            return_value=AIMessage(content='{"emotion": "happy", "reply": "你好！"}')
        )
        result = agent.chat("你好")
        assert result["emotion"] == "happy"
        assert result["reply"] == "你好！"

    def test_tool_call_loop(self, patched_history):
        """模型先调用工具再回复"""
        agent = ChatAgent(model_factory=_FakeFactory(), tool_manager=_StubToolManager())

        # 第一次：请求调用本地假工具
        # 第二次：给出最终回复
        agent.llm_with_tools.invoke = MagicMock(side_effect=[
            AIMessage(
                content="",
                tool_calls=[{"name": "_fake_echo", "args": {"text": "hi"}, "id": "tc1"}],
            ),
            AIMessage(content='{"emotion": "neutral", "reply": "现在是下午"}'),
        ])
        result = agent.chat("几点了")
        assert result["emotion"] == "neutral"
        assert result["reply"] == "现在是下午"
        # 工具结果应回填到历史
        tool_msgs = [m for m in agent.history.messages if isinstance(m, ToolMessage)]
        assert len(tool_msgs) == 1
        assert tool_msgs[0].content == "echo:hi"

    def test_unknown_tool_returns_error_message(self, patched_history):
        """模型请求调用未授权工具时回填错误信息"""
        agent = ChatAgent(model_factory=_FakeFactory())
        agent.llm_with_tools.invoke = MagicMock(side_effect=[
            AIMessage(
                content="",
                tool_calls=[{"name": "nonexistent", "args": {}, "id": "tc1"}],
            ),
            AIMessage(content='{"emotion": "neutral", "reply": "抱歉"}'),
        ])
        result = agent.chat("测试")
        assert result["reply"] == "抱歉"
        tool_msgs = [m for m in agent.history.messages if isinstance(m, ToolMessage)]
        assert "不可用" in tool_msgs[0].content

    def test_max_tool_steps_reached(self, patched_history):
        """工具调用达到上限时强制结束"""
        agent = ChatAgent(model_factory=_FakeFactory(), tool_manager=_StubToolManager())
        # 每次都请求调用工具，永不给出最终回复
        agent.llm_with_tools.invoke = MagicMock(
            return_value=AIMessage(
                content="",
                tool_calls=[{"name": "_fake_echo", "args": {}, "id": "tc1"}],
            )
        )
        result = agent.chat("无限循环")
        # 达到 MAX_TOOL_STEPS 后应返回兜底回复
        assert agent.llm_with_tools.invoke.call_count == MAX_TOOL_STEPS
        assert isinstance(result["emotion"], str)

    def test_user_message_recorded(self, patched_history):
        """用户输入应记录到历史"""
        agent = ChatAgent(model_factory=_FakeFactory())
        agent.llm_with_tools.invoke = MagicMock(
            return_value=AIMessage(content='{"emotion": "happy", "reply": "好的"}')
        )
        agent.chat("你好呀")
        human_msgs = [m for m in agent.history.messages if isinstance(m, HumanMessage)]
        assert any(m.content == "你好呀" for m in human_msgs)
