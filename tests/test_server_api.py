"""单元测试：server HTTP API

用 httpx.ASGITransport + 假服务（FakeServices），不请求真实模型 / 网络。
覆盖健康检查、SSE 事件顺序、错误分支、参数校验与 token 鉴权。
"""
import asyncio
import json

import httpx

from backend.api.app import create_app


def _result(**overrides):
    base = {
        "emotion": "happy",
        "reply": "你好呀",
        "mode": "emotion",
        "steps": 1,
        "tool_calls": [],
        "latency_ms": 12.0,
    }
    base.update(overrides)
    return base


class _FakeAgent:
    def __init__(self, result, exc):
        self.result = result
        self.exc = exc

    def chat(self, text):
        if self.exc is not None:
            raise self.exc
        return self.result


class FakeServices:
    """与 server.services.Services 同接口的测试替身"""

    model_name = "fake-model"
    turns_file = None

    def __init__(self, result=None, exc=None, turns_file=None):
        self.agent = _FakeAgent(result or _result(), exc)
        self.turns_file = turns_file
        self.last_call = None
        self._locks = {}

    def lock(self, session_id):
        return self._locks.setdefault(session_id, asyncio.Lock())

    def chat(self, session_id, text):
        self.last_call = (session_id, text)
        return self.agent.chat(text)


def _request(services, method, path, **kwargs):
    app = create_app(services=services)

    async def main():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.request(method, path, **kwargs)

    return asyncio.run(main())


def _parse_sse(text):
    """把 SSE 响应体解析成 [(event_name, data_dict), ...]"""
    events = []
    for block in text.strip().split("\n\n"):
        name, data = None, None
        for line in block.splitlines():
            if line.startswith("event: "):
                name = line[len("event: "):]
            elif line.startswith("data: "):
                data = json.loads(line[len("data: "):])
        if name and data is not None:
            events.append((name, data))
    return events


class TestMeta:
    """健康检查"""

    def test_health(self):
        resp = _request(FakeServices(), "GET", "/v1/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok", "version": "0.1.0", "model": "fake-model"}


class TestChatStream:
    """POST /v1/chat：SSE 事件顺序与字段"""

    def test_success_event_order(self):
        services = FakeServices()
        resp = _request(services, "POST", "/v1/chat", json={"text": "你好"})
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        assert resp.headers["cache-control"] == "no-cache"

        events = _parse_sse(resp.text)
        names = [name for name, _ in events]
        assert names == [
            "turn.start",
            "state",
            "state",
            "text.delta",
            "text.done",
            "emotion",
            "turn.end",
            "state",
        ]
        # seq 从 1 连续递增，turn_id 一致
        assert [data["seq"] for _, data in events] == list(range(1, len(events) + 1))
        assert len({data["turn_id"] for _, data in events}) == 1

        payload = dict(events)
        assert payload["state"]["value"] == "idle"
        assert payload["turn.start"]["mode"] == "emotion"
        assert payload["text.delta"]["text"] == "你好呀"
        assert payload["text.done"]["text"] == "你好呀"
        assert payload["emotion"]["name"] == "happy"
        assert payload["turn.end"]["reply"] == "你好呀"
        assert services.last_call == ("default", "你好")

    def test_states_in_order(self):
        resp = _request(FakeServices(), "POST", "/v1/chat", json={"text": "hi"})
        states = [data["value"] for name, data in _parse_sse(resp.text) if name == "state"]
        assert states == ["thinking", "speaking", "idle"]

    def test_tool_events_appended_after_text(self):
        result = _result(tool_calls=[
            {"name": "get_weather", "args": {"city": "北京"}, "ok": True, "duration_ms": 820.0}
        ])
        resp = _request(FakeServices(result=result), "POST", "/v1/chat", json={"text": "天气"})
        names = [name for name, _ in _parse_sse(resp.text)]
        assert names.index("tool.call") > names.index("text.done")
        assert names.index("tool.result") > names.index("tool.call")
        assert names[-2:] == ["turn.end", "state"]

    def test_session_passed_through(self):
        services = FakeServices()
        resp = _request(
            services, "POST", "/v1/chat",
            json={"session_id": "work", "text": "hi"},
        )
        assert resp.status_code == 200
        assert services.last_call == ("work", "hi")
        events = dict(_parse_sse(resp.text))
        assert events["turn.start"]["mode"] == "emotion"

    def test_agent_error_emits_error_then_idle(self):
        resp = _request(FakeServices(exc=RuntimeError("boom")), "POST", "/v1/chat", json={"text": "hi"})
        assert resp.status_code == 200
        events = _parse_sse(resp.text)
        names = [name for name, _ in events]
        assert names == ["turn.start", "state", "error", "state"]
        error = dict(events)["error"]
        assert error["code"] == "INTERNAL"
        assert error["retryable"] is True
        assert events[-1][1]["value"] == "idle"

    def test_timeout_maps_to_llm_timeout(self):
        resp = _request(FakeServices(exc=TimeoutError("timeout")), "POST", "/v1/chat", json={"text": "hi"})
        error = dict(_parse_sse(resp.text))["error"]
        assert error["code"] == "LLM_TIMEOUT"

    def test_turn_end_reports_first_event_ms(self):
        resp = _request(FakeServices(), "POST", "/v1/chat", json={"text": "hi"})
        turn_end = dict(_parse_sse(resp.text))["turn.end"]
        assert turn_end["first_event_ms"] >= 0.0

    def test_connection_error_maps_to_llm_error(self):
        resp = _request(
            FakeServices(exc=httpx.ConnectError("refused")), "POST", "/v1/chat",
            json={"text": "hi"},
        )
        error = dict(_parse_sse(resp.text))["error"]
        assert error["code"] == "LLM_ERROR"
        assert error["retryable"] is True

    def test_value_error_maps_to_bad_request(self):
        resp = _request(
            FakeServices(exc=ValueError("未知的 agent 模式")), "POST", "/v1/chat",
            json={"text": "hi"},
        )
        error = dict(_parse_sse(resp.text))["error"]
        assert error["code"] == "BAD_REQUEST"
        assert error["retryable"] is False

    def test_invalid_session_id_returns_400(self):
        resp = _request(FakeServices(), "POST", "/v1/chat", json={"session_id": "../evil", "text": "hi"})
        assert resp.status_code == 400

    def test_empty_text_returns_400(self):
        resp = _request(FakeServices(), "POST", "/v1/chat", json={"text": ""})
        assert resp.status_code == 400


