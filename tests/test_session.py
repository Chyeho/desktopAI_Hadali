"""单元测试：core/session.py 会话管理

覆盖历史文件映射、ID 校验、agent 惰性缓存、会话隔离与 per-session 锁。
"""
import asyncio
import os

import pytest

from backend.core.session import SessionManager


class _FakeAgent:
    """最小假 agent：只用于验证会话隔离"""

    def __init__(self, session_id):
        self.session_id = session_id


def _manager(tmp_path, calls=None):
    def factory(session_id):
        if calls is not None:
            calls.append(session_id)
        return _FakeAgent(session_id)

    return SessionManager(agent_factory=factory, history_dir=str(tmp_path))


class TestHistoryFile:
    """history_file：默认会话兼容与自定义会话隔离"""

    def test_default_session_uses_default_json(self, tmp_path):
        mgr = _manager(tmp_path)
        assert mgr.history_file("default") == os.path.join(str(tmp_path), "default.json")

    def test_custom_session_uses_own_file(self, tmp_path):
        mgr = _manager(tmp_path)
        assert mgr.history_file("work") == os.path.join(str(tmp_path), "work.json")

    @pytest.mark.parametrize("sid", ["", "a b", "../evil", "a/b", "x" * 65])
    def test_invalid_session_rejected(self, tmp_path, sid):
        mgr = _manager(tmp_path)
        with pytest.raises(ValueError):
            mgr.history_file(sid)


class TestAgents:
    """get_agent：惰性创建、缓存、隔离"""

    def test_agent_created_once_and_cached(self, tmp_path):
        calls = []
        mgr = _manager(tmp_path, calls)
        first = mgr.get_agent("default")
        second = mgr.get_agent("default")
        assert first is second
        assert calls == ["default"]

    def test_sessions_isolated(self, tmp_path):
        mgr = _manager(tmp_path)
        assert mgr.get_agent("a") is not mgr.get_agent("b")
        assert mgr.get_agent("a").session_id == "a"

    def test_invalid_session_rejected(self, tmp_path):
        mgr = _manager(tmp_path)
        with pytest.raises(ValueError):
            mgr.get_agent("../evil")


class TestLocks:
    """get_lock：同会话同一把锁，不同会话互不影响"""

    def test_lock_identity(self, tmp_path):
        mgr = _manager(tmp_path)

        async def main():
            assert mgr.get_lock("a") is mgr.get_lock("a")
            assert mgr.get_lock("a") is not mgr.get_lock("b")

        asyncio.run(main())

    def test_lock_serializes_same_session(self, tmp_path):
        mgr = _manager(tmp_path)
        order = []

        async def main():
            lock = mgr.get_lock("default")

            async def task(name, delay):
                async with lock:
                    order.append(f"{name}-enter")
                    await asyncio.sleep(delay)
                    order.append(f"{name}-exit")

            await asyncio.gather(task("a", 0.05), task("b", 0.0))

        asyncio.run(main())
        assert order == ["a-enter", "a-exit", "b-enter", "b-exit"]
