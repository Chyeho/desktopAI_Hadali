# DesktopAI_Hadali

基于 PySide6 + Live2D 的桌面情感陪伴 AI 助手「哈达莉」。形象为 Live2D 模型（HiYori），对话引擎以 LangGraph 情感陪伴主图为核心（兼容任意 OpenAI 协议大模型），具备感知门控、ReAct 工具循环、情感标签驱动的表情动画、可换源 TTS 语音播报与可选 MCP 工具扩展。哈达莉既陪伴聊天、关心日常，也可按需扩展为办公、编程等专用 agent 模式。

## 功能特性

- Live2D 桌宠形象，随窗口等比缩放
- 流式对话：回复逐 token 显示，支持思考中打断
- LangGraph 陪伴主图：感知门控（游戏请求进入占位子图，其余进入陪伴 agent）+ ReAct 工具循环
- 内置工具：天气查询 / 联网搜索；可选接入 MCP 工具（未配置自动降级）
- 时间感知：消息自动附加时间戳，UI 展示保持干净文本
- 对话历史持久化：MemorySaver 维持多轮上下文，JSON 镜像保证重启后仍记得之前的对话
- 情感动画：10 种情感标签映射到 6 组 HiYori 动作，播完平滑回到常态
- 多 agent 模式扩展通道（当前为情感陪伴主模式，办公 / 编程等预留）
- 半透明聊天框，支持拖拽窗口、滚轮缩放；右键菜单可最小化到托盘或退出

> Live2D 形象来源于 Live2D 官方免费模型（HiYori），仅用于学习与演示。

## 项目结构

- `main.py`              程序入口（`client.main` 的 shim，保持 `python main.py` 可用）
- `client/`              客户端（UI 进程）
  - `client/main.py`     客户端入口：初始化 OpenGL → 启动后端并等待就绪 → 显示窗口
  - `client/ui/`         ChatBox（三态聊天框）/ Live2DWidget（渲染与表情）/ ImageWindow（主窗口）
  - `client/transport/`  Transport 接口 + SseWorker(QThread) + SSE 事件解析
  - `client/voice/tts.py` 语音合成（qwen3-tts / edge-tts）
  - `client/emotion_map.py` 情感 → 动作组映射与播放
  - `client/server_launcher.py` 后端探活、自动拉起与退出清理
- `backend/`             后端（无 GUI）
  - `backend/api/`       FastAPI 路由 / 服务容器 / token 校验（`python -m backend`）
  - `backend/agent/`     LangGraph 陪伴主图、历史与回合类型、公共工具
  - `backend/core/`      纯逻辑门面与会话管理（`facade` / `session` / `tracing`）
  - `backend/protocol/`  前后端共用的请求与 SSE 事件模型
  - `backend/model_factory/` 模型工厂（langchain ChatOpenAI，工厂模式）
- `archive/legacy_multi_mode/` 旧版多模式 agent 归档（不参与运行与测试）
- `utils/`               配置 / 日志 / 路径 / 提示词 / .env / 时间注入工具
- `prompts/`             系统提示词文本（不硬编码在代码中）
- `config/`              提示词路径 yaml；MCP 示例 `mcp_servers.example.json`
- `tests/`               单元测试（`pytest`，覆盖逻辑模块与陪伴主图）
- `evals/`               行为评测（确定性回归 + 可选 live 冒烟）
- `bench/`               真实模型性能基准（延迟 / 工具率，需 API Key 与网络）
- `docs/`                技术文档、前后端接口 JSON 契约、开发文档
- `expression_tester.py` Live2D 表情动画调试台（独立运行）
- `resources.py`         资源目录常量
- `Resources/`           Live2D 模型资源（HiYori 模型 + 动作）

## 运行指南

### 1. 前置依赖

| 依赖 | 要求 | 说明 |
| --- | --- | --- |
| Python | 3.13+ | 项目声明 `requires-python >=3.13`，在 3.13.0 验证 |
| uv | 建议 0.10+ | 依赖管理与运行入口（`uv sync` / `uv run`），在 0.10.12 验证 |
| Node.js + npm | 18+（可选） | 仅部分 MCP 服务通过 `npx` 提供；不接入这类服务可不装。在 Node v24.10.0 / npm 11.19.0 验证 |
| Windows | 10/11 | Live2D 透明窗口依赖 OpenGL |

`uv` 安装后自带 `uvx`，用于运行 Python 版 MCP 服务（如 `mcp-server-fetch`）。

### 2. .env 配置

在项目根目录创建 `.env`，模板如下：

```text
# 环境变量配置文件（敏感信息，勿提交）

# 1. 大模型连接（支持任意 OpenAI 协议：DeepSeek / 通义兼容端 / 本地 vLLM 等）
API_KEY=sk-你的llm密钥
BASE_URL=https://api.deepseek.com/v1
MODEL=deepseek-chat

# 2. 语音合成（TTS）
# TTS_MODE=demo：优先 qwen3-tts，失败时 edge-tts 兜底；dev：仅 edge-tts
TTS_MODE=demo
EDGE_TTS_VOICE=zh-CN-XiaoxiaoNeural
# 阿里云百炼 qwen3-tts（可选，demo 模式优先使用）
DASHSCOPE_API_KEY=sk-你的阿里云密钥
DASHSCOPE_MODEL=qwen3-tts-vd-2026-01-26
DASHSCOPE_VOICE=音色ID
```

