"""单元测试：情绪标签解析与流式过滤 agent/graph/emotion.py"""
from backend.agent.graph.emotion import EmotionStreamFilter, parse_emotion_tag


class TestParseEmotionTag:
    """parse_emotion_tag"""

    def test_valid_tag(self):
        emotion, reply = parse_emotion_tag("[emotion:happy]\n今天真开心")
        assert emotion == "happy"
        assert reply == "今天真开心"

    def test_tag_with_equals_and_spaces(self):
        emotion, reply = parse_emotion_tag("  [emotion = shy]  你好呀")
        assert emotion == "shy"
        assert reply == "你好呀"

    def test_missing_tag_falls_back_to_neutral(self):
        emotion, reply = parse_emotion_tag("今天有点累")
        assert emotion == "neutral"
        assert reply == "今天有点累"

    def test_unknown_tag_falls_back_to_neutral(self):
        emotion, reply = parse_emotion_tag("[emotion:unknown_xx]\n嗯嗯")
        assert emotion == "neutral"
        assert reply == "嗯嗯"

    def test_empty_content(self):
        assert parse_emotion_tag("") == ("neutral", "")

    def test_lowercase_tag(self):
        emotion, reply = parse_emotion_tag("[emotion:SAD]\n有点难过")
        assert emotion == "sad"
        assert reply == "有点难过"


class TestEmotionStreamFilter:
    """EmotionStreamFilter 流式剥离"""

    def test_tag_in_one_token(self):
        filter_ = EmotionStreamFilter()
        assert filter_.feed("[emotion:happy]\n今天真好") == "今天真好"
        assert filter_.feed("呀") == "呀"
        assert filter_.flush() == ""

    def test_tag_split_across_tokens(self):
        filter_ = EmotionStreamFilter()
        outputs = [
            filter_.feed("[emot"),
            filter_.feed("ion:hap"),
            filter_.feed("py]\n"),
            filter_.feed("你好"),
        ]
        assert "".join(outputs) == "你好"

    def test_plain_text_passthrough(self):
        filter_ = EmotionStreamFilter()
        outputs = [
            filter_.feed("今天"),
            filter_.feed("也"),
            filter_.feed("要开心"),
        ]
        assert "".join(outputs) == "今天也要开心"

    def test_non_tag_bracket_text(self):
        filter_ = EmotionStreamFilter()
        outputs = [filter_.feed("[笑哭]"), filter_.feed(" 哈哈")]
        assert "".join(outputs) == "[笑哭] 哈哈"

    def test_leading_space_before_plain_text(self):
        filter_ = EmotionStreamFilter()
        assert filter_.feed(" 你好呀") == " 你好呀"

    def test_flush_returns_pending_plain_text(self):
        filter_ = EmotionStreamFilter()
        assert filter_.feed("   ") == ""
        assert filter_.flush() == "   "

    def test_flush_after_tag_returns_empty(self):
        filter_ = EmotionStreamFilter()
        assert filter_.feed("[emotion:calm]") == ""
        assert filter_.flush() == ""
