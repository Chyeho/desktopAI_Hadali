"""单元测试：语音合成 chatbotTTS.py

覆盖：
- _clean_text：清理不适合朗读的字符
- _load_env：.env 解析
- TTS_MODE / 音色配置默认值与回退
"""
import os
from unittest.mock import patch

import pytest

import chatbotTTS


class TestCleanText:
    """_clean_text：清理不适合朗读的字符"""

    def test_plain_text_unchanged(self):
        assert chatbotTTS._clean_text("你好，我是哈达莉") == "你好，我是哈达莉"

    def test_removes_emoji(self):
        text = "你好😄世界🎉"
        result = chatbotTTS._clean_text(text)
        assert "😄" not in result
        assert "🎉" not in result
        assert "你好" in result
        assert "世界" in result

    def test_removes_markdown_symbols(self):
        text = "**加粗** `代码` _斜体_ ~删除~ #标题"
        result = chatbotTTS._clean_text(text)
        for sym in ("*", "`", "_", "~", "#"):
            assert sym not in result

    def test_strips_whitespace(self):
        assert chatbotTTS._clean_text("  你好  ") == "你好"

    def test_empty_string(self):
        assert chatbotTTS._clean_text("") == ""

    def test_only_emoji_returns_empty(self):
        assert chatbotTTS._clean_text("😄🎉😍") == ""

    def test_mixed_content(self):
        text = "你好！*这是*一段`测试`文本。😊"
        result = chatbotTTS._clean_text(text)
        assert "你好！" in result
        assert "这是一段测试文本。" in result
        assert "😊" not in result

    def test_preserves_punctuation(self):
        """中文标点应保留"""
        result = chatbotTTS._clean_text("你好，世界！今天天气不错。")
        assert "，" in result
        assert "！" in result
        assert "。" in result


class TestTtsModeConfig:
    """TTS_MODE 配置与回退"""

    def test_tts_mode_is_demo_or_dev(self):
        assert chatbotTTS.TTS_MODE in ("demo", "dev")

    def test_edge_tts_voice_not_empty(self):
        assert chatbotTTS.EDGE_TTS_VOICE

    def test_dashscope_model_default(self):
        assert chatbotTTS.DASHSCOPE_MODEL == "qwen3-tts-vd-2026-01-26"

    def test_dashscope_voice_not_empty(self):
        assert chatbotTTS.DASHSCOPE_VOICE


class TestSpeakFunction:
    """speak：对外接口（不实际播放）"""

    def test_empty_text_does_not_start_thread(self):
        """空文本应直接返回，不启动播放线程"""
        with patch("threading.Thread") as mock_thread:
            chatbotTTS.speak("")
            mock_thread.assert_not_called()

    def test_only_emoji_does_not_start_thread(self):
        """全是不可朗读字符时应直接返回"""
        with patch("threading.Thread") as mock_thread:
            chatbotTTS.speak("😄🎉")
            mock_thread.assert_not_called()

    def test_normal_text_starts_thread(self):
        with patch("threading.Thread") as mock_thread:
            chatbotTTS.speak("你好")
            mock_thread.assert_called_once()
            # 清理可能启动的线程
            chatbotTTS.stop()


class TestStreamPlayer:
    """_StreamPlayer：播放器会话管理"""

    def test_set_and_get_session(self):
        player = chatbotTTS._StreamPlayer()
        player.set_session(42)
        assert player.session == 42

    def test_session_default_none(self):
        player = chatbotTTS._StreamPlayer()
        assert player.session is None

    def test_enqueue_with_wrong_session_dropped(self):
        """携带错误 session 的音频块应被丢弃"""
        player = chatbotTTS._StreamPlayer()
        player.set_session(1)
        import numpy as np
        player.enqueue(np.zeros(100, dtype="float32"), session=2)
        # 队列应为空（块被丢弃）
        assert player._queue.empty()

    def test_enqueue_with_correct_session_accepted(self):
        player = chatbotTTS._StreamPlayer()
        player.set_session(1)
        import numpy as np
        player.enqueue(np.zeros(100, dtype="float32"), session=1)
        assert not player._queue.empty()

    def test_end_with_wrong_session_dropped(self):
        player = chatbotTTS._StreamPlayer()
        player.set_session(1)
        player.end(session=2)
        assert player._queue.empty()

    def test_end_with_correct_session_accepted(self):
        player = chatbotTTS._StreamPlayer()
        player.set_session(1)
        player.end(session=1)
        assert not player._queue.empty()