说明：

- `API_KEY` / `BASE_URL` / `MODEL` 为必填，默认 DeepSeek。
- `TTS_MODE=demo` 需 `DASHSCOPE_API_KEY`，失败自动兜底 edge-tts；`dev` 模式只用 edge-tts（免费、零配置）。
- 其余可选环境变量：

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `HADALI_TOKEN` | 空 | 后端接口校验 token；未配置仅建议本机使用 |
| `MCP_CONFIG_PATH` | `config/mcp_servers.json` | MCP 配置文件路径 |
| `MCP_LOAD_TIMEOUT` | `30` | 单个 MCP 服务加载超时（秒） |

### 3. MCP 配置（非强制）

不配置时仅使用内置的天气 / 联网搜索工具，功能正常。

1. 复制配置模板：

   ```powershell
   copy config\mcp_servers.example.json config\mcp_servers.json
   ```

2. 按需填写 `mcpServers`（支持 `stdio` / `sse` / `streamable_http`）。推荐示例：

   ```json
   {
     "mcpServers": {
       "filesystem": {
         "transport": "stdio",
         "command": "npx",
         "args": ["-y", "@modelcontextprotocol/server-filesystem", "D:\\soft\\ai_workspace"]
       },
       "fetch": {
         "transport": "stdio",
         "command": "uvx",
         "args": ["mcp-server-fetch"]
       },
       "duckduckgo_search": {
         "transport": "stdio",
         "command": "uvx",
         "args": ["duckduckgo-mcp-server"]
       },
       "context7": {
         "transport": "stdio",
         "command": "npx",
         "args": ["-y", "@upstash/context7-mcp"]
       }
     }
   }
   ```

3. 重启后端（重开客户端即可）。配置只在构建 agent 工具时读取并缓存；MCP 工具在**第一条消息**时加载，首轮可能稍慢。
4. 验证日志出现 `[graph.tooling]MCP 服务 filesystem 工具：['filesystem_read_file', ...]`，工具名带服务名前缀。
5. 对话中直接描述任务，或点名“用 context7 查一下这个库的文档”。

注意事项：

- 多个服务**逐个独立加载**，某个服务包名错误 / 启动失败 / 超时只跳过自身并打印原因链，不影响其他服务，也不影响聊天。
- `uvx` 服务首次启动会安装依赖（`mcp-server-fetch` 等可能较慢）；可先 `uv tool install mcp-server-fetch` 预热，或调大 `MCP_LOAD_TIMEOUT`。
- Windows 下 `npx` 报 `EPERM ... _cacache\tmp` 表示 npm 缓存目录不可写；可在该服务配置里加 `"env": {"npm_config_cache": "D:\\可写目录"}`。
- 部分 npm 包（如 `duckduckgo-mcp`）依赖 Bun；未安装 Bun 时建议改用 `uvx duckduckgo-mcp-server`。
- 真实配置可能含密钥，已在 `.gitignore` 中忽略。

### 4. 运行方式

前后端分离：`client/` 负责界面、表情与语音，`server/` 持有 Agent、历史、工具与大模型配置，二者通过本机 HTTP + SSE 通信（默认 `http://127.0.0.1:8765`）。

1. 安装依赖：

   ```powershell
   uv sync
   ```

2. 完成 `.env`（以及可选的 MCP）配置。

3. 启动（推荐：客户端自动探活，必要时拉起后端）：

   ```powershell
   uv run python main.py
   ```

   客户端会**先启动并等待后端就绪，再显示桌宠窗口**，避免后端未就绪时提前对话；首次等待主要来自后端导入依赖。若后端启动失败，窗口仍会显示并给出错误提示。

   也可分开启动，便于查看后端日志或多客户端接入：

   ```powershell
   uv run python -m backend --port 8765
   uv run python main.py --server-url http://127.0.0.1:8765 --no-spawn
   ```

4. 运行测试与评测：

   ```powershell
   uv run pytest -q                     # 单元测试（无需 API Key）
   uv run pytest evals/ -q              # 行为评测（确定性回归，无需 API Key）
   $env:RUN_LIVE_EVALS = "1"
   uv run pytest evals/live -m live -q  # 实时冒烟（需 .env 配置 API_KEY）
   ```

   `tests/` 覆盖模块逻辑，`evals/` 覆盖路由/工具/时间/容错/流式/记忆等行为回归，
   `bench/` 用真实模型统计延迟与工具调用率，三者分工详见 [评测说明](evals/README.md)。

> 后端按 `session_id` 隔离历史（桌面端默认 `default`）。
> `python main.py` 仍是原入口（现为 `client/main.py` 的 shim）。

更详细的实现说明见 [项目技术文档](docs/项目技术文档.md)，前后端对接以 [接口 JSON 契约](docs/前后端接口JSON契约_v1.md) 为准。
