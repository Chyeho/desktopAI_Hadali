"""单元测试：backend/agent/history.py 历史持久化

覆盖 HistoryStore 的加载容错、保存 roundtrip、裁剪窗口、整体替换与
system prompt 管理（从 legacy 测试迁出，保证公共能力独立受测）。
"""
import os

from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from backend.agent.history import HISTORY_WINDOW, HistoryStore


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
        HistoryStore(file_path=str(nested))
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
        assert [m.content for m in store2.messages] == ["system", "hello", "hi"]

    def test_save_preserves_tool_messages(self, tmp_path):
        """保存/加载应保留 ToolMessage 的 tool_call_id"""
        f = tmp_path / "history.json"
        store = HistoryStore(file_path=str(f))
        store.append(HumanMessage(content="几点了"))
        store.append(ToolMessage(content="12:00", tool_call_id="tc1", name="get_current_time"))
        store.save()

        tm = HistoryStore(file_path=str(f)).messages[-1]
        assert isinstance(tm, ToolMessage)
        assert tm.content == "12:00"
        assert tm.tool_call_id == "tc1"


class TestHistoryStoreTrim:
    """HistoryStore._trim：历史裁剪"""

    def test_trim_keeps_system_and_recent(self, tmp_path):
        """裁剪后保留 system 消息 + 最近 HISTORY_WINDOW 条非 system 消息"""
        store = HistoryStore(file_path=str(tmp_path / "history.json"))
        store.set_system_prompt("sys")
        for i in range(HISTORY_WINDOW + 5):
            store.append(HumanMessage(content=f"msg-{i}"))

        system_count = sum(1 for m in store.messages if isinstance(m, SystemMessage))
        other_count = sum(1 for m in store.messages if not isinstance(m, SystemMessage))
        assert system_count == 1
        assert other_count == HISTORY_WINDOW

    def test_no_trim_when_under_limit(self, tmp_path):
        """未超限时不应裁剪"""
        store = HistoryStore(file_path=str(tmp_path / "history.json"))
        for i in range(5):
            store.append(HumanMessage(content=f"m{i}"))
        assert len(store.messages) == 5

    def test_trim_keeps_latest_messages(self, tmp_path):
        """裁剪后保留的是最新的消息"""
        store = HistoryStore(file_path=str(tmp_path / "history.json"))
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
        assert len(HistoryStore(file_path=str(f)).messages) == HISTORY_WINDOW


class TestHistoryStoreSystemPrompt:
    """HistoryStore.set_system_prompt / clear"""

    def test_set_system_prompt_replaces_old(self, tmp_path):
        store = HistoryStore(file_path=str(tmp_path / "history.json"))
        store.set_system_prompt("prompt-A")
        store.set_system_prompt("prompt-B")
        system_msgs = [m for m in store.messages if isinstance(m, SystemMessage)]
        assert len(system_msgs) == 1
        assert system_msgs[0].content == "prompt-B"

    def test_set_system_prompt_at_index_zero(self, tmp_path):
        store = HistoryStore(file_path=str(tmp_path / "history.json"))
        store.append(HumanMessage(content="hi"))
        store.set_system_prompt("sys")
        assert isinstance(store.messages[0], SystemMessage)

    def test_clear_empties_messages(self, tmp_path):
        store = HistoryStore(file_path=str(tmp_path / "history.json"))
        store.append(HumanMessage(content="x"))
        store.clear()
        assert store.messages == []

    def test_clear_persists_empty(self, tmp_path):
        """clear 后文件应为空列表"""
        f = tmp_path / "history.json"
        store = HistoryStore(file_path=str(f))
        store.append(HumanMessage(content="x"))
        store.clear()
        assert HistoryStore(file_path=str(f)).messages == []
