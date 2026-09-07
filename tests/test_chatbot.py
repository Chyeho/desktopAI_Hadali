"""单元测试：AI 对话门面 chatbot.py

覆盖：
- _load_env：.env 文件解析
- init_api_key / init_api_key_from_env：初始化（mock 工厂）
- chat_with_model / switch_mode：对外接口（mock agent）
"""
import os
from unittest.mock import MagicMock, patch

import pytest

import chatbot


class TestLoadEnv:
    """_load_env：轻量 .env 解析"""

    def test_parse_basic_env(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text(
            'API_KEY=sk-test123\n'
            'BASE_URL=https://api.test.com/v1\n'
            'MODEL=test-model\n',
            encoding="utf-8",
        )
        env = chatbot._load_env(str(env_file))
        assert env["API_KEY"] == "sk-test123"
        assert env["BASE_URL"] == "https://api.test.com/v1"
        assert env["MODEL"] == "test-model"

    def test_skip_comments(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text(
            '# 这是注释\n'
            'API_KEY=sk-real\n'
            '#BASE_URL=skipped\n'
            'MODEL=m\n',
            encoding="utf-8",
        )
        env = chatbot._load_env(str(env_file))
        assert env == {"API_KEY": "sk-real", "MODEL": "m"}

    def test_skip_empty_lines(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("\n\nAPI_KEY=sk-x\n\n\n", encoding="utf-8")
        env = chatbot._load_env(str(env_file))
        assert env == {"API_KEY": "sk-x"}

    def test_skip_lines_without_equals(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("API_KEY=sk-x\nNOT_A_LINE\n", encoding="utf-8")
        env = chatbot._load_env(str(env_file))
        assert env == {"API_KEY": "sk-x"}

    def test_strip_quotes(self, tmp_path):
        """值两端的引号应被去除"""
        env_file = tmp_path / ".env"
        env_file.write_text(
            'KEY1="quoted"\n'
            "KEY2='single'\n",
            encoding="utf-8",
        )
        env = chatbot._load_env(str(env_file))
        assert env["KEY1"] == "quoted"
        assert env["KEY2"] == "single"

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            chatbot._load_env(str(tmp_path / "nope.env"))


class TestInitApiKey:
    """init_api_key：初始化对话 Agent"""

    def test_init_sets_agent(self):
        chatbot._agent = None
        chatbot.init_api_key(api_key="sk-test", base_url="http://x", model="m")
        assert chatbot._agent is not None
        assert chatbot._agent.mode_config["name"] == "emotion"
        # 清理全局状态
        chatbot._agent = None

    def test_init_default_values(self):
        """不传 base_url / model 时使用默认值"""
        chatbot._agent = None
        with patch("chatbot.ChatModelFactory") as mock_factory_cls:
            mock_factory = MagicMock()
            mock_factory_cls.return_value = mock_factory
            chatbot.init_api_key(api_key="sk-test")
            mock_factory_cls.assert_called_once_with(
                api_key="sk-test",
                base_url="https://api.deepseek.com/v1",
                model="deepseek-chat",
            )
        chatbot._agent = None


class TestInitApiKeyFromEnv:
    """init_api_key_from_env：从 .env 读取并初始化"""

    def test_missing_api_key_raises(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("MODEL=m\n", encoding="utf-8")
        with pytest.raises(ValueError, match="API_KEY"):
            chatbot.init_api_key_from_env(str(env_file))

    def test_loads_from_env_file(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text(
            "API_KEY=sk-env-test\n"
            "BASE_URL=http://localhost\n"
            "MODEL=custom-model\n",
            encoding="utf-8",
        )
        chatbot._agent = None
        with patch("chatbot.ChatModelFactory") as mock_factory_cls:
            mock_factory_cls.return_value = MagicMock()
            chatbot.init_api_key_from_env(str(env_file))
            mock_factory_cls.assert_called_once_with(
                api_key="sk-env-test",
                base_url="http://localhost",
                model="custom-model",
            )
        chatbot._agent = None


class TestChatWithModel:
    """chat_with_model：对外对话接口"""

    def test_raises_when_not_initialized(self):
        chatbot._agent = None
        with pytest.raises(RuntimeError, match="尚未初始化"):
            chatbot.chat_with_model("你好")

    def test_returns_reply_text(self):
        """已初始化时调用 agent.chat 并返回 reply"""
        mock_agent = MagicMock()
        mock_agent.chat.return_value = {"emotion": "happy", "reply": "你好呀"}
        chatbot._agent = mock_agent
        result = chatbot.chat_with_model("你好", live2d_model=None)
        assert result == "你好呀"
        mock_agent.chat.assert_called_once()
        chatbot._agent = None

    def test_updates_partial_reply(self):
        mock_agent = MagicMock()
        mock_agent.chat.return_value = {"emotion": "neutral", "reply": "回复"}
        chatbot._agent = mock_agent
        chatbot.last_partial_reply = ""
        chatbot.chat_with_model("hi")
        assert chatbot.last_partial_reply == "回复"
        chatbot._agent = None


class TestSwitchMode:
    """switch_mode：模式切换接口"""

    def test_raises_when_not_initialized(self):
        chatbot._agent = None
        with pytest.raises(RuntimeError, match="尚未初始化"):
            chatbot.switch_mode("office")

    def test_calls_agent_set_mode(self):
        mock_agent = MagicMock()
        chatbot._agent = mock_agent
        chatbot.switch_mode("office")
        mock_agent.set_mode.assert_called_once_with("office")
        chatbot._agent = None
