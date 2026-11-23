"""单元测试：agent 模式配置 agent/mode_configs/

覆盖 MODE_REGISTRY 结构、DEFAULT_MODE、各模式配置字段完整性。
"""
from backend.agent.mode_configs import DEFAULT_MODE, MODE_REGISTRY


class TestModeRegistry:
    """MODE_REGISTRY：模式注册表"""

    def test_contains_emotion_mode(self):
        assert "emotion" in MODE_REGISTRY

    def test_contains_office_mode(self):
        assert "office" in MODE_REGISTRY

    def test_default_mode_is_emotion(self):
        assert DEFAULT_MODE == "emotion"


class TestEmotionModeConfig:
    """情感陪伴模式配置"""

    def setup_method(self):
        self.cfg = MODE_REGISTRY["emotion"]

    def test_name(self):
        assert self.cfg["name"] == "emotion"

    def test_display_name(self):
        assert self.cfg["display_name"] == "情感陪伴"

    def test_system_prompt_path(self):
        assert self.cfg["system_prompt_path"] == "prompts/system_prompt.txt"

    def test_allowed_tools(self):
        assert self.cfg["allowed_tools"] == ["get_weather", "web_search"]

    def test_time_tool_not_allowed(self):
        """时间能力已迁至 utils/time_utils.py，不再出现在白名单"""
        assert "get_current_time" not in self.cfg["allowed_tools"]

    def test_model_params(self):
        params = self.cfg["model_params"]
        assert "temperature" in params
        assert "max_tokens" in params
        assert params["temperature"] == 0.7


class TestOfficeModeConfig:
    """桌面办公模式配置（预留 stub）"""

    def setup_method(self):
        self.cfg = MODE_REGISTRY["office"]

    def test_name(self):
        assert self.cfg["name"] == "office"

    def test_display_name(self):
        assert self.cfg["display_name"] == "桌面办公"

    def test_allowed_tools_empty(self):
        """办公模式工具待开发，白名单应为空"""
        assert self.cfg["allowed_tools"] == []

    def test_model_params_lower_temperature(self):
        """专业模式温度偏低"""
        assert self.cfg["model_params"]["temperature"] == 0.3


class TestAllModeConfigsIntegrity:
    """所有模式配置字段完整性校验"""

    def test_all_configs_have_required_fields(self):
        required_keys = {"name", "display_name", "system_prompt_path",
                         "allowed_tools", "model_params"}
        for mode_name, cfg in MODE_REGISTRY.items():
            missing = required_keys - set(cfg.keys())
            assert not missing, f"模式 {mode_name} 缺少字段：{missing}"

    def test_name_matches_registry_key(self):
        for key, cfg in MODE_REGISTRY.items():
            assert cfg["name"] == key

    def test_model_params_not_empty(self):
        for mode_name, cfg in MODE_REGISTRY.items():
            assert len(cfg["model_params"]) > 0, f"模式 {mode_name} 的 model_params 为空"
