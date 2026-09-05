"""
AI 对话模块（桌宠对话门面）

职责：
- 从 .env 读取大模型连接参数（API_KEY / BASE_URL / MODEL），通过工厂模式初始化模型与对话 Agent
- 对外提供 chat_with_model（供 UI 工作线程调用，返回纯回复文本）
- 对外提供 switch_mode（多 agent 模式切换的扩展通道，供后续 UI 右键菜单接入）

核心逻辑均在 agent/ 下：
- 模型工厂 modelFactory/factory.py（langchain ChatOpenAI，支持任意 OpenAI 协议模型）
- 工具调用 / 历史持久化 / JSON 解析 / 情感驱动 agent/chat_agent.py
"""
import os

from modelFactory.factory import ChatModelFactory
from agent.chat_agent import ChatAgent
from agent.tool_manager import ToolManager
from utils.logger_handler import logger

# 全局对话 Agent（由 init_api_key_from_env 初始化）
_agent: ChatAgent | None = None

# 出错兜底：流式/处理中途异常时保留已生成的回复，供 UI 优先展示而非空白
last_partial_reply = ""

# 本模块所在目录（用于定位 .env，保证任意工作目录启动都能找到）
_MODULE_DIR = os.path.dirname(os.path.abspath(__file__))


def _load_env(env_path: str) -> dict:
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


def init_api_key(api_key: str,
                 base_url: str = "https://api.deepseek.com/v1",
                 model: str = "deepseek-chat") -> None:
    """使用连接参数初始化大模型工厂与对话 Agent（默认情感陪伴模式）"""
    global _agent
    factory = ChatModelFactory(api_key=api_key, base_url=base_url, model=model)
    _agent = ChatAgent(model_factory=factory, tool_manager=ToolManager())
    logger.info(f"[chatbot]对话 Agent 初始化完成，当前模式：{_agent.mode_config['name']}")


def init_api_key_from_env(env_path: str = None) -> None:
    """从 .env 读取 API_KEY / BASE_URL / MODEL 并初始化

    函数名保持与旧版一致，main.py 无需改动。
    """
    if env_path is None:
        env_path = os.path.join(_MODULE_DIR, ".env")
    env = _load_env(env_path)

    api_key = env.get("API_KEY", "")
    if not api_key:
        raise ValueError(f"未在 {env_path} 中找到有效的 API_KEY")
    base_url = env.get("BASE_URL", "https://api.deepseek.com/v1")
    model = env.get("MODEL", "deepseek-chat")

    init_api_key(api_key=api_key, base_url=base_url, model=model)


def chat_with_model(user_input: str, live2d_model=None) -> str:
    """处理一次用户对话，返回剥离情感标签后的纯回复文本（供聊天框显示 / TTS 播报）

    参数：
        user_input   : 用户输入内容
        live2d_model : live2d 模型对象（来自 UI），用于情感驱动表情；纯逻辑测试时可传 None
    """
    global last_partial_reply
    if _agent is None:
        raise RuntimeError("对话 Agent 尚未初始化，请先调用 init_api_key_from_env()")

    last_partial_reply = ""
    result = _agent.chat(user_input, live2d_model=live2d_model)
    last_partial_reply = result["reply"]
    logger.info(
        f"[chatbot]本轮回复完成（情感：{result['emotion']}）：{result['reply'][:50]}"
        f"{'...' if len(result['reply']) > 50 else ''}"
    )
    return result["reply"]


def switch_mode(mode_name: str) -> None:
    """切换 agent 模式（扩展通道：后续 UI 右键菜单 / 对话指令接入）

    切换后系统提示词、工具白名单、模型生成参数均按新模式配置刷新。
    """
    if _agent is None:
        raise RuntimeError("对话 Agent 尚未初始化，请先调用 init_api_key_from_env()")
    _agent.set_mode(mode_name)
    logger.info(f"[chatbot]已切换 agent 模式：{mode_name}")
