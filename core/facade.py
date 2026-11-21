'''core 层门面：对外暴露与 UI 无关的对话能力

职责：
- 解析 .env 中的大模型连接参数
- 按 AGENT_ENGINE 选择引擎（graph=LangGraph 陪伴主图，legacy=原 ChatAgent）
- 发起一轮对话、切换 agent 模式

本模块不持有 UI 状态、不 import PySide6 / live2d / httpx / fastapi；
client 由自身保存 agent 引用与部分回复状态（P1 过渡期见根 chatbot.py）。
'''
import os

from agent.chat_agent import ChatAgent, TurnResult
from agent.graph.runner import CompanionGraphAgent
from agent.mode_configs import DEFAULT_MODE, MODE_REGISTRY
from agent.tool_manager import ToolManager
from modelFactory.factory import ChatModelFactory
from utils.path_tool import get_abs_path

DEFAULT_BASE_URL = "https://api.deepseek.com/v1"
DEFAULT_MODEL = "deepseek-chat"
# 默认使用 LangGraph 陪伴主图；legacy 用于一键回滚
DEFAULT_ENGINE = "graph"
VALID_ENGINES = ("graph", "legacy")


def resolve_engine(engine: str = None) -> str:
    """解析引擎名：显式参数 > 环境变量 AGENT_ENGINE > 默认 graph"""
    name = (engine or os.getenv("AGENT_ENGINE") or DEFAULT_ENGINE).strip().lower()
    if name not in VALID_ENGINES:
        raise ValueError(f"未知的 AGENT_ENGINE：{name}，可选：{list(VALID_ENGINES)}")
    return name


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
                 history_file: str = None,
                 engine: str = None):
    """使用连接参数构造对话 Agent（默认 LangGraph 陪伴主图）

    参数：
        factory_cls  : 模型工厂类（便于测试注入；P1 过渡期由根 chatbot.py 传入）
        history_file : 可选的历史持久化文件路径，默认沿用 chat_history/default.json
        engine       : graph / legacy；为空时读 AGENT_ENGINE，再默认 graph
    """
    factory = factory_cls(api_key=api_key, base_url=base_url, model=model)
    engine = resolve_engine(engine)
    if engine == "graph":
        # 沿用情感陪伴模式的生成参数，保证与 legacy 引擎输出风格一致
        params = MODE_REGISTRY[DEFAULT_MODE].get("model_params", {})
        llm = factory.generator(**params)
        return CompanionGraphAgent(llm=llm, history_file=history_file)
    return ChatAgent(
        model_factory=factory,
        tool_manager=ToolManager(),
        history_file=history_file,
    )


def create_agent_from_env(env_path: str = None,
                          factory_cls: type = ChatModelFactory,
                          history_file: str = None,
                          engine: str = None):
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
        engine=engine or env.get("AGENT_ENGINE"),
    )


def chat(agent, user_input: str) -> TurnResult:
    """对指定 agent 发起一轮对话，返回结构化回合结果"""
    if agent is None:
        raise RuntimeError("对话 Agent 尚未初始化，请先调用 create_agent() 或 create_agent_from_env()")
    return agent.chat(user_input)


def switch_mode(agent: ChatAgent, mode_name: str) -> None:
    """切换指定 agent 的模式（提示词 / 工具白名单 / 生成参数随之刷新）"""
    if agent is None:
        raise RuntimeError("对话 Agent 尚未初始化，请先调用 create_agent() 或 create_agent_from_env()")
    agent.set_mode(mode_name)
