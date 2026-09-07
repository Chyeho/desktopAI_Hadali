"""单元测试：本机时间工具 tools/common/get_time.py

覆盖 get_current_time 工具的输出格式与星期映射。
"""
import re
from datetime import datetime

from tools.common.get_time import _WEEKDAY_CN, get_current_time


class TestWeekdayMapping:
    """_WEEKDAY_CN：中文星期映射"""

    def test_seven_days(self):
        assert len(_WEEKDAY_CN) == 7

    def test_monday_first(self):
        assert _WEEKDAY_CN[0] == "星期一"

    def test_sunday_last(self):
        assert _WEEKDAY_CN[6] == "星期日"

    def test_full_order(self):
        expected = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
        assert _WEEKDAY_CN == expected


class TestGetCurrentTime:
    """get_current_time：langchain 工具"""

    def test_tool_name(self):
        assert get_current_time.name == "get_current_time"

    def test_invoke_returns_string(self):
        result = get_current_time.invoke({})
        assert isinstance(result, str)

    def test_output_format(self):
        """输出应匹配 'YYYY年MM月DD日 HH:MM:SS，星期X'"""
        result = get_current_time.invoke({})
        pattern = r"\d{4}年\d{2}月\d{2}日 \d{2}:\d{2}:\d{2}，星期[一二三四五六日]"
        assert re.match(pattern, result), f"输出格式不符：{result}"

    def test_output_contains_today_weekday(self):
        """输出的星期应与今天一致"""
        result = get_current_time.invoke({})
        today_weekday = _WEEKDAY_CN[datetime.now().weekday()]
        assert today_weekday in result

    def test_output_contains_today_date(self):
        """输出的日期应与今天一致"""
        result = get_current_time.invoke({})
        now = datetime.now()
        expected_date = now.strftime("%Y年%m月%d日")
        assert expected_date in result

    def test_has_description(self):
        """工具应有 docstring 描述"""
        assert get_current_time.description
        assert len(get_current_time.description) > 0