class FakeStreamingServices(FakeServices):
    """在 FakeServices 基础上提供同步增量生成器，模拟 graph 引擎流式"""

    def __init__(self, deltas=("你", "好呀"), result=None):
        super().__init__(result=result)
        self.deltas = tuple(deltas)

    def stream_chat(self, session_id, text):
        self.last_call = (session_id, text)

        def gen():
            for piece in self.deltas:
                yield ("delta", piece)
            yield ("done", self.agent.chat(text))

        return gen()


class FakeFailingStreamServices(FakeServices):
    """流式生成器中途抛异常，用于验证错误事件映射"""

    def __init__(self, exc):
        super().__init__()
        self.exc = exc

    def stream_chat(self, session_id, text):
        exc = self.exc

        def gen():
            yield ("delta", "你")
            raise exc

        return gen()


class FakeNoDoneStreamServices(FakeServices):
    """流式生成器只产出 delta 就结束（缺 done），验证路由兜底报错"""

    def stream_chat(self, session_id, text):
        def gen():
            yield ("delta", "你")

        return gen()


class TestChatStreamingGraph:
    """graph 引擎：逐 token 下发 text.delta，legacy 引擎一次性下发"""

    def test_stream_deltas_event_order(self):
        services = FakeStreamingServices()
        resp = _request(services, "POST", "/v1/chat", json={"text": "你好"})
        assert resp.status_code == 200

        events = _parse_sse(resp.text)
        names = [name for name, _ in events]
        assert names == [
            "turn.start",
            "state",
            "state",
            "text.delta",
            "text.delta",
            "text.done",
            "emotion",
            "turn.end",
            "state",
        ]
        assert [data["text"] for name, data in events if name == "text.delta"] == ["你", "好呀"]
        payload = dict(events)
        assert payload["text.done"]["text"] == "你好呀"
        assert payload["emotion"]["name"] == "happy"
        assert services.last_call == ("default", "你好")

    def test_stream_session_passed_through(self):
        services = FakeStreamingServices()
        resp = _request(
            services, "POST", "/v1/chat",
            json={"session_id": "work", "text": "hi"},
        )
        assert resp.status_code == 200
        assert services.last_call == ("work", "hi")
        assert dict(_parse_sse(resp.text))["turn.start"]["mode"] == "emotion"

    def test_stream_error_maps_to_bad_request(self):
        resp = _request(
            FakeFailingStreamServices(ValueError("未知的 agent 模式")),
            "POST", "/v1/chat", json={"text": "hi"},
        )
        events = _parse_sse(resp.text)
        names = [name for name, _ in events]
        assert names == ["turn.start", "state", "state", "text.delta", "error", "state"]
        error = dict(events)["error"]
        assert error["code"] == "BAD_REQUEST"
        assert events[-1][1]["value"] == "idle"

    def test_stream_without_done_emits_internal_error(self):
        resp = _request(
            FakeNoDoneStreamServices(), "POST", "/v1/chat", json={"text": "hi"},
        )
        # 生成器正常结束但没有 done → 路由应报错（不被吞掉）
        error = dict(_parse_sse(resp.text))["error"]
        assert error["code"] == "INTERNAL"
        assert "流式对话未返回最终结果" in error["message"]

    def test_legacy_fallback_emits_single_delta(self):
        """没有 stream_chat 的服务：仍应一次性下发完整回复"""
        resp = _request(FakeServices(), "POST", "/v1/chat", json={"text": "你好"})
        deltas = [data["text"] for name, data in _parse_sse(resp.text) if name == "text.delta"]
        assert deltas == ["你好呀"]


class TestAuthAndInterrupt:
    """token 鉴权与打断接口"""

    def test_no_token_configured_allows_request(self, monkeypatch):
        monkeypatch.delenv("HADALI_TOKEN", raising=False)
        assert _request(FakeServices(), "GET", "/v1/health").status_code == 200

    def test_missing_token_returns_401(self, monkeypatch):
        monkeypatch.setenv("HADALI_TOKEN", "dev-token")
        assert _request(FakeServices(), "GET", "/v1/health").status_code == 401

    def test_wrong_token_returns_401(self, monkeypatch):
        monkeypatch.setenv("HADALI_TOKEN", "dev-token")
        resp = _request(FakeServices(), "GET", "/v1/health", headers={"X-Hadali-Token": "wrong"})
        assert resp.status_code == 401

    def test_correct_token_passes(self, monkeypatch):
        monkeypatch.setenv("HADALI_TOKEN", "dev-token")
        resp = _request(FakeServices(), "GET", "/v1/health", headers={"X-Hadali-Token": "dev-token"})
        assert resp.status_code == 200

    def test_interrupt_returns_ok(self):
        resp = _request(FakeServices(), "POST", "/v1/interrupt", json={"session_id": "default"})
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}
