'''会话管理：session_id → ChatAgent，以及 per-session 异步锁

- `default` 会话沿用 `chat_history/default.json`，老对话记录不丢；
- 其他会话写入 `chat_history/<session_id>.json`；
- session_id 只允许 `^[A-Za-z0-9_-]{1,64}$`，防止路径穿越。
'''
import asyncio
import os
import re
import threading

from backend.agent.chat_agent import ChatAgent
from backend.agent.history import HISTORY_DIR
from backend.core import facade

SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class SessionManager:
    '''按会话隔离 agent 与锁；agent 首次访问时由工厂惰性创建'''

    def __init__(self, agent_factory=None, history_dir: str = None):
        self._agent_factory = agent_factory or self._create_agent_from_env
        self.history_dir = history_dir or HISTORY_DIR
        self._agents: dict[str, ChatAgent] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        # 保护两个字典（server 内 agent 创建可能发生在 worker 线程）
        self._guard = threading.Lock()

    @staticmethod
    def validate_session_id(session_id: str) -> str:
        '''校验会话 ID，非法直接抛 ValueError（server 映射为 400）'''
        if not isinstance(session_id, str) or not SESSION_ID_RE.match(session_id):
            raise ValueError(f"非法 session_id：{session_id!r}")
        return session_id

    def history_file(self, session_id: str) -> str:
        '''会话对应的历史文件路径'''
        self.validate_session_id(session_id)
        name = "default.json" if session_id == "default" else f"{session_id}.json"
        return os.path.join(self.history_dir, name)

    def _create_agent_from_env(self, session_id: str) -> ChatAgent:
        '''默认工厂：从 .env 读连接参数，使用该会话专属的历史文件'''
        return facade.create_agent_from_env(history_file=self.history_file(session_id))

    def get_agent(self, session_id: str) -> ChatAgent:
        '''获取（必要时创建）该会话的 agent'''
        self.validate_session_id(session_id)
        with self._guard:
            agent = self._agents.get(session_id)
            if agent is None:
                agent = self._agent_factory(session_id)
                self._agents[session_id] = agent
            return agent

    def get_lock(self, session_id: str) -> asyncio.Lock:
        '''获取该会话的异步锁（同会话串行，不同会话互不影响）'''
        self.validate_session_id(session_id)
        with self._guard:
            lock = self._locks.get(session_id)
            if lock is None:
                lock = asyncio.Lock()
                self._locks[session_id] = lock
            return lock
