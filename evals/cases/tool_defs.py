'''评测用本地假工具：固定返回、不访问网络

工具名与真实工具保持一致（get_weather / web_search），便于断言 ToolMessage.name；
空结果与异常通过参数或独立工具构造。
'''
from langchain_core.tools import tool

WEATHER_SUNNY = "{city}：晴，25 摄氏度，微风。"
WEATHER_EMPTY = "没有查到该城市的天气信息，可以换个城市试试。"
SEARCH_RESULT = "搜索结果：LangGraph 是用于构建有状态智能体的框架。"
SEARCH_EMPTY = "没有找到相关结果，可以换个关键词试试。"
WEATHER_ERROR_TEXT = "查询失败：服务暂时不可用，请稍后再试。"


@tool
def get_weather(city: str = "北京") -> str:
    """查询指定城市的天气（评测假数据，不联网）"""
    if not city or city in ("火星", "不存在"):
        return WEATHER_EMPTY
    return WEATHER_SUNNY.format(city=city)


@tool
def web_search(query: str = "") -> str:
    """按关键词搜索网页（评测假数据，不联网）"""
    if not query or "不存在" in query:
        return SEARCH_EMPTY
    return SEARCH_RESULT


@tool
def broken_weather(city: str = "北京") -> str:
    """查询天气，但总是抛异常（容错评测用）"""
    raise RuntimeError("weather service unavailable")


@tool
def flaky_weather(city: str = "北京") -> str:
    """查询天气，但返回错误文本（容错评测用）"""
    return WEATHER_ERROR_TEXT
