"""单元测试：陪伴主图感知门控 agent/graph/perception.py"""
from langchain_core.messages import AIMessage, HumanMessage

from backend.agent.graph import perception
from backend.agent.graph.perception import (
    CHAT_ROUTE,
    GAME_CONFIDENCE_THRESHOLD,
    GAME_ROUTE,
    decide_route,
    perception_node,
)


class _FailingBackend:
    """模拟 FakeJev 调用异常，验证关键词兜底"""

    def choose(self, request):
        raise RuntimeError("backend down")


class TestDecideRoute:
    """FakeJev 门控结果"""

    def test_game_request_routes_to_game(self):
        """明确的下棋请求进入 game"""
        route, confidence = decide_route("来下盘五子棋吧")
        assert route == GAME_ROUTE
        assert confidence > GAME_CONFIDENCE_THRESHOLD

    def test_plain_chat_routes_to_chat(self):
        """普通聊天不进游戏"""
        route, _ = decide_route("今天心情有点低落，想聊聊天")
        assert route == CHAT_ROUTE

    def test_tool_task_routes_to_chat(self):
        """工具型任务不进游戏"""
        route, _ = decide_route("帮我查一下北京天气")
        assert route == CHAT_ROUTE

    def test_empty_text_routes_to_chat(self):
        """空输入默认走聊天"""
        assert decide_route("") == (CHAT_ROUTE, 0.0)
        assert decide_route("   ")[0] == CHAT_ROUTE

    def test_backend_failure_falls_back_to_keywords(self, monkeypatch):
        """FakeJev 异常时回落关键词：两个命中才进游戏"""
        monkeypatch.setattr(perception, "_backend", _FailingBackend())

        assert decide_route("来下盘五子棋")[0] == GAME_ROUTE
        assert decide_route("今天好累")[0] == CHAT_ROUTE


class TestPerceptionNode:
    """门控节点只写路由字段"""

    def test_game_node_returns_game_request(self):
        state = {"messages": [HumanMessage(content="陪我下盘棋")]}
        update = perception_node(state)

        assert update["route"] == GAME_ROUTE
        assert update["game_request"] == "陪我下盘棋"
        assert "messages" not in update

    def test_chat_node_clears_game_request(self):
        state = {"messages": [HumanMessage(content="今天想聊聊天")]}
        update = perception_node(state)

        assert update["route"] == CHAT_ROUTE
        assert update["game_request"] is None
        assert "messages" not in update

    def test_time_prefix_is_stripped(self):
        state = {"messages": [HumanMessage(content="[2026-11-21 14:30] 来下盘五子棋")]}
        update = perception_node(state)

        assert update["route"] == GAME_ROUTE
        assert update["game_request"] == "来下盘五子棋"

    def test_uses_last_human_message(self):
        state = {
            "messages": [
                HumanMessage(content="来下盘五子棋"),
                AIMessage(content="好呀"),
                HumanMessage(content="今天天气怎么样"),
            ]
        }
        update = perception_node(state)

        assert update["route"] == CHAT_ROUTE

    def test_no_messages_routes_to_chat(self):
        assert perception_node({"messages": []})["route"] == CHAT_ROUTE
