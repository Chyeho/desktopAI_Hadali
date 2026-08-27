"""
程序主入口

整合三个模块启动整个应用：
- chatbotUI：Live2D 桌宠界面（形象 + 聊天框 + 托盘）
- chatbot   ：AI 对话逻辑（DeepSeek 大模型）
- resources ：资源路径常量

启动流程：设置 OpenGL 格式 → 校验模型 → 读取 API_KEY → 初始化 live2d → 显示窗口。
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
    # 设置 OpenGL 默认格式：支持透明与抗锯齿（必须在创建 QApplication 之前设置）
    fmt = QSurfaceFormat()
    fmt.setAlphaBufferSize(8)   # 8 位 alpha 通道，保证窗口透明渲染
    fmt.setSamples(4)           # 4x 多重采样抗锯齿，让 Live2D 边缘更平滑
    QSurfaceFormat.setDefaultFormat(fmt)

    # 校验 Live2D 模型文件是否存在（路径缺失时给出明确提示而不是崩溃）
    if not os.path.exists(chatbotUI.MODEL_PATH):
        print(f"❌ Live2D 模型不存在: {chatbotUI.MODEL_PATH}")
        print(f"资源目录: {resources.RESOURCES_DIRECTORY}")
        sys.exit(1)

    # 从 .env 读取 API_KEY 并初始化 DeepSeek 客户端
    try:
        chatbot.init_api_key_from_env()
    except Exception as e:
        print(f"❌ API Key 初始化失败: {e}")
        sys.exit(1)

    # 初始化 live2d 运行时（需在创建 OpenGL 窗口前调用）
    live2d.init()

    app = QApplication(sys.argv)
    app.setApplicationName("SSS_bot_live2d")  # 应用程序名称（用于托盘等）

    # 创建并显示桌宠主窗口
    window = chatbotUI.ImageWindow()
    window.setWindowTitle("哈达莉")
    window.show()

    # 进入 Qt 主事件循环，程序在此阻塞直到退出
    app.exec()
    # 释放 live2d 运行时资源
    live2d.dispose()


if __name__ == "__main__":
    main()
