"""单元测试：提示词加载 utils/prompt_loader.py

覆盖 load_prompt / load_system_prompt 的文件读取与异常处理。
"""
import pytest

from utils.prompt_loader import load_prompt, load_system_prompt


class TestLoadPrompt:
    """load_prompt：按相对路径加载提示词文件"""

    def test_load_existing_prompt(self):
        """加载项目自带的 system_prompt.txt"""
        content = load_prompt("prompts/system_prompt.txt")
        assert isinstance(content, str)
        assert len(content) > 0

    def test_load_empty_file(self, tmp_path):
        """加载空文件应返回空字符串"""
        empty = tmp_path / "empty.txt"
        empty.write_text("", encoding="utf-8")
        # load_prompt 需要相对路径 → 用 get_abs_path 拼接，此处直接造临时绝对路径
        from utils.path_tool import get_root_path
        import shutil
        import os
        dst = os.path.join(get_root_path(), "tmp_test_empty_prompt.txt")
        try:
            shutil.copy(str(empty), dst)
            assert load_prompt("tmp_test_empty_prompt.txt") == ""
        finally:
            os.remove(dst)

    def test_load_missing_prompt_raises(self):
        """不存在的提示词文件应抛 FileNotFoundError"""
        with pytest.raises(FileNotFoundError):
            load_prompt("prompts/__not_exist__.txt")


class TestLoadSystemPrompt:
    """load_system_prompt：按 yaml 配置加载默认系统提示词"""

    def test_load_default_system_prompt(self):
        content = load_system_prompt()
        assert isinstance(content, str)
        assert len(content) > 0
