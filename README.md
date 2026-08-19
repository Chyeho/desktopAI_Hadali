# DesktopAI_Hadali

基于 PySide6 + Live2D 的桌面 AI 助手。 AI 助手形象为 Live2D 模型（固定神态动作），内置 AI 聊天功能（DeepSeek 大模型）。

## 功能特性

- Live2D 桌宠形象，自动适配窗口大小、随窗口等比缩放
- 与 AI 角色对话（哈达莉），流式显示回复
- 单轮对话框交互：输入 → 思考中 → 回复 → 点击恢复输入
- 半透明聊天框，支持拖拽窗口、滚轮缩放
- 右键菜单：最小化到托盘 / 退出程序

> Live2D 形象来源于 Live2D 官方提供的免费模型（HiYori），仅用于学习与演示用途。

## 运行方式

1. 安装依赖（使用国内镜像加速）：

   ```
   uv sync
   ```

2. 在项目根目录创建 `.env` 文件，写入 API Key（DeepSeek 密钥）：

   ```
   API_KEY=sk-你的DeepSeek密钥
   ```

3. 启动程序：

   ```
   uv run python main.py
   ```

## 项目结构

- `main.py`      程序主入口
- `chatbot.py`   AI 对话逻辑（自动读取 `.env` 中的 `API_KEY`）
- `chatbotUI.py` Live2D 桌宠界面
- `resources.py` 资源目录常量
- `Resources/`   Live2D 模型资源
