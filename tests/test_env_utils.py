"""单元测试：.env 解析 utils/env_utils.py

覆盖注释/空行/引号处理、缺失文件行为与 missing_ok 降级。
"""
import pytest

from utils.env_utils import load_env


class TestLoadEnv:
    def test_parse_basic(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text(
            "API_KEY=sk-test\nBASE_URL=https://api.test.com/v1\n", encoding="utf-8"
        )
        assert load_env(str(env_file)) == {
            "API_KEY": "sk-test",
            "BASE_URL": "https://api.test.com/v1",
        }

    def test_skip_comments_and_empty_lines(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text(
            "# 注释\n\nAPI_KEY=sk-real\n#SKIP=1\nNO_EQUALS\n", encoding="utf-8"
        )
        assert load_env(str(env_file)) == {"API_KEY": "sk-real"}

    def test_strip_quotes_and_spaces(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text(
            'KEY1 = "quoted"\nKEY2=\'single\'\n', encoding="utf-8"
        )
        assert load_env(str(env_file)) == {"KEY1": "quoted", "KEY2": "single"}

    def test_missing_file_raises_by_default(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_env(str(tmp_path / "nope.env"))

    def test_missing_ok_returns_empty(self, tmp_path):
        assert load_env(str(tmp_path / "nope.env"), missing_ok=True) == {}
