"""单元测试：时间纯函数 utils/time_utils.py

覆盖格式化、用户前缀、AI 后缀、前缀/后缀剥离与幂等性。
"""
from datetime import datetime

from utils.time_utils import (
    DEFAULT_TIME_FORMAT,
    now_str,
    strip_reply_time,
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
