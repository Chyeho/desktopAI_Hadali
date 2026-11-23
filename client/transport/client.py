'''前端传输层：把 UI 与后端对话彻底解耦

- `Transport`：UI 依赖的抽象接口（send / interrupt / close + 两个信号），未来
  若引入 asyncio 方案，只需新增一个实现，UI 层不改。
- `SseTransport`：本期实现，`SseWorker(QThread)` 内用 `httpx.Client` +
  `httpx_sse.connect_sse` 消费 `POST /v1/chat` 的事件流，再以 Qt 信号把
  `(event_name, payload)` 投递回主线程。

线程约定：本模块的任何函数都不触碰 live2d / Qt 控件；事件只通过信号交给 UI。
'''
from __future__ import annotations

import os
import threading

import httpx
from httpx_sse import connect_sse
from PySide6.QtCore import QObject, QThread, Signal

from backend.protocol.events import EVENT_MODEL_MAP
from utils.logger_handler import logger

DEFAULT_BASE_URL = "http://127.0.0.1:8765"
TOKEN_HEADER = "X-Hadali-Token"

# 事件流是长连接：建连/写超时较短，读超时 60s（两帧之间超时视为断连，由 UI 提示重发）
DEFAULT_TIMEOUT = httpx.Timeout(connect=3.0, read=60.0, write=10.0, pool=10.0)


def decode_event(event_name: str, data: str) -> tuple[str, dict] | None:
    """SSE 原始帧 → (事件名, 字典载荷)

    未知事件（如未来新增事件）与非法 JSON 只记日志并丢弃，不让单帧脏数据中断整轮对话。
    """
    model = EVENT_MODEL_MAP.get(event_name)
    if model is None:
        logger.debug(f"[transport]忽略未知事件：{event_name}")
        return None
    try:
        event = model.model_validate_json(data)
    except Exception as exc:
        logger.warning(f"[transport]事件解析失败 {event_name}：{exc}")
        return None
    return event_name, event.model_dump(mode="json")


def _status_message(response: httpx.Response) -> str:
    """HTTP 错误状态 → 面向用户的中文提示"""
    status = response.status_code
    if status == 401:
        return "后端鉴权失败（token 不匹配），请重新启动客户端"
    if status == 400:
        return "请求参数错误，请检查输入后重试"
    if status == 404:
        return "后端接口不存在，请确认服务版本"
    return f"后端返回错误（HTTP {status}）"


class Transport(QObject):
    """传输层接口：UI 只依赖这里的信号与方法"""

    event_received = Signal(str, dict)   # (事件名, 载荷)
    failed = Signal(str)                 # 连接/协议错误（面向用户的中文提示）

    def send(self, text: str, session_id: str = "default") -> None:
        raise NotImplementedError

    def interrupt(self, session_id: str = "default") -> None:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError


class SseWorker(QThread):
    """单轮对话的 SSE 消费线程

    每次 send() 新建一个实例，线程内同步阻塞读流；一轮结束线程自然退出。
    UI 线程若要打断，调用 cancel() 关闭底层连接，读流立即抛错并被识别为“已取消”。
    """

    event = Signal(str, dict)
    failed = Signal(str)

    def __init__(self, url: str, payload: dict, headers: dict | None = None,
                 client_factory=None, close_client: bool = True,
                 retry_delay: float = 1.0, parent=None):
        super().__init__(parent)
        self.url = url
        self.payload = payload
        self.headers = headers or {}
        self.retry_delay = retry_delay
        self._client_factory = client_factory
        self._close_client = close_client
        self._cancelled = threading.Event()
        self._client: httpx.Client | None = None
        self._response = None
        self._client_lock = threading.Lock()

    # ---------- 生命周期 ----------
    def cancel(self) -> None:
        """打断：标记取消并关闭当前响应流，使阻塞中的读流尽快返回

        只关响应、不关共享 Client：避免一次打断让后续轮次重建 Client
        （Windows 上 `httpx.Client()` 初始化约 1.4s，代价很高）。
        """
        self._cancelled.set()
        with self._client_lock:
            response = self._response
            client = self._client
        if response is not None:
            try:
                response.close()
            except Exception:
                pass
        if self._close_client and client is not None:
            try:
                client.close()
            except Exception:
                pass

    @property
    def cancelled(self) -> bool:
        return self._cancelled.is_set()

    def _make_client(self) -> httpx.Client:
        if self._client_factory is not None:
            return self._client_factory()
        return httpx.Client(timeout=DEFAULT_TIMEOUT)

    def run(self) -> None:  # noqa: D401 - QThread 入口
        """消费事件流；仅当“连接阶段失败且一个事件都没收到”时重试一次

        重试不会重放已发送的 turn：只要收到过任意一拍（含 turn.start），
        说明请求已到达 server，此时失败一律上报，避免重复调用大模型。
        """
        attempt = 0
        while True:
            attempt += 1
            received = False
            client = self._make_client()
            with self._client_lock:
                self._client = client
            try:
                with connect_sse(client, "POST", self.url,
                                 json=self.payload, headers=self.headers) as source:
                    with self._client_lock:
                        self._response = source.response
                    source.response.raise_for_status()
                    for message in source.iter_sse():
                        if self.cancelled:
                            return
                        received = True
                        decoded = decode_event(message.event, message.data)
                        if decoded is not None:
                            self.event.emit(*decoded)
                return
            except httpx.HTTPStatusError as exc:
                if not self.cancelled:
                    logger.warning(f"[transport]后端返回 HTTP {exc.response.status_code}")
                    self.failed.emit(_status_message(exc.response))
                return
            except Exception as exc:
                if self.cancelled:
                    return
                connect_failed = isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout))
                if attempt == 1 and not received and connect_failed:
                    logger.warning(f"[transport]连接失败，{self.retry_delay}s 后重试一次：{exc}")
                    if self.retry_delay > 0 and self._cancelled.wait(self.retry_delay):
                        return
                    continue
                logger.warning(f"[transport]连接异常：{exc}")
                self.failed.emit(f"与后端的连接中断：{exc}")
                return
            finally:
                with self._client_lock:
                    self._response = None
                    self._client = None
                if self._close_client:
                    try:
                        client.close()
                    except Exception:
                        pass


