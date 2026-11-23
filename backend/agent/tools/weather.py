'''公共工具：天气查询（wttr.in 免费接口，无需 API Key，标准库 urllib 实现）'''
import json
import urllib.parse
import urllib.request

from langchain_core.tools import tool

from utils.logger_handler import logger

# wttr.in 天气接口：j1 返回 JSON，lang=zh 返回中文天气描述
_WTTR_URL = "https://wttr.in/{city}?format=j1&lang=zh"
_TIMEOUT = 10  # 请求超时（秒）

# wttr.in 部分天气现象无中文翻译（lang_zh 仍返回英文），补充常见英文描述的中文映射
_WEATHER_CN = {
    "Sunny": "晴", "Clear": "晴", "Partly cloudy": "局部多云", "Cloudy": "多云",
    "Overcast": "阴", "Mist": "薄雾", "Fog": "雾", "Freezing fog": "冻雾",
    "Haze": "霾", "Smoky haze": "烟霾", "Dust": "沙尘",
    "Patchy rain possible": "局部可能有雨", "Patchy rain nearby": "附近有零星降雨",
    "Patchy snow possible": "局部可能有雪", "Patchy sleet possible": "局部可能有雨夹雪",
    "Patchy freezing drizzle possible": "局部可能有冻毛毛雨",
    "Thundery outbreaks possible": "可能有雷阵雨",
    "Blowing snow": "吹雪", "Blizzard": "暴风雪",
    "Patchy light drizzle": "零星毛毛雨", "Light drizzle": "小毛毛雨",
    "Freezing drizzle": "冻毛毛雨", "Heavy freezing drizzle": "强冻毛毛雨",
    "Patchy light rain": "零星小雨", "Light rain": "小雨",
    "Moderate rain at times": "间歇中雨", "Moderate rain": "中雨",
    "Heavy rain at times": "间歇大雨", "Heavy rain": "大雨",
    "Light freezing rain": "小冻雨", "Moderate or heavy freezing rain": "中到大冻雨",
    "Light sleet": "小雨夹雪", "Moderate or heavy sleet": "中到大雨夹雪",
    "Patchy light snow": "零星小雪", "Light snow": "小雪",
    "Patchy moderate snow": "零星中雪", "Moderate snow": "中雪",
    "Patchy heavy snow": "零星大雪", "Heavy snow": "大雪",
    "Ice pellets": "冰粒", "Light rain shower": "小阵雨",
    "Moderate or heavy rain shower": "中到大阵雨", "Torrential rain shower": "暴雨",
    "Light sleet showers": "小阵雨夹雪", "Moderate or heavy sleet showers": "中到大阵雨夹雪",
    "Light snow showers": "小阵雪", "Moderate or heavy snow showers": "中到大阵雪",
    "Light showers of ice pellets": "小阵冰粒",
    "Moderate or heavy showers of ice pellets": "中到大阵冰粒",
    "Patchy light rain with thunder": "零星小雨伴雷",
    "Moderate or heavy rain with thunder": "中到大雨伴雷",
    "Patchy light snow with thunder": "零星小雪伴雷",
    "Moderate or heavy snow with thunder": "中到大雪伴雷",
}

# 16 方位风向英文缩写 → 中文
_WIND_DIR_CN = {
    "N": "北", "NNE": "东北偏北", "NE": "东北", "ENE": "东北偏东",
    "E": "东", "ESE": "东南偏东", "SE": "东南", "SSE": "东南偏南",
    "S": "南", "SSW": "西南偏南", "SW": "西南", "WSW": "西南偏西",
    "W": "西", "WNW": "西北偏西", "NW": "西北", "NNW": "西北偏北",
}


@tool
def get_weather(city: str) -> str:
    """查询指定城市的实时天气情况（天气状况、气温、体感温度、湿度、风力等）。
    当用户询问某地天气、气温、是否下雨等问题时调用。
    参数 city 为城市名称，可传中文，如“北京”“上海”“广州”。
    """
    try:
        url = _WTTR_URL.format(city=urllib.parse.quote(city))
        # wttr.in 对非 curl UA 可能返回 HTML，伪装成 curl 以确保返回 JSON
        req = urllib.request.Request(url, headers={"User-Agent": "curl/8.0"})
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        current = data["current_condition"][0]
        # 天气描述：优先中文（lang_zh），再查补充映射，最后回退英文原文
        desc = ""
        if current.get("lang_zh"):
            desc = current["lang_zh"][0].get("value", "")
        if not desc:
            desc = current.get("weatherDesc", [{}])[0].get("value", "")
        desc = _WEATHER_CN.get(desc, desc)
        wind_dir = _WIND_DIR_CN.get(current.get("winddir16Point", ""), current.get("winddir16Point", ""))

        return (
            f"{city}当前天气：{desc}，"
            f"气温 {current.get('temp_C')}℃（体感 {current.get('FeelsLikeC')}℃），"
            f"湿度 {current.get('humidity')}%，"
            f"风速 {current.get('windspeedKmph')}km/h（{wind_dir}风）。"
        )
    except Exception as e:
        logger.error(f"[get_weather]天气查询失败，city={city}，原因：{str(e)}")
        return f"天气查询失败（{city}）：{str(e)}。请稍后重试或换个城市试试。"
