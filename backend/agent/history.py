'''对话历史持久化存储（JSON 文件）

从 `chat_agent.py` 抽出：主图 runner、server session 与 legacy 引擎共用，
避免公共能力随旧引擎一起被归档。

使用 langchain 的 message_to_dict / messages_from_dict 做序列化，
完整保留 Human / AIMessage（含 tool_calls）/ Tool / System 各类消息。
'''
import json
import os

from langchain_core.messages import (
    BaseMessage,
    SystemMessage,
    message_to_dict,
    messages_from_dict,
)

from utils.logger_handler import logger
from utils.path_tool import get_abs_path

# 历史记忆保留的最近消息条数（不含 system 消息），超出后裁剪旧消息，避免 token 膨胀
HISTORY_WINDOW = 30
# 历史消息持久化目录与文件（单用户单会话默认文件；多会话按会话 ID 区分）
HISTORY_DIR = get_abs_path("chat_history")
HISTORY_FILE = os.path.join(HISTORY_DIR, "default.json")


class HistoryStore:
    '''对话历史持久化存储（JSON 文件）'''

    def __init__(self, file_path: str = HISTORY_FILE):
        self.file_path = file_path
        os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
        self.messages: list[BaseMessage] = self._load()

    def _load(self) -> list[BaseMessage]:
        '''从文件加载历史消息，防御文件不存在/为空/损坏'''
        if not os.path.exists(self.file_path) or os.path.getsize(self.file_path) == 0:
            return []
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
            if not content:
                return []
            return messages_from_dict(json.loads(content))
        except Exception as e:
            logger.error(f"[HistoryStore]历史消息文件损坏或解析失败：{str(e)}，已重置为空")
            return []

    def save(self) -> None:
        '''将当前消息列表持久化到文件'''
        try:
            data = [message_to_dict(m) for m in self.messages]
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"[HistoryStore]历史消息写入失败：{str(e)}")

    def append(self, message: BaseMessage) -> None:
        '''追加一条消息并裁剪超长历史'''
        self.messages.append(message)
        self._trim()

    def replace(self, messages: list[BaseMessage]) -> None:
        '''整体替换历史并裁剪保存（LangGraph 引擎的 JSON 镜像使用）'''
        self.messages = list(messages)
        self._trim()
        self.save()

    def _trim(self) -> None:
        '''裁剪历史：始终保留 system 消息，其余只保留最近 HISTORY_WINDOW 条'''
        system_msgs = [m for m in self.messages if isinstance(m, SystemMessage)]
        others = [m for m in self.messages if not isinstance(m, SystemMessage)]
        if len(others) > HISTORY_WINDOW:
            others = others[-HISTORY_WINDOW:]
        self.messages = system_msgs + others

    def set_system_prompt(self, prompt: str) -> None:
        '''更新 system 消息（初始化或切换模式时调用）'''
        self.messages = [m for m in self.messages if not isinstance(m, SystemMessage)]
        if prompt:
            self.messages.insert(0, SystemMessage(content=prompt))

    def clear(self) -> None:
        '''清空历史'''
        self.messages = []
        self.save()
