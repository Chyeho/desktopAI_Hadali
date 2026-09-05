'''提示词模板加载工具：从本地文件加载提示词，不硬编码在代码中'''
from utils.config_handler import prompts_conf
from utils.path_tool import get_abs_path
from utils.logger_handler import logger


def load_prompt(rel_path: str) -> str:
    '''按相对路径（相对项目根目录）加载提示词文件内容

    供各 agent 模式加载自己的系统提示词使用。
    '''
    abs_path = get_abs_path(rel_path)
    try:
        with open(abs_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        logger.error(f"[load_prompt]加载提示词出错（{rel_path}）：{str(e)}")
        raise e


def load_system_prompt() -> str:
    '''按 yaml 配置（prompts_config.yml 的 system_prompt_path）加载默认系统提示词'''
    try:
        system_prompt_path = prompts_conf["system_prompt_path"]
    except KeyError as e:
        logger.error("[load_system_prompt]在 yaml 配置项中没有 system_prompt_path 配置项")
        raise e

    try:
        with open(get_abs_path(system_prompt_path), "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        logger.error(f"[load_system_prompt]解析系统提示词出错，{str(e)}")
        raise e
