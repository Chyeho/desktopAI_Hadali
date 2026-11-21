'''服务容器：组装 core 层能力，供路由依赖注入与测试替换

路由只依赖本类的这几个方法/属性：lock / chat / stream_chat / list_modes /
set_mode / current_mode / model_name / turns_file，测试可注入同名鸭子类型。
'''
from fastapi import Request

from agent.chat_agent import TurnResult
from agent.mode_configs import DEFAULT_MODE, MODE_REGISTRY
from core import facade
from core.session import SessionManager
from utils.path_tool import get_abs_path

SERVER_VERSION = "0.1.0"


def _detect_model() -> str:
    '''读取 .env 中配置的模型名（读不到时为空串，不影响启动）'''
    try:
        return facade.load_env(get_abs_path(".env")).get("MODEL", "")
    except Exception:
        return ""


class Services:
    '''服务集合：会话管理 + 进程级当前模式 + 指标文件'''

    def __init__(self, sessions: SessionManager = None, model_name: str = None,
                 current_mode: str = DEFAULT_MODE, turns_file: str = None):
        self.sessions = sessions or SessionManager()
        self.model_name = _detect_model() if model_name is None else model_name
        self.current_mode = current_mode
        self.turns_file = turns_file

    def lock(self, session_id: str):
        '''该会话的异步锁（同会话串行）'''
        return self.sessions.get_lock(session_id)

    def _resolve_agent(self, session_id: str, mode: str = None):
        '''取会话 agent，必要时切换到目标模式'''
        agent = self.sessions.get_agent(session_id)
        target = mode or self.current_mode
        current = (agent.mode_config or {}).get("name")
        if target and current != target:
            agent.set_mode(target)
        return agent

    def chat(self, session_id: str, text: str, mode: str = None) -> TurnResult:
        '''取会话 agent（必要时切换模式）并执行一轮对话'''
        return self._resolve_agent(session_id, mode).chat(text)

    def stream_chat(self, session_id: str, text: str, mode: str = None):
        '''返回同步增量生成器：("delta", 文本) / ("done", TurnResult)

        引擎不支持流式（如 legacy ChatAgent）时返回 None，路由退回一次性下发。
        '''
        agent = self._resolve_agent(session_id, mode)
        stream = getattr(agent, "stream_chat", None)
        if not callable(stream):
            return None
        return stream(text, session_id=session_id)

    def list_modes(self) -> list[dict]:
        return [
            {"name": name, "display_name": cfg.get("display_name", "")}
            for name, cfg in MODE_REGISTRY.items()
        ]

    def set_mode(self, name: str) -> None:
        '''切换进程级当前模式；已存在的 agent 在下一轮对话时惰性跟随'''
        if name not in MODE_REGISTRY:
            raise ValueError(f"未知的 agent 模式：{name}")
        self.current_mode = name


def get_services(request: Request) -> Services:
    '''FastAPI 依赖：从 app.state 取服务容器（测试通过 create_app(services=...) 替换）'''
    return request.app.state.services
