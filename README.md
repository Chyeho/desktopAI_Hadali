# DesktopAI_Hadali

基于 PySide6 + Live2D 的多功能桌面情感陪伴 AI 助手「哈达莉」。AI 助手形象为 Live2D 模型（HiYori），对话引擎以 LangGraph 情感陪伴主图为核心（支持任意 OpenAI 协议大模型），内置感知门控、ReAct 工具循环、情感标签驱动的表情动画、多 agent 模式扩展通道与可换源的 TTS 语音播报。哈达莉的定位是「伴随在桌面的情感陪伴 AI 助手」——既能自然地陪伴聊天、关心用户日常，也能按需扩展为桌面办公、编程等专用 agent 模式，辅助用户处理实际任务。

## 功能特性

- Live2D 桌宠形象，自动适配窗口大小、随窗口等比缩放
- 与 AI 角色对话（哈达莉），回复流式逐 token 显示
- LangGraph 陪伴主图：感知门控（游戏请求进入占位子图，其余进入陪伴 agent）+ ReAct 工具循环
- AI 具备基础工具调用能力：天气查询 / 联网搜索；可选接入 MCP 工具（未配置自动降级）
- 时间感知：用户消息与 AI 回复自动附加时间戳，UI 侧保持干净文本
- 对话历史持久化：MemorySaver 维持多轮上下文，JSON 镜像保证重启后 AI 仍记得之前的对话
- 已接入部分表情动画，持续开发中（10 种情感标签 → 6 组 hiyori 自带动作，播完平滑过渡回常态）
- 多 agent 模式扩展通道（当前为情感陪伴主模式，办公 / 编程等模式预留）
- 单轮对话框交互：输入 → 思考中 → 回复 → 点击恢复输入
- 半透明聊天框，支持拖拽窗口、滚轮缩放
- 右键菜单：最小化到托盘 / 退出程序

> Live2D 形象来源于 Live2D 官方提供的免费模型（HiYori），仅用于学习与演示用途。

## 项目结构

- `main.py`              程序入口（`client.main` 的 shim，保持 `python main.py` 可用）
- `client/`              客户端（UI 进程）
  - `client/main.py`     客户端入口：OpenGL 初始化 → 拉起/复用后端 → 显示窗口
  - `client/ui/`         ChatBox（三态聊天框）/ Live2DWidget（渲染与表情）/ ImageWindow（主窗口）
  - `client/transport/`  Transport 接口 + SseWorker(QThread) + SSE 事件解析
  - `client/voice/tts.py` 语音合成（qwen3-tts / edge-tts）
  - `client/emotion_map.py` 情感 → 动作组映射与播放
  - `client/server_launcher.py` 后端探活、自动拉起与退出清理
- `server/`              后端（无 GUI）：FastAPI 路由 / 服务容器 / token 校验
- `protocol/`            请求与 SSE 事件模型（client 与 server 共用）
- `core/`                纯逻辑门面与会话管理（`facade` / `session` / `tracing`）
- `chatbot.py`           AI 对话兼容适配器（保留模块级 `_agent` 供既有测试使用）
- `agent/`               AI 对话核心
  - `agent/graph/`       LangGraph 陪伴主图（感知门控 / agent ⇄ tools / 游戏占位子图 / 运行时）
  - `agent/chat_agent.py` legacy 对话引擎（`AGENT_ENGINE=legacy` 时回滚使用）
  - `agent/tool_manager.py` / `mode_configs/` 工具注册表与模式配置
- `modelFactory/`        模型工厂（langchain ChatOpenAI，工厂模式）
- `tools/common/`        公共工具（天气 / 联网搜索）
- `utils/`               工具集（配置 / 日志 / 路径 / 提示词加载 / 时间注入）
- `prompts/`             系统提示词文本（不硬编码在代码中）
- `config/`              配置文件（提示词路径 yaml；MCP 示例 `mcp_servers.example.json`）
- `bench/`               批量评测脚本与固定 prompt（见 `docs/项目技术文档.md`）
- `docs/`                文档：项目技术文档、前后端接口 JSON 契约、开发文档
- `expression_tester.py` Live2D 表情动画调试台（独立运行，见 `docs/项目技术文档.md`）
- `resources.py`         资源目录常量
- `Resources/`           Live2D 模型资源（HiYori 模型 + 动作）

