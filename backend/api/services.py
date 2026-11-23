'''服务容器：组装 core 层能力，供路由依赖注入与测试替换

路由只依赖本类的这几个方法/属性：lock / chat / stream_chat / model_name / turns_file，
测试可注入同名鸭子类型。
'''
from fastapi import Request

from backend.agent.turn import TurnResult
from backend.core import facade
from backend.core.session import SessionManager
from utils.path_tool import get_abs_path

SERVER_VERSION = "0.1.0"
# 单引擎（LangGraph 陪伴主图）：协议中的 mode 字段固定为该值
AGENT_MODE = "emotion"


def _detect_model() -> str:
    '''读取 .env 中配置的模型名（读不到时为空串，不影响启动）'''
    try:
        return facade.load_env(get_abs_path(".env")).get("MODEL", "")
    except Exception:
        return ""


class Services:
    '''服务集合：会话管理 + 指标文件'''

    def __init__(self, sessions: SessionManager = None, model_name: str = None,
                 turns_file: str = None):
        self.sessions = sessions or SessionManager()
        self.model_name = _detect_model() if model_name is None else model_name
        self.turns_file = turns_file

    def lock(self, session_id: str):
        '''该会话的异步锁（同会话串行）'''
        return self.sessions.get_lock(session_id)

    def chat(self, session_id: str, text: str) -> TurnResult:
        '''取会话 agent 并执行一轮对话'''
        return self.sessions.get_agent(session_id).chat(text)

    def stream_chat(self, session_id: str, text: str):
        '''返回同步增量生成器：("delta", 文本) / ("done", TurnResult)

        主图引擎均支持流式；服务未实现时返回 None，路由退回一次性下发。
        '''
        stream = getattr(self.sessions.get_agent(session_id), "stream_chat", None)
        if not callable(stream):
            return None
        return stream(text, session_id=session_id)


def get_services(request: Request) -> Services:
    '''FastAPI 依赖：从 app.state 取服务容器（测试通过 create_app(services=...) 替换）'''
    return request.app.state.services
