'''core 层门面：对外暴露与 UI 无关的对话能力

职责：
- 解析 .env 中的大模型连接参数
- 通过模型工厂构造 ChatAgent
- 发起一轮对话、切换 agent 模式

本模块不持有 UI 状态、不 import PySide6 / live2d / httpx / fastapi；
client 由自身保存 agent 引用与部分回复状态（P1 过渡期见根 chatbot.py）。
'''
from agent.chat_agent import ChatAgent, TurnResult
from agent.tool_manager import ToolManager
from modelFactory.factory import ChatModelFactory
from utils.path_tool import get_abs_path

DEFAULT_BASE_URL = "https://api.deepseek.com/v1"
DEFAULT_MODEL = "deepseek-chat"


def load_env(env_path: str) -> dict:
    """轻量解析 .env（key=value，跳过注释/空行），避免额外引入 python-dotenv"""
    env = {}
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def create_agent(api_key: str,
                 base_url: str = DEFAULT_BASE_URL,
                 model: str = DEFAULT_MODEL,
                 factory_cls: type = ChatModelFactory,
                 history_file: str = None) -> ChatAgent:
    """使用连接参数构造对话 Agent（默认情感陪伴模式）

    参数：
        factory_cls  : 模型工厂类（便于测试注入；P1 过渡期由根 chatbot.py 传入）
        history_file : 可选的历史持久化文件路径，默认沿用 chat_history/default.json
    """
    factory = factory_cls(api_key=api_key, base_url=base_url, model=model)
    return ChatAgent(
        model_factory=factory,
        tool_manager=ToolManager(),
        history_file=history_file,
    )


def create_agent_from_env(env_path: str = None,
                          factory_cls: type = ChatModelFactory,
                          history_file: str = None) -> ChatAgent:
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


def chat(agent: ChatAgent, user_input: str) -> TurnResult:
    """对指定 agent 发起一轮对话，返回结构化回合结果"""
    if agent is None:
        raise RuntimeError("对话 Agent 尚未初始化，请先调用 create_agent() 或 create_agent_from_env()")
    return agent.chat(user_input)


def switch_mode(agent: ChatAgent, mode_name: str) -> None:
    """切换指定 agent 的模式（提示词 / 工具白名单 / 生成参数随之刷新）"""
    if agent is None:
        raise RuntimeError("对话 Agent 尚未初始化，请先调用 create_agent() 或 create_agent_from_env()")
    agent.set_mode(mode_name)
