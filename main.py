"""
程序主入口
整合 chatbotUI（Live2D 桌宠界面）、chatbot（AI 对话）、resources（资源路径）
"""
import os
import sys

import live2d.v3 as live2d
from PySide6.QtGui import QSurfaceFormat
from PySide6.QtWidgets import QApplication

import chatbot
import chatbotUI
import resources


def main():
    """程序主入口：初始化 OpenGL/Live2D、API Key，并启动桌宠窗口"""
    # 设置 OpenGL 默认格式：支持透明与抗锯齿（需在 QApplication 之前）
    fmt = QSurfaceFormat()
    fmt.setAlphaBufferSize(8)
    fmt.setSamples(4)
    QSurfaceFormat.setDefaultFormat(fmt)

    # 校验 Live2D 模型文件是否存在
    if not os.path.exists(chatbotUI.MODEL_PATH):
        print(f"❌ Live2D 模型不存在: {chatbotUI.MODEL_PATH}")
        print(f"资源目录: {resources.RESOURCES_DIRECTORY}")
        sys.exit(1)

    # 从 .env 读取 API_KEY 并初始化
    try:
        chatbot.init_api_key_from_env()
    except Exception as e:
        print(f"❌ API Key 初始化失败: {e}")
        sys.exit(1)

    live2d.init()

    app = QApplication(sys.argv)
    app.setApplicationName("SSS_bot_live2d")

    window = chatbotUI.ImageWindow()
    window.setWindowTitle("哈达莉")
    window.show()

    app.exec()
    live2d.dispose()


if __name__ == "__main__":
    main()
