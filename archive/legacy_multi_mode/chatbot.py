"""
AI 对话模块（桌宠对话门面）

职责：
- 从 .env 读取大模型连接参数（API_KEY / BASE_URL / MODEL），通过工厂模式初始化模型与对话 Agent
- 对外提供 chat_with_model（供 UI 工作线程调用，返回纯回复文本）
- 对外提供 switch_mode（多 agent 模式切换的扩展通道，供后续 UI 右键菜单接入）

P1 过渡说明：本模块是 core 层之上的**兼容适配器**，保留模块级 `_agent` /
`last_partial_reply` 与 `live2d_model` 形参，供旧入口与既有测试使用；
对话逻辑已下沉到 core/facade.py 与 agent/。P3 起 UI 已改为 client/transport，
本适配器仅为兼容保留（tests/test_chatbot.py 依赖其模块级全局）。
live2d 表情动画改由 client/emotion_map.py 承担（按需懒加载，避免 core 依赖 UI）。
"""
from backend.model_factory.factory import ChatModelFactory
from backend.agent.chat_agent import ChatAgent
from backend.core import facade
from utils.logger_handler import logger

# 全局对话 Agent（由 init_api_key_from_env 初始化）
_agent: ChatAgent | None = None

# 出错兜底：流式/处理中途异常时保留已生成的回复，供 UI 优先展示而非空白
last_partial_reply = ""


def _load_env(env_path: str) -> dict:
    """轻量解析 .env（key=value，跳过注释/空行），避免额外引入 python-dotenv"""
    return facade.load_env(env_path)


def init_api_key(api_key: str,
                 base_url: str = "https://api.deepseek.com/v1",
                 model: str = "deepseek-chat") -> None:
    """使用连接参数初始化大模型工厂与对话 Agent（默认情感陪伴模式）"""
    global _agent
    _agent = facade.create_agent(
        api_key=api_key,
        base_url=base_url,
        model=model,
        factory_cls=ChatModelFactory,
    )
    logger.info(f"[chatbot]对话 Agent 初始化完成，当前模式：{_agent.mode_config['name']}")


def init_api_key_from_env(env_path: str = None) -> None:
    """从 .env 读取 API_KEY / BASE_URL / MODEL 并初始化

    函数名保持与旧版一致，main.py 无需改动；env_path 为空时使用项目根目录 .env。
    """
    global _agent
    _agent = facade.create_agent_from_env(env_path=env_path, factory_cls=ChatModelFactory)
    logger.info(f"[chatbot]对话 Agent 初始化完成，当前模式：{_agent.mode_config['name']}")


def chat_with_model(user_input: str, live2d_model=None) -> str:
    """处理一次用户对话，返回剥离情感标签后的纯回复文本（供聊天框显示 / TTS 播报）

    参数：
        user_input   : 用户输入内容
        live2d_model : live2d 模型对象（来自旧 UI），用于情感驱动表情；纯逻辑测试时可传 None
    """
    global last_partial_reply
    if _agent is None:
        raise RuntimeError("对话 Agent 尚未初始化，请先调用 init_api_key_from_env()")

    last_partial_reply = ""
    result = facade.chat(_agent, user_input)
    last_partial_reply = result["reply"]

    # P1 过渡：旧 UI 仍通过本适配器驱动表情；表情映射与播放属于表现层，懒加载避免 core 依赖 UI
    if live2d_model is not None:
        from client.emotion_map import drive_expression
        drive_expression(result["emotion"], live2d_widget=live2d_model)

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
    facade.switch_mode(_agent, mode_name)
    logger.info(f"[chatbot]已切换 agent 模式：{mode_name}")
