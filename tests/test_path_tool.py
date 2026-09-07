"""单元测试：路径工具 utils/path_tool.py

覆盖 get_root_path / get_abs_path 的路径拼接行为。
"""
import os

from utils.path_tool import get_abs_path, get_root_path


class TestGetRootPath:
    """get_root_path：返回项目根目录"""

    def test_returns_absolute_path(self):
        root = get_root_path()
        assert os.path.isabs(root)

    def test_contains_utils_dir(self):
        """根目录下应存在 utils 目录（间接验证根路径正确）"""
        root = get_root_path()
        assert os.path.isdir(os.path.join(root, "utils"))

    def test_contains_main_py(self):
        root = get_root_path()
        assert os.path.isfile(os.path.join(root, "main.py"))


class TestGetAbsPath:
    """get_abs_path：相对路径 → 绝对路径"""

    def test_single_segment(self):
        abs_path = get_abs_path("prompts")
        assert os.path.isabs(abs_path)
        assert abs_path.endswith(os.sep + "prompts")

    def test_multi_segment(self):
        abs_path = get_abs_path("config" + os.sep + "prompts_config.yml")
        assert os.path.isabs(abs_path)
        assert abs_path.endswith(os.path.join("config", "prompts_config.yml"))

    def test_points_to_existing_file(self):
        """拼接出的路径应指向真实存在的文件"""
        abs_path = get_abs_path("config" + os.sep + "prompts_config.yml")
        assert os.path.isfile(abs_path)

    def test_root_consistency(self):
        """get_abs_path 的前缀应与 get_root_path 一致"""
        abs_path = get_abs_path("foo")
        assert abs_path == os.path.join(get_root_path(), "foo")
