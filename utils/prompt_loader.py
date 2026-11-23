'''提示词模板加载工具：统一从 config/prompts_config.yml 取路径，不硬编码在业务代码中'''
from utils.config_handler import prompts_conf
from utils.path_tool import get_abs_path
from utils.logger_handler import logger


def load_prompt(rel_path: str) -> str:
    '''按相对路径（相对项目根目录）加载提示词文件内容'''
    abs_path = get_abs_path(rel_path)
    try:
        with open(abs_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        logger.error(f"[load_prompt]加载提示词出错（{rel_path}）：{str(e)}")
        raise e


def load_prompt_by_config(key: str) -> str:
    '''按 prompts_config.yml 中的键加载提示词路径

    统一的“配置键 → 提示词文件”入口，避免各模块自行硬编码路径。
    '''
    try:
        rel_path = prompts_conf[key]
    except KeyError as e:
        logger.error(f"[load_prompt_by_config]yaml 配置项中缺少 {key}")
        raise e
    return load_prompt(rel_path)


def load_system_prompt() -> str:
    '''加载 legacy 情感陪伴提示词（system_prompt_path）'''
    return load_prompt_by_config("system_prompt_path")


def load_graph_prompt() -> str:
    '''加载 LangGraph 陪伴主图提示词（graph_system_prompt_path）'''
    return load_prompt_by_config("graph_system_prompt_path")
