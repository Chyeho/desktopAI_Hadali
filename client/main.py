'''客户端入口（UI 进程）

职责：OpenGL 格式 → 模型校验 → live2d.init() → QApplication → 拉起后端并等待就绪 →
显示桌宠窗口。后端先启动、前端后显示，避免窗口已出现但后端尚未就绪时用户提前对话。
API Key 与 Agent 初始化全部在后端完成，客户端不再因配置问题退出。
'''
import argparse
import os
import sys

import live2d.v3 as live2d
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtGui import QSurfaceFormat
from PySide6.QtWidgets import QApplication

from client.server_launcher import DEFAULT_BASE_URL, READY_TIMEOUT, ServerLauncher
from client.transport.client import SseTransport
from client.ui.live2d_widget import MODEL_PATH
from client.ui.window import ImageWindow

# 等待后端的兜底上限：launcher 自身 READY_TIMEOUT 失败后会发 failed，这里只防卡死
WAIT_TIMEOUT_MS = int((READY_TIMEOUT + 5) * 1000)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hadali", description="Live2D 桌宠客户端")
    parser.add_argument(
        "--server-url",
        default=os.environ.get("HADALI_SERVER_URL", DEFAULT_BASE_URL),
        help="后端地址（默认 http://127.0.0.1:8765）",
    )
    parser.add_argument(
        "--no-spawn",
        action="store_true",
        help="只连接已存在的后端，不自动拉起",
    )
    return parser


def wait_for_backend(launcher: ServerLauncher,
                     timeout_ms: int = WAIT_TIMEOUT_MS) -> dict:
    """阻塞等待后端就绪，返回 {ok, base_url, token, error}

    此阶段主窗口尚未创建，用户无法提前发起对话；事件循环仅用于接收
    launcher 的 ready / failed 信号。
    """
    loop = QEventLoop()
    result = {"ok": False, "base_url": "", "token": "", "error": "后端启动超时"}

    def on_ready(base_url: str, token: str) -> None:
        result.update(ok=True, base_url=base_url, token=token, error="")
        loop.quit()

    def on_failed(message: str) -> None:
        result["error"] = message
        loop.quit()

    launcher.ready.connect(on_ready)
    launcher.failed.connect(on_failed)
    launcher.start()
    QTimer.singleShot(timeout_ms, loop.quit)
    loop.exec()
    return result


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    # 设置 OpenGL 默认格式：支持透明与抗锯齿（必须在创建 QApplication 之前设置）
    fmt = QSurfaceFormat()
    fmt.setAlphaBufferSize(8)
    fmt.setSamples(4)
    QSurfaceFormat.setDefaultFormat(fmt)

    if not os.path.exists(MODEL_PATH):
        print(f"❌ Live2D 模型不存在: {MODEL_PATH}")
        return 1

    # 初始化 live2d 运行时（需在创建 OpenGL 窗口前调用）
    live2d.init()

    app = QApplication(sys.argv)
    app.setApplicationName("SSS_bot_live2d")

    # 先启动后端并等待就绪，再创建/显示主窗口
    launcher = ServerLauncher(base_url=args.server_url, spawn=not args.no_spawn)
    print("[client] 正在启动后端，请稍候...")
    outcome = wait_for_backend(launcher)
    if outcome["ok"]:
        print(f"[client] 后端已就绪：{outcome['base_url']}")
    else:
        print(f"[client] 后端未就绪：{outcome['error']}")
        launcher.shutdown()

    transport = SseTransport(base_url=args.server_url)
    window = ImageWindow(transport)
    if outcome["ok"]:
        transport.configure(base_url=outcome["base_url"], token=outcome["token"])
        window.set_backend_ready(outcome["base_url"])
    else:
        window.show_backend_error(outcome["error"])

    window.setWindowTitle("哈达莉")
    window.show()

    try:
        app.exec()
    finally:
        transport.close()
        launcher.shutdown()
        live2d.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
