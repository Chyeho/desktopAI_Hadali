"""单元测试：client/transport/client.py

覆盖：
- decode_event：合法事件解析、未知事件 / 非法 JSON 丢弃
- SseWorker：真实 HTTP 上的 SSE 帧顺序、HTTP 错误、连接拒绝（断连不崩）
- SseTransport：send 转发事件、interrupt 发出 POST 且不抛异常
"""
import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest
from PySide6.QtCore import QCoreApplication

from client.transport.client import SseTransport, SseWorker, decode_event


@pytest.fixture(scope="module", autouse=True)
def _qt_app():
    """QThread / 信号需要 QCoreApplication 实例"""
    return QCoreApplication.instance() or QCoreApplication([])


def _payload(**fields) -> dict:
    data = {"seq": 1, "turn_id": "t1", "ts": 0}
    data.update(fields)
    return data


def _frame(name: str, **fields) -> str:
    return f"event: {name}\ndata: {json.dumps(_payload(**fields))}\n\n"


def _wait_until(predicate, timeout: float = 5.0, interval: float = 0.02) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        QCoreApplication.processEvents()
        if predicate():
            return True
        time.sleep(interval)
    return False


class _SseHandler(BaseHTTPRequestHandler):
    """按测试设定的状态码返回固定的 SSE 帧；记录收到的请求路径"""

    frames: list[str] = []
    status = 200
    paths: list[str] = []

    def do_POST(self):
        cls = type(self)
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            self.rfile.read(length)
        cls.paths.append(self.path)
        if self.path == "/v1/interrupt":
            body = b'{"ok":true}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(cls.status)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        if cls.status == 200:
            for frame in cls.frames:
                self.wfile.write(frame.encode("utf-8"))
                self.wfile.flush()

    def log_message(self, fmt, *args):
        pass


@pytest.fixture
def sse_server():
    """启动本地 SSE 服务，返回 (base_url, handler_cls)"""
    servers = []

    def _start(frames, status: int = 200):
        handler = type("Handler", (_SseHandler,), {
            "frames": list(frames),
            "status": status,
            "paths": [],
        })
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        servers.append(server)
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        return base_url, handler

    yield _start
    for server in servers:
        server.shutdown()
        server.server_close()


def _closed_port_url() -> str:
    """取一个刚释放的端口，模拟后端未启动"""
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return f"http://127.0.0.1:{port}"


class TestDecodeEvent:
    """SSE 帧 → (事件名, 载荷)"""

    def test_valid_event(self):
        name, payload = decode_event("emotion", json.dumps(_payload(name="relaxed")))
        assert name == "emotion"
        assert payload["name"] == "relaxed"
        assert payload["seq"] == 1
        assert payload["turn_id"] == "t1"

    def test_enum_field_dumped_as_string(self):
        _, payload = decode_event("state", json.dumps(_payload(value="thinking")))
        assert payload["value"] == "thinking"

    def test_unknown_event_ignored(self):
        assert decode_event("future.event", json.dumps(_payload())) is None

    def test_invalid_json_ignored(self):
        assert decode_event("emotion", "{not json") is None

    def test_missing_required_field_ignored(self):
        assert decode_event("emotion", json.dumps({"seq": 1})) is None


