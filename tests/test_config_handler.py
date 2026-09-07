"""单元测试：配置管理 utils/config_handler.py

覆盖 load_prompts_config 加载 yaml 配置的行为。
"""
import os

import pytest

from utils.config_handler import load_prompts_config, prompts_conf


class TestLoadPromptsConfig:
    """load_prompts_config：加载 yaml 配置文件"""

    def test_default_config_loaded(self):
        """模块级 prompts_conf 应已加载默认配置"""
        assert isinstance(prompts_conf, dict)
        assert "system_prompt_path" in prompts_conf

    def test_default_config_value(self):
        """默认配置的 system_prompt_path 指向 prompts/system_prompt.txt"""
        assert prompts_conf["system_prompt_path"] == "prompts/system_prompt.txt"

    def test_load_with_custom_path(self, tmp_path):
        """传入自定义 yaml 文件路径"""
        cfg = tmp_path / "custom.yml"
        cfg.write_text("key: value\nnum: 42\n", encoding="utf-8")
        result = load_prompts_config(config_path=str(cfg))
        assert result["key"] == "value"
        assert result["num"] == 42

    def test_load_nested_yaml(self, tmp_path):
        """加载含嵌套结构的 yaml"""
        cfg = tmp_path / "nested.yml"
        cfg.write_text("outer:\n  inner: data\nlist:\n  - a\n  - b\n", encoding="utf-8")
        result = load_prompts_config(config_path=str(cfg))
        assert result["outer"]["inner"] == "data"
        assert result["list"] == ["a", "b"]

    def test_load_missing_file_raises(self, tmp_path):
        """文件不存在时应抛 FileNotFoundError"""
        missing = tmp_path / "nope.yml"
        with pytest.raises(FileNotFoundError):
            load_prompts_config(config_path=str(missing))