class SseTransport(Transport):
    """基于本机 HTTP + SSE 的传输实现

    参数：
        base_url       : 后端地址，默认读 `HADALI_SERVER_URL`，再回退 127.0.0.1:8765
        token          : 鉴权 token，默认读 `HADALI_TOKEN`；为空则不发送请求头
        client_factory : 测试注入点，返回 httpx.Client 的可调用对象
    """

    def __init__(self, base_url: str | None = None, token: str | None = None,
                 session_id: str = "default", client_factory=None,
                 retry_delay: float = 1.0, parent=None):
        super().__init__(parent)
        self.base_url = (base_url or os.environ.get("HADALI_SERVER_URL")
                         or DEFAULT_BASE_URL).rstrip("/")
        self.token = token if token is not None else os.environ.get("HADALI_TOKEN", "")
        self.session_id = session_id
        self.retry_delay = retry_delay
        self._client_factory = client_factory
        self._worker: SseWorker | None = None
        self._shared_http: httpx.Client | None = None
        self._shared_lock = threading.Lock()
        self._lock = threading.Lock()

    # ---------- 配置 ----------
    def configure(self, base_url: str | None = None, token: str | None = None) -> None:
        """后端就绪后由启动器回填实际地址与 token"""
        if base_url:
            self.base_url = base_url.rstrip("/")
        if token is not None:
            self.token = token

    def _headers(self) -> dict:
        headers = {"Accept": "text/event-stream"}
        if self.token:
            headers[TOKEN_HEADER] = self.token
        return headers

    def _get_client(self) -> httpx.Client:
        """复用同一个 httpx.Client

        `httpx.Client()` 在 Windows 上初始化约 1.4s（加载证书上下文），
        每轮新建会让“首事件延迟”凭空多出一秒多，因此整条传输链路共用一个实例。
        """
        with self._shared_lock:
            if self._shared_http is None:
                self._shared_http = (self._client_factory()
                                     if self._client_factory is not None
                                     else httpx.Client(timeout=DEFAULT_TIMEOUT))
            return self._shared_http

    # ---------- Transport 接口 ----------
    def is_busy(self) -> bool:
        with self._lock:
            worker = self._worker
        return worker is not None and worker.isRunning()

    def send(self, text: str, session_id: str | None = None) -> None:
        """发起一轮对话（非阻塞）；上一轮未结束时拒绝并发出 failed 信号"""
        if self.is_busy():
            self.failed.emit("上一轮回复尚未结束，请稍候")
            return
        sid = session_id or self.session_id
        payload = {"session_id": sid, "text": text}
        worker = SseWorker(
            f"{self.base_url}/v1/chat",
            payload,
            headers=self._headers(),
            client_factory=self._get_client,
            close_client=False,
            retry_delay=self.retry_delay,
            parent=self,
        )
        worker.event.connect(self.event_received)
        worker.failed.connect(self.failed)
        with self._lock:
            self._worker = worker
        worker.start()

    def interrupt(self, session_id: str | None = None) -> None:
        """打断当前轮：通知后端（尽力而为）并立即关闭本地事件流"""
        sid = session_id or self.session_id
        threading.Thread(target=self._post_interrupt, args=(sid,),
                         daemon=True, name="transport-interrupt").start()
        with self._lock:
            worker = self._worker
        if worker is not None:
            worker.cancel()

    def close(self) -> None:
        """退出时释放：关闭事件流、等待线程收尾、关闭共享 Client"""
        self.interrupt()
        with self._lock:
            worker = self._worker
            self._worker = None
        if worker is not None:
            worker.cancel()
            worker.wait(1500)
        with self._shared_lock:
            client, self._shared_http = self._shared_http, None
        if client is not None:
            try:
                client.close()
            except Exception:
                pass

    # ---------- 内部 ----------
    def _post_interrupt(self, session_id: str) -> None:
        try:
            client = self._get_client()
            client.post(f"{self.base_url}/v1/interrupt",
                        json={"session_id": session_id}, headers=self._headers())
        except Exception as exc:
            logger.debug(f"[transport]interrupt 请求失败（可忽略）：{exc}")
