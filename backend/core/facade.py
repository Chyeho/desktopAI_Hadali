'''core 层门面：对外暴露与 UI 无关的对话能力

职责：
- 解析 .env 中的大模型连接参数
- 构造 LangGraph 陪伴主图并发起一轮对话

本模块不持有 UI 状态、不 import PySide6 / live2d / httpx / fastapi。
'''
from backend.agent.turn import TurnResult
from backend.agent.graph.config import GRAPH_MODEL_PARAMS
from backend.agent.graph.runner import CompanionGraphAgent
from backend.model_factory.factory import ChatModelFactory
from utils.env_utils import load_env
from utils.path_tool import get_abs_path

DEFAULT_BASE_URL = "https://api.deepseek.com/v1"
DEFAULT_MODEL = "deepseek-chat"


def create_agent(api_key: str,
                 base_url: str = DEFAULT_BASE_URL,
                 model: str = DEFAULT_MODEL,
                 factory_cls: type = ChatModelFactory,
                 history_file: str = None) -> CompanionGraphAgent:
    """使用连接参数构造陪伴主图 Agent

    参数：
        factory_cls  : 模型工厂类（便于测试注入）
        history_file : 可选的历史持久化文件路径，默认沿用 chat_history/default.json
    """
    factory = factory_cls(api_key=api_key, base_url=base_url, model=model)
    llm = factory.generator(**GRAPH_MODEL_PARAMS)
    return CompanionGraphAgent(llm=llm, history_file=history_file)


def create_agent_from_env(env_path: str = None,
                          factory_cls: type = ChatModelFactory,
                          history_file: str = None) -> CompanionGraphAgent:
    """从 .env 读取 API_KEY / BASE_URL / MODEL 并构造对话 Agent"""
    if env_path is None:
        env_path = get_abs_path(".env")
    env = load_env(env_path)

    api_key = env.get("API_KEY", "")
    if not api_key:
        raise ValueError(f"未在 {env_path} 中找到有效的 API_KEY")
    base_url = env.get("BASE_URL", DEFAULT_BASE_URL)
    model = env.get("MODEL", DEFAULT_MODEL)

    return create_agent(
        api_key=api_key,
        base_url=base_url,
        model=model,
        factory_cls=factory_cls,
        history_file=history_file,
    )


def chat(agent, user_input: str) -> TurnResult:
    """对指定 agent 发起一轮对话，返回结构化回合结果"""
    if agent is None:
        raise RuntimeError("对话 Agent 尚未初始化，请先调用 create_agent() 或 create_agent_from_env()")
    return agent.chat(user_input)