class TestSseWorker:
    """SseWorker：真实 HTTP 上的流式消费"""

    def test_receives_events_in_order(self, sse_server):
        frames = [
            _frame("turn.start", mode="emotion"),
            _frame("state", value="thinking"),
            _frame("text.delta", text="你好"),
            _frame("turn.end", reply="你好", emotion="neutral", latency_ms=10.0),
        ]
        base_url, _ = sse_server(frames)
        events, failures = [], []
        worker = SseWorker(f"{base_url}/v1/chat", {"session_id": "default", "text": "hi"})
        worker.event.connect(lambda name, data: events.append((name, data)))
        worker.failed.connect(failures.append)
        worker.start()
        assert worker.wait(5000)
        # 信号以排队方式投递到主线程，需处理事件循环后才能看到回调结果
        assert _wait_until(lambda: len(events) == 4)
        assert [name for name, _ in events] == [
            "turn.start", "state", "text.delta", "turn.end",
        ]
        assert events[2][1]["text"] == "你好"
        assert events[3][1]["emotion"] == "neutral"
        assert failures == []

    def test_http_error_emits_failed(self, sse_server):
        base_url, _ = sse_server([], status=401)
        failures = []
        worker = SseWorker(f"{base_url}/v1/chat", {"session_id": "default", "text": "hi"})
        worker.failed.connect(failures.append)
        worker.start()
        assert worker.wait(5000)
        assert _wait_until(lambda: len(failures) == 1)
        assert "鉴权" in failures[0]

    def test_connection_refused_emits_failed(self):
        failures = []
        worker = SseWorker(f"{_closed_port_url()}/v1/chat",
                           {"session_id": "default", "text": "hi"}, retry_delay=0)
        worker.failed.connect(failures.append)
        worker.start()
        # Windows 上连接被拒绝的单次尝试可能耗时数秒，且会重试一次
        assert worker.wait(15000)
        assert _wait_until(lambda: len(failures) == 1)
        assert failures[0]


class TestSseTransport:
    """SseTransport：UI 使用的发送 / 打断接口"""

    def test_send_forwards_events(self, sse_server):
        frames = [
            _frame("turn.start", mode="emotion"),
            _frame("text.delta", text="收到"),
        ]
        base_url, _ = sse_server(frames)
        transport = SseTransport(base_url=base_url)
        events = []
        transport.event_received.connect(lambda name, data: events.append(name))
        transport.send("你好")
        assert _wait_until(lambda: events == ["turn.start", "text.delta"])
        assert _wait_until(lambda: not transport.is_busy())
        transport.close()
        assert events == ["turn.start", "text.delta"]

    def test_interrupt_posts_and_cancels(self, sse_server):
        base_url, handler = sse_server([_frame("turn.start", mode="emotion")])
        transport = SseTransport(base_url=base_url)
        transport.send("你好")
        transport.interrupt()
        assert _wait_until(lambda: "/v1/interrupt" in handler.paths)
        assert _wait_until(lambda: not transport.is_busy())
        transport.close()

    def test_failure_forwarded(self, sse_server):
        base_url, _ = sse_server([], status=500)
        transport = SseTransport(base_url=base_url)
        failures = []
        transport.failed.connect(failures.append)
        transport.send("你好")
        assert _wait_until(lambda: bool(failures))
        transport.close()
        assert "HTTP 500" in failures[0]


class TestRetry:
    """连接阶段失败（未收到事件）重试一次；HTTP 状态错误不重试"""

    def _worker(self, handler, events, failures):
        worker = SseWorker(
            "http://bench/v1/chat",
            {"session_id": "default", "text": "hi"},
            client_factory=lambda: httpx.Client(transport=httpx.MockTransport(handler)),
            retry_delay=0,
        )
        worker.event.connect(lambda name, data: events.append(name))
        worker.failed.connect(failures.append)
        return worker

    def test_retry_once_after_connect_error(self):
        calls = {"n": 0}

        def handler(request):
            calls["n"] += 1
            if calls["n"] == 1:
                raise httpx.ConnectError("refused", request=request)
            body = _frame("turn.start", mode="emotion").encode()
            return httpx.Response(
                200, headers={"Content-Type": "text/event-stream"}, content=body
            )

        events, failures = [], []
        worker = self._worker(handler, events, failures)
        worker.start()
        assert worker.wait(5000)
        assert _wait_until(lambda: events == ["turn.start"])
        assert calls["n"] == 2
        assert failures == []

    def test_http_error_not_retried(self):
        calls = {"n": 0}

        def handler(request):
            calls["n"] += 1
            return httpx.Response(500)

        events, failures = [], []
        worker = self._worker(handler, events, failures)
        worker.start()
        assert worker.wait(5000)
        assert _wait_until(lambda: len(failures) == 1)
        assert calls["n"] == 1
        assert events == []
