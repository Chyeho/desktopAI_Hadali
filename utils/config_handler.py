'''配置信息管理工具'''
import yaml
from utils.path_tool import get_abs_path


def load_prompts_config(
        config_path: str = get_abs_path("config/prompts_config.yml"),
        encoding: str = "utf-8",
):
    '''加载 prompts 配置信息文件（yaml）'''
    with open(config_path, "r", encoding=encoding) as f:
        return yaml.load(f, Loader=yaml.FullLoader)


prompts_conf = load_prompts_config()
