'''感知门控：判断本轮用户输入是否要进入游戏子图

优先使用 langgraph-jev-router 的 FakeJev 本地规则后端（与 root_graph.py 用法一致）；
导入失败或调用异常时回落到本地关键词规则，保证主图永远可运行。

注意：FakeJev 关键词单命中置信度为 0.70 + 抖动，恰好 0.70 时不满足 > 0.7，
因此游戏关键词刻意保留包含关系（如「五子棋」与「棋」），让常见说法至少命中 2 个。
'''
import re

from langchain_core.messages import BaseMessage, HumanMessage

from agent.graph.state import AgentState
from utils.logger_handler import logger

# 游戏路由阈值：严格大于 0.7 才进入游戏子图
GAME_CONFIDENCE_THRESHOLD = 0.7
GAME_ROUTE = "game"
CHAT_ROUTE = "chat"

# 游戏意图关键词：存在包含关系，确保常见说法至少命中两个
GAME_KEYWORDS = (
    "玩游戏",
    "玩一局",
    "来一局",
    "来一盘",
    "下一盘",
    "下盘",
    "下棋",
    "五子棋",
    "象棋",
    "围棋",
    "一局",
    "棋",
    "game",
)

# 用户消息可能带有 agent 注入的时间前缀（[YYYY-MM-DD HH:MM]），判断意图前先剥离
_TIME_PREFIX_RE = re.compile(r"^\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}\]\s*")

_backend = None


def _get_backend():
    '''懒加载 FakeJev 后端；导入失败时抛异常，由 decide_route 回落关键词规则'''
    global _backend
    if _backend is None:
        from langgraph_jev_router import FakeJev
        from langgraph_jev_router import settings as jev_settings

        # chat 不配置关键词：避免用户话术中的普通词稀释游戏置信度，
        # 无命中时 FakeJev 会返回低置信度，门控自然会回落到 chat。
        _backend = FakeJev(rules={GAME_ROUTE: GAME_KEYWORDS})
        jev_settings.configure(backend=_backend)
        logger.info(f"[graph.perception]FakeJev 后端已就绪，游戏关键词：{list(GAME_KEYWORDS)}")
    return _backend


def _keyword_route(text: str) -> tuple[str, float]:
    '''本地关键词兜底：命中两个及以上关键词才视为游戏请求'''
    lowered = text.lower()
    hits = sum(1 for keyword in GAME_KEYWORDS if keyword in lowered)
    if hits >= 2:
        return GAME_ROUTE, 0.78
    return CHAT_ROUTE, 0.0


def decide_route(text: str) -> tuple[str, float]:
    '''返回 (route, confidence)，route 只会是 game / chat'''
    cleaned = (text or "").strip()
    if not cleaned:
        return CHAT_ROUTE, 0.0

    try:
        from langgraph_jev_router.types import ChoiceRequest

        decision = _get_backend().choose(
            ChoiceRequest(
                question="判断用户这句话是否在请求玩一局游戏。",
                options=(
                    (GAME_ROUTE, "发起游戏对局，例如下棋、五子棋、来一局游戏"),
                    (CHAT_ROUTE, "普通聊天、情绪陪伴、提问或需要工具完成的任务"),
                ),
                state={"request": cleaned},
                model="fake-jev",
            )
        )
        route = decision.route if decision.route in (GAME_ROUTE, CHAT_ROUTE) else CHAT_ROUTE
        confidence = float(decision.confidence)
    except Exception as e:
        logger.warning(f"[graph.perception]FakeJev 判断失败，回落关键词规则：{str(e)}")
        return _keyword_route(cleaned)

    if route == GAME_ROUTE and confidence > GAME_CONFIDENCE_THRESHOLD:
        return GAME_ROUTE, confidence
    return CHAT_ROUTE, confidence


def _last_user_text(state: AgentState) -> str:
    '''取最近一条用户消息文本（去掉时间前缀），没有则回退最后一条消息'''
    messages: list[BaseMessage] = list(state.get("messages") or [])
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            content = message.content if isinstance(message.content, str) else str(message.content)
            return _TIME_PREFIX_RE.sub("", content)
    if messages:
        content = messages[-1].content
        return content if isinstance(content, str) else str(content)
    return ""


def perception_node(state: AgentState) -> dict:
    '''门控节点：只写路由字段，不写 messages、不调工具'''
    text = _last_user_text(state)
    route, confidence = decide_route(text)
    logger.info(f"[graph.perception]路由判断：{route}（置信度 {confidence:.2f}）")
    if route == GAME_ROUTE:
        return {"route": GAME_ROUTE, "game_request": text}
    return {"route": CHAT_ROUTE, "game_request": None}
