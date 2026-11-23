'''M2 路由用例：游戏意图与反例

所有用例使用全新 thread_id 独立运行；脚本化 LLM 只提供固定回复，
因此断言聚焦 route 与最终回复是否命中游戏拒绝词。
'''
from evals.keywords import GAME_REFUSAL_KEYWORDS

ROUTING_CASES = [
    {
        "id": "routing_game_explicit_01",
        "category": "routing",
        "description": "明确请求来一局五子棋 → game",
        "input": "陪我玩一局五子棋吧",
        "scripted_reply": "我还在学习下棋呢，暂时还不能陪你玩，等我练好了就来。",
        "expect": {
            "route": "game",
            "final_contains_any": GAME_REFUSAL_KEYWORDS,
        },
    },
    {
        "id": "routing_game_confide_02",
        "category": "routing",
        "description": "倾诉中提到游戏但并非发起对局 → chat（核心反例）",
        "input": "今天在游戏公司加班好累，想跟你聊聊",
        "scripted_reply": "加班到这么晚真的很辛苦，先歇一会儿，我陪你聊聊。",
        "expect": {
            "route": "chat",
            "final_contains_any": ("辛苦", "陪你", "歇"),
        },
    },
    {
        "id": "routing_game_ambiguous_03",
        "category": "routing",
        "description": "模糊提到游戏话题，不是邀请对局 → chat",
        "input": "我最近对游戏有点腻了，想换点别的爱好",
        "scripted_reply": "腻了也正常呀，要不要试试散步、画画或者听歌？",
        "expect": {
            "route": "chat",
            "final_contains_any": ("试试", "要不要", "正常"),
        },
    },
    {
        "id": "routing_chat_general_04",
        "category": "routing",
        "description": "普通情绪陪伴 → chat",
        "input": "今天有点累，陪我聊聊天吧",
        "scripted_reply": "我在呢，今天发生什么了？慢慢说给我听。",
        "expect": {
            "route": "chat",
            "final_contains_any": ("我在", "慢慢", "今天"),
        },
    },
]
