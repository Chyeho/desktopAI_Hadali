"""单元测试：时间纯函数 utils/time_utils.py

覆盖格式化、用户前缀、AI 后缀、前缀/后缀剥离与幂等性。
"""
from datetime import datetime

from utils.time_utils import (
    DEFAULT_TIME_FORMAT,
    TimeMarkerStreamFilter,
    now_str,
    strip_reply_time,
    strip_time_markers,
    strip_user_time,
    with_reply_time,
    with_user_time,
)

FIXED_DT = datetime(2026, 11, 21, 14, 30)


class TestNowStr:
    """now_str：时间格式化"""

    def test_default_format(self):
        assert now_str(FIXED_DT) == "2026-11-21 14:30"
        assert DEFAULT_TIME_FORMAT == "%Y-%m-%d %H:%M"

    def test_custom_format(self):
        assert now_str(FIXED_DT, "%Y年%m月%d日 %H:%M") == "2026年11月21日 14:30"

    def test_uses_current_time_when_dt_missing(self):
        result = now_str()
        assert isinstance(result, str)
        assert len(result) == 16


class TestUserTime:
    """用户消息时间前缀"""

    def test_add_prefix(self):
        assert with_user_time("你好", FIXED_DT) == "[2026-11-21 14:30] 你好"

    def test_strip_prefix(self):
        assert strip_user_time("[2026-11-21 14:30] 你好") == "你好"

    def test_strip_without_prefix(self):
        assert strip_user_time("你好") == "你好"

    def test_idempotent(self):
        once = with_user_time("你好", FIXED_DT)
        twice = with_user_time(once, FIXED_DT)
        assert once == twice


class TestReplyTime:
    """AI 回复时间后缀"""

    def test_add_suffix(self):
        assert with_reply_time("我在呢", FIXED_DT) == "我在呢 [2026-11-21 14:30]"

    def test_strip_suffix(self):
        assert strip_reply_time("我在呢 [2026-11-21 14:30]") == "我在呢"

    def test_strip_without_suffix(self):
        assert strip_reply_time("我在呢") == "我在呢"

    def test_strip_keeps_inner_brackets(self):
        text = "刚才[14:30]在忙 [2026-11-21 14:30]"
        assert strip_reply_time(text) == "刚才[14:30]在忙"

    def test_idempotent(self):
        once = with_reply_time("我在呢", FIXED_DT)
        twice = with_reply_time(once, FIXED_DT)
        assert once == twice

    def test_empty_reply(self):
        assert strip_reply_time("") == ""


class TestStripTimeMarkers:
    """strip_time_markers：清除任意位置的时间标记（模型复述兜底）"""

    def test_strip_trailing_marker(self):
        assert strip_time_markers("我在呢 [2026-11-21 14:30]") == "我在呢"

    def test_strip_inner_marker(self):
        assert strip_time_markers("现在是 [2026-11-21 14:30]，该吃饭啦。") == "现在是，该吃饭啦。"

    def test_strip_multiple_markers(self):
        text = "[2026-11-21 14:30] 早上好 [2026-11-21 14:31] 今天也要开心"
        assert strip_time_markers(text) == "早上好 今天也要开心"

    def test_keep_non_time_brackets(self):
        assert strip_time_markers("[emotion:happy] 好呀") == "[emotion:happy] 好呀"

    def test_empty_text(self):
        assert strip_time_markers("") == ""


class TestTimeMarkerStreamFilter:
    """TimeMarkerStreamFilter：流式删除时间标记（含节点最终消息补发）"""

    def test_remove_tail_marker_single_chunk(self):
        filter_ = TimeMarkerStreamFilter()
        assert filter_.feed("我在呢 [2026-11-21 14:30]") == "我在呢"
        assert filter_.flush() == ""

    def test_remove_marker_split_across_chunks(self):
        filter_ = TimeMarkerStreamFilter()
        assert filter_.feed("我在呢 [2026-11-") == "我在呢"
        assert filter_.feed("21 14:30]") == ""
        assert filter_.flush() == ""

    def test_keep_normal_text_with_bracket(self):
        filter_ = TimeMarkerStreamFilter()
        assert filter_.feed("结果[1] 很好") == "结果[1] 很好"
        assert filter_.flush() == ""

    def test_lone_bracket_flushed(self):
        filter_ = TimeMarkerStreamFilter()
        assert filter_.feed("看这里 [") == "看这里"
        assert filter_.flush() == " ["

    def test_remove_inner_marker(self):
        filter_ = TimeMarkerStreamFilter()
        output = filter_.feed("现在是 [2026-11-21 14:30]，吃饭啦")
        assert "2026" not in output
        assert "吃饭啦" in output
