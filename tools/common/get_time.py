'''公共工具：获取用户本机当前日期与时间'''
from datetime import datetime

from langchain_core.tools import tool

# 中文星期映射（weekday()：周一=0 ... 周日=6）
_WEEKDAY_CN = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]


@tool
def get_current_time() -> str:
    """查询用户本机当前的日期、时间与星期。当用户询问现在几点、今天星期几、当前日期时间等问题时调用此工具，无需参数。"""
    now = datetime.now()
    return now.strftime("%Y年%m月%d日 %H:%M:%S，") + _WEEKDAY_CN[now.weekday()]
