'''客户端入口（UI 进程）

职责：OpenGL 格式 → 模型校验 → live2d.init() → QApplication → 拉起/复用后端 →
显示桌宠窗口。API Key 与 Agent 初始化全部在后端完成，客户端不再因配置问题退出。
'''
import argparse
import os
import sys

import live2d.v3 as live2d
from PySide6.QtGui import QSurfaceFormat
from PySide6.QtWidgets import QApplication

from client.server_launcher import DEFAULT_BASE_URL, ServerLauncher
from client.transport.client import SseTransport
from client.ui.live2d_widget import MODEL_PATH
from client.ui.window import ImageWindow


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

    transport = SseTransport(base_url=args.server_url)
    window = ImageWindow(transport)
    launcher = ServerLauncher(base_url=args.server_url, spawn=not args.no_spawn)

    def on_backend_ready(base_url: str, token: str) -> None:
        transport.configure(base_url=base_url, token=token)
        window.set_backend_ready(base_url)

    launcher.ready.connect(on_backend_ready)
    launcher.failed.connect(window.show_backend_error)
    launcher.start()

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