## 运行指南

### 1. .env 配置

在项目根目录创建 `.env` 文件，完整模板如下：

```text
# 环境变量配置文件
# 用于存储敏感信息，如API密钥、数据库连接等

# 1.API密钥（支持任意 OpenAI 协议大模型：DeepSeek / 通义兼容端 / 本地 vLLM 等）
API_KEY=sk-你的llm密钥
# 1.1 大模型接口地址（OpenAI 兼容端点）
BASE_URL=https://api.deepseek.com/v1
# 1.2 大模型名称
MODEL=deepseek-chat

# 2.语音合成(TTS)配置项
# TTS 运行模式（demo / dev）：
#     demo = 演示模式：优先 qwen3-tts，失败时 edge-tts 兜底
#     dev  = 开发模式：仅使用 edge-tts
TTS_MODE=demo
# 2.1  edge-tts 音色
EDGE_TTS_VOICE=zh-CN-XiaoxiaoNeural
# 2.2 阿里云百炼 qwen3-tts 云端 TTS
#     获取 API Key：阿里云百炼控制台 https://bailian.console.aliyun.com/
DASHSCOPE_API_KEY=sk-你的阿里云密钥
#     模型：qwen3-tts-vd-2026-01-26（声音设计音色，HTTP 流式） / qwen3-tts-vc-2026-01-22（声音复刻音色）
#     其他：cosyvoice-v2 / cosyvoice-v3-flash / qwen-audio-3.0-tts-plus 等（WebSocket 接入）
DASHSCOPE_MODEL=qwen3-tts-vd-2026-01-26
#     音色（qwen3-tts 常用）：longxiaoxia_v2 龙小夏(温柔年轻女声) / longxiaochun_v2 龙小淳(温柔姐姐)
#     自定义声音设计/复刻音色：直接填音色 ID（需与模型匹配）
DASHSCOPE_VOICE=音色ID
```

说明：

- `API_KEY` / `BASE_URL` / `MODEL` 为必填项，默认 DeepSeek，也可换任意 OpenAI 协议端。
- 对话引擎默认使用 LangGraph 陪伴主图；如需回滚到旧引擎，设置 `AGENT_ENGINE=legacy`。
- `TTS_MODE=demo` 时优先 qwen3-tts（需 `DASHSCOPE_API_KEY`），失败自动兜底 edge-tts；`dev` 模式只用 edge-tts（免费、零配置）。
- 需要给本机接口加校验时，额外设置环境变量 `HADALI_TOKEN`；未配置时接口仅建议本机调试使用。
- 可选 MCP 工具：把 `config/mcp_servers.example.json` 复制为 `config/mcp_servers.json` 并填入服务；未配置或加载失败时自动降级，不影响启动。也可用 `MCP_CONFIG_PATH` 指向其他配置文件。

### 2. 运行方式

项目为**前后端分离**架构：

- `client/`（PySide6 + Live2D + TTS）：只负责界面、表情动画与语音播报
- `server/`（FastAPI + uvicorn）：持有 Agent、会话历史、工具调用与大模型配置
- 两者通过本机 HTTP + SSE 通信（默认 `http://127.0.0.1:8765`）

1. 安装依赖（使用国内镜像加速）：

   ```
   uv sync
   ```

2. 按上一节完成 `.env` 配置。

3. 启动程序（推荐：客户端会自动探活，必要时拉起后端）：

   ```
   uv run python main.py
   ```

   也可以分开启动，便于查看后端日志 / 多客户端接入：

   ```
   uv run python -m server --port 8765
   uv run python main.py --server-url http://127.0.0.1:8765 --no-spawn
   ```

> 后端按 `session_id` 隔离对话历史（桌面端默认 `default`）。
> `python main.py` 仍是原来的启动入口（现在是 `client/main.py` 的 shim）。

更详细的实现说明见 [项目技术文档](docs/项目技术文档.md)，前后端对接以 [接口 JSON 契约](docs/前后端接口JSON契约_v1.md) 为准。
