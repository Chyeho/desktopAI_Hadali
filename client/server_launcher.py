'''后端进程拉起与探活

启动顺序（全部在 QThread 中执行，不阻塞主线程）：
1. 带 token 探活 → 成功则复用现有后端；
2. 不带 token 再探一次 → 兼容手工启动的调试后端；
3. 都失败则用 `python -m server` 拉起子进程（`HADALI_TOKEN` 经环境变量传入）；
4. 轮询 `/v1/health` 直到就绪或超时。

失败只发 `failed` 信号，绝不 `sys.exit`：窗口必须保持可见。
'''
from __future__ import annotations

import json
import os
import queue
import secrets
import subprocess
import sys
import threading
import time
from urllib.parse import urlparse

import httpx
from PySide6.QtCore import QObject, QThread, Signal

from client.transport.client import DEFAULT_BASE_URL, TOKEN_HEADER
from utils.logger_handler import logger
from utils.path_tool import get_root_path

READY_PREFIX = "HADALI_SERVER_READY"
PROBE_TIMEOUT = 0.5      # 单次探活超时
# 拉起后等待就绪的上限：本机实测空载启动（langchain 等重依赖导入）约 13s，
# 因此不能沿用执行文档的 5s；窗口在等待期间保持可用，由聊天框提示“后端正在启动”。
READY_TIMEOUT = 20.0


def probe(base_url: str, token: str, timeout: float = PROBE_TIMEOUT) -> bool:
    """GET /v1/health 探活"""
    headers = {TOKEN_HEADER: token} if token else {}
    try:
        with httpx.Client(timeout=timeout) as client:
            return client.get(f"{base_url}/v1/health", headers=headers).status_code == 200
    except Exception:
        return False


class _LaunchWorker(QThread):
    """探活 / 拉起子进程的工作线程"""

    ready = Signal(str, str)   # (base_url, token)
    failed = Signal(str)

    def __init__(self, base_url: str, token: str, spawn: bool = True, parent=None):
        super().__init__(parent)
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.spawn = spawn
        self.proc: subprocess.Popen | None = None
        self._stop = threading.Event()
        self._log_file = None

    def stop(self) -> None:
        """终止自己拉起的子进程（复用的外部后端不受影响）"""
        self._stop.set()
        proc = self.proc
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(3)
            except Exception:
                proc.kill()
        self._close_log()

    def run(self) -> None:  # noqa: D401 - QThread 入口
        # 1) 复用已就绪的后端（带 token / 不带 token 各试一次）
        if probe(self.base_url, self.token):
            self.ready.emit(self.base_url, self.token)
            return
        if self.token and probe(self.base_url, ""):
            self.ready.emit(self.base_url, "")
            return
        if not self.spawn:
            self.failed.emit("未检测到可用后端，且已禁用自动拉起")
            return
        if self._stop.is_set():
            return
        base_url = self._spawn_server()
        if base_url is None:
            self.failed.emit("后端启动失败，请查看 logs/server.log")
            return
        self.ready.emit(base_url, self.token)

    # ---------- 子进程拉起 ----------
    def _spawn_server(self) -> str | None:
        parsed = urlparse(self.base_url)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 0
        root = get_root_path()
        log_dir = os.path.join(root, "logs")
        os.makedirs(log_dir, exist_ok=True)
        self._log_file = open(os.path.join(log_dir, "server.log"), "ab")

        env = os.environ.copy()
        env["HADALI_TOKEN"] = self.token
        cmd = [sys.executable, "-m", "server", "--host", host, "--port", str(port)]
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            self.proc = subprocess.Popen(
                cmd, cwd=root, env=env,
                stdout=subprocess.PIPE if port == 0 else subprocess.DEVNULL,
                stderr=self._log_file,
                creationflags=creationflags,
            )
        except Exception as exc:
            logger.error(f"[launcher]拉起后端失败：{exc}")
            self._close_log()
            return None

        deadline = time.time() + READY_TIMEOUT
        announced = None
        if port == 0:
            announced = self._wait_announced_port(deadline)
            if announced is None:
                self.stop()
                self._close_log()
                return None

        candidate = f"http://{host}:{announced}" if announced else self.base_url
        while time.time() < deadline and not self._stop.is_set():
            if self.proc.poll() is not None:
                break   # 进程提前退出（端口被占用等）
            if probe(candidate, self.token, timeout=0.3):
                logger.info(f"[launcher]后端已就绪：{candidate}")
                return candidate
            time.sleep(0.2)
        self.stop()
        self._close_log()
        return None

    def _wait_announced_port(self, deadline: float) -> int | None:
        """`--port 0`：从子进程 stdout 读取就绪行里的真实端口"""
        lines: queue.Queue[str] = queue.Queue()

        def reader():
            for line in self.proc.stdout:
                lines.put(line.rstrip("\n"))

        threading.Thread(target=reader, daemon=True, name="launcher-stdout").start()
        while time.time() < deadline and not self._stop.is_set():
            try:
                line = lines.get(timeout=0.2)
            except queue.Empty:
                continue
            if not line.startswith(READY_PREFIX):
                continue
            try:
                return int(json.loads(line[len(READY_PREFIX):].strip())["port"])
            except Exception:
                logger.warning(f"[launcher]无法解析就绪行：{line}")
        return None

    def _close_log(self) -> None:
        if self._log_file is not None:
            try:
                self._log_file.close()
            except Exception:
                pass
            self._log_file = None


class ServerLauncher(QObject):
    """对外接口：start() 后通过 ready / failed 信号通知结果"""

    ready = Signal(str, str)
    failed = Signal(str)

    def __init__(self, base_url: str | None = None, token: str | None = None,
                 spawn: bool = True, parent=None):
        super().__init__(parent)
        self.base_url = (base_url or os.environ.get("HADALI_SERVER_URL")
                         or DEFAULT_BASE_URL).rstrip("/")
        self.token = token or os.environ.get("HADALI_TOKEN") or secrets.token_urlsafe(32)
        self.spawn = spawn
        self._worker: _LaunchWorker | None = None

    def start(self) -> None:
        worker = _LaunchWorker(self.base_url, self.token, spawn=self.spawn, parent=self)
        worker.ready.connect(self.ready)
        worker.failed.connect(self.failed)
        self._worker = worker
        worker.start()

    def shutdown(self) -> None:
        """退出时终止自己拉起的后端（外部复用的后端不动）"""
        worker, self._worker = self._worker, None
        if worker is not None:
            worker.stop()
            worker.wait(3000)
