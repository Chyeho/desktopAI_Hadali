"""单元测试：天气查询工具 tools/common/weather.py

覆盖：
- _WEATHER_CN / _WIND_DIR_CN 数据映射
- get_weather 工具的网络调用（mock urllib）
"""
import json
from unittest.mock import MagicMock, patch

from backend.agent.tools.weather import _WIND_DIR_CN, _WEATHER_CN, get_weather


class TestWeatherCnMapping:
    """_WEATHER_CN：英文天气描述 → 中文"""

    def test_sunny(self):
        assert _WEATHER_CN["Sunny"] == "晴"

    def test_clear(self):
        assert _WEATHER_CN["Clear"] == "晴"

    def test_cloudy(self):
        assert _WEATHER_CN["Cloudy"] == "多云"

    def test_light_rain(self):
        assert _WEATHER_CN["Light rain"] == "小雨"

    def test_heavy_snow(self):
        assert _WEATHER_CN["Heavy snow"] == "大雪"

    def test_mapping_not_empty(self):
        assert len(_WEATHER_CN) > 30


class TestWindDirCnMapping:
    """_WIND_DIR_CN：16 方位风向 → 中文"""

    def test_north(self):
        assert _WIND_DIR_CN["N"] == "北"

    def test_east(self):
        assert _WIND_DIR_CN["E"] == "东"

    def test_south(self):
        assert _WIND_DIR_CN["S"] == "南"

    def test_west(self):
        assert _WIND_DIR_CN["W"] == "西"

    def test_northeast(self):
        assert _WIND_DIR_CN["NE"] == "东北"

    def test_sixteen_directions(self):
        assert len(_WIND_DIR_CN) == 16


class TestGetWeatherTool:
    """get_weather：langchain 工具"""

    def test_tool_name(self):
        assert get_weather.name == "get_weather"

    def test_has_description(self):
        assert get_weather.description
        assert "天气" in get_weather.description

    def test_invoke_success(self):
        """mock 网络请求，验证正常解析"""
        fake_response = {
            "current_condition": [{
                "temp_C": "25",
                "FeelsLikeC": "27",
                "humidity": "60",
                "windspeedKmph": "10",
                "winddir16Point": "NE",
                "lang_zh": [{"value": "晴"}],
                "weatherDesc": [{"value": "Sunny"}],
            }]
        }
        fake_body = json.dumps(fake_response).encode("utf-8")

        mock_resp = MagicMock()
        mock_resp.read.return_value = fake_body
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = get_weather.invoke({"city": "北京"})

        assert "北京" in result
        assert "晴" in result
        assert "25" in result
        assert "27" in result
        assert "60" in result
        assert "东北" in result

    def test_invoke_fallback_to_weatherdesc(self):
        """无 lang_zh 时回退到 weatherDesc"""
        fake_response = {
            "current_condition": [{
                "temp_C": "20",
                "FeelsLikeC": "21",
                "humidity": "50",
                "windspeedKmph": "5",
                "winddir16Point": "N",
                "weatherDesc": [{"value": "Cloudy"}],
            }]
        }
        fake_body = json.dumps(fake_response).encode("utf-8")

        mock_resp = MagicMock()
        mock_resp.read.return_value = fake_body
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = get_weather.invoke({"city": "上海"})

        # Cloudy → 多云
        assert "多云" in result

    def test_invoke_network_error_returns_message(self):
        """网络异常时返回友好错误信息，不抛异常"""
        with patch("urllib.request.urlopen", side_effect=Exception("timeout")):
            result = get_weather.invoke({"city": "北京"})
        assert "天气查询失败" in result
        assert "北京" in result
