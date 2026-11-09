# 给 AI 编程助手的提示词：前后端 HTTP/SSE 解耦改造

# 任务

你是本项目（desktopAI_Hadali，Live2D 桌面情感陪伴 AI 助手「哈达莉」）的 AI 编程助手。

本次任务：在**不改变技术栈、不改变现有功能**的前提下，把当前"单体 PySide 应用"改造成 `core（业务逻辑） / server（HTTP 服务） / client（PySide 前端）` 三层结构，前后端通过 **HTTP + SSE** 通信。

目标不是换前端，而是让 agent 能脱离 GUI 独立运行 / 测试 / 评估，并为将来用 TypeScript 重写前端留出干净接口。

## 第一步：只调研，不改代码

### （1）完整阅读并理解项目（不要只看目录名，要读关键函数实现）

- 入口与启动：`main.py`
- 对话门面：`chatbot.py`
- 核心逻辑：`agent/chat_agent.py`、`agent/tool_manager.py`、`agent/expression_driver.py`、`agent/mode_configs/*`
- 模型层：`modelFactory/factory.py`
- 工具：`tools/common/*`
- 前端：`chatbotUI.py`（重点四个部分：`AIWorker` / `ChatBox` / `Live2DWidget` / `ImageWindow`）
- 语音：`chatbotTTS.py`（重点 `_StreamPlayer` 的 session 打断机制）
- 测试：`tests/`（14 个测试文件）
- 配置与提示词：`prompts/`、`config/`、`utils/*`
- `.env` 只需了解**键名**，禁止读取或输出任何密钥内容

### （2）跑测试建立基线

```
.venv\Scripts\python.exe -m pytest -q
```

记录通过数量、耗时、失败与警告。（参考基线：186 passed / 约 60s）

### （3）在 `docs\development_docs\` 下输出 `http解耦执行文档.md`

必须包含以下章节，内容要具体到**文件名 + 函数名 + 行级耦合点**，不要写空话：

1. **现状架构**：模块依赖关系图（mermaid 或 ASCII），标出所有耦合点
2. **关键耦合点清单**：逐条列出"哪一行/哪个函数把 UI 和 agent 绑死了"
3. **目标架构**：三层职责边界 + 依赖方向规则（core 不许 import 什么、client 不许 import 什么）
4. **目录与文件迁移表**：每个现有文件 → 保留 / 移动 / 拆分 / 新增，并给出理由
5. **通信协议 v1**：接口表、SSE 事件表（event 名、字段、触发时机）、两条完整示例报文
6. **事件循环与线程方案**：qasync 与 QThread 两方案对比结论 + 最终选型理由
7. **分阶段任务清单**：P1–P4，每阶段写明"改哪些文件、怎么验收、怎么回滚"
8. **风险清单**：至少覆盖 live2d 单线程、SSE 断连、TTS 打断、会话与历史、测试 import 失效、双进程启动、错误兜底
9. **不做的事（Out of Scope）**：明确列出本次不改的东西
10. **测试计划**：新增哪些测试文件、如何 mock 大模型与 SSE

### （4）写完文档立即停止

把文档交给我确认。**在我确认之前，除新增 docs 文件外，不要修改任何业务代码。**

# 硬性约束（不可自行放宽）

- 技术栈不变：继续 **PySide6 + live2d-py（`live2d.v3`）**。不引入 Electron / Tauri / TypeScript / React / Vue。
- **Agent 逻辑不重写**：保留现有手写工具调用循环、`MAX_TOOL_STEPS`、`parse_reply_json`、`set_mode` 语义。禁止改造成 LangGraph / ReAct agent。
- **Agent 保持同步（`.invoke`）**，不要在 core 里引入 async。异步只出现在 server 请求处理与 client 传输层；server 里的阻塞调用用 `asyncio.to_thread` 包。
- **不破坏一键启动**：改造后 `python main.py` 仍能启动完整应用（client 负责拉起本地 server）。
- `expression_tester.py` 必须继续能独立运行。
- 现有 14 个测试文件全部保留并继续通过（允许改 import 路径，**禁止删测试或放宽断言**）。
- **依赖方向强制**：
  - `core/`、`agent/`、`tools/`、`utils/`、`modelFactory/` 中不得出现 `PySide6` / `live2d` / `httpx` / `fastapi` 的 import；
  - `client/` 中不得出现 `langchain` / `openai` / `langgraph` 的 import。
- **live2d 单线程**：所有 `Model.Update/Draw/StartMotion/SetParamById` 只能在 Qt 主线程执行；后台只能通过 Qt Signal 请求，不能直接调用。
- 不修改 `.env` 既有键的语义；新增配置项必须有默认值，且"不配置也能跑"。
- 不提交、不打印任何密钥。
- 中文注释与 docstring 风格沿用现有代码（模块顶部写职责、关键函数解释"为什么"）。不要为了"看起来简洁"删掉现有解释性注释。
- 不顺手重构无关代码，不重命名已有公共函数（除任务明确要求）。
- **不要一次性大爆改**：按阶段推进，每阶段结束时项目必须是"可运行 + 测试全绿"。开工前确认 `git status` 干净；每阶段结束提交一次（commit message 中文，格式如 `refactor(server): 新增 SSE 对话接口`）。

# 架构决策（已定，照此执行；若你认为有问题，先提出来，不要私自改）

## 1. 目录布局（低搬迁成本优先）

```
desktopAI_Hadali/
├─ core/                  【新】业务门面与会话层（纯 Python）
│  ├─ facade.py           ← 由 chatbot.py 演化：初始化 + 每轮对话入口
│  ├─ session.py          ← session_id 管理，每会话一个 ChatAgent
│  └─ tracing.py          ← 每轮指标采集（见"可观测性"）
├─ agent/                 【保留原位】chat_agent / tool_manager / mode_configs
├─ modelFactory/ tools/ utils/ prompts/ config/   【保留原位，不动】
├─ protocol/              【新】pydantic 模型：请求体、SSE 事件（前后端唯一协议源）
│  ├─ requests.py
│  └─ events.py
├─ server/                【新】FastAPI 应用
│  ├─ app.py              ← create_app() 工厂函数
│  ├─ routes/chat.py      ← POST /v1/chat（SSE）、POST /v1/interrupt
│  ├─ routes/meta.py      ← GET /v1/health、GET /v1/modes、POST /v1/mode
│  ├─ services.py         ← 组装 core（依赖注入点，测试在此替换假 agent）
│  ├─ security.py         ← 本地 token 校验
│  └─ __main__.py         ← uvicorn 启动，支持 --port 0
├─ client/                【新】PySide 前端
│  ├─ main.py             ← 由 main.py 演化（OpenGL 格式、live2d.init、窗口）
│  ├─ ui/window.py        ← ImageWindow
│  ├─ ui/chat_box.py      ← ChatBox（三态 + 打字机）
│  ├─ ui/live2d_widget.py ← Live2DWidget（渲染 + 表情 + 回常态过渡）
│  ├─ transport/client.py ← HTTP/SSE 客户端（统一接口，内部可换 qasync/QThread）
│  ├─ emotion_map.py      ← 情感标签 → 动作组（从 agent/expression_driver.py 迁出）
│  ├─ voice/tts.py        ← 由 chatbotTTS.py 迁移（逻辑不变，只改 import）
│  ├─ server_launcher.py  ← 拉起/复用本地 server（探活 + 端口 + token）
│  └─ devtools/           ← 开发调试工具的挂载点（expression_tester.py 本体仍留根目录）
├─ main.py                【保留】只做 shim：`from client.main import main`
├─ expression_tester.py   【保留原位，不改逻辑】
└─ tests/
```

搬迁原则：**纯逻辑目录一律不动**（`agent/`、`tools/`、`utils/`、`modelFactory/`、`prompts/`、`config/`），只把"UI 与语音"搬进 `client/`，把"门面"演化成 `core/`。目的：把 import 改动控制在最小范围。

## 2. 必须切断的三个耦合点

1. `chatbot.chat_with_model(user_input, live2d_model=...)`：agent 层不应持有 UI 对象。改为返回结构化 `TurnResult`，表情由 client 依据 `emotion` 自行播放。
2. `agent/expression_driver.py`：把"情感标签 → live2d 动作组"这类**表现层语义**迁到 `client/emotion_map.py`；core 只产出语义标签（happy/sad/...），并保留 `VALID_EMOTIONS` 做校验。
3. `chatbotTTS.speak()` 只由 client 调用；**本期 TTS 不上移 server**（避免在 HTTP 里传 PCM）。但协议里要预留 `audio.*` 事件类型占位。

## 3. 通信协议 v1（字段名照此实现，不要自行改）

```
POST /v1/chat
  body: {"session_id": "...", "text": "...", "mode": "emotion" | null}
  返回: text/event-stream

POST /v1/interrupt   body: {"session_id": "..."}   → {"ok": true}
GET  /v1/health      → {"status":"ok","version":"...","model":"..."}
GET  /v1/modes       → {"current":"emotion","modes":[{"name":"...","display_name":"..."}]}
POST /v1/mode        body: {"mode":"office"}       → {"ok":true,"current":"office"}
```

鉴权：请求头 `X-Hadali-Token`，由 client 启动 server 时随机生成并通过环境变量传入；server 未配置 token 时（独立调试场景）允许放行。

SSE 事件（每条都带 `seq`、`turn_id`、`ts`）：

| event | 关键字段 | 说明 |
|---|---|---|
| `turn.start` | turn_id, mode | 一轮开始 |
| `state` | value: thinking / speaking / idle | 状态机 |
| `text.delta` | text | 本期整段一次性下发，字段必须支持后续增量 |
| `text.done` | text | 最终完整文本 |
| `emotion` | name, intensity? | 语义情感标签 |
| `tool.call` / `tool.result` | name, args / ok, duration_ms | 工具过程（本期只落日志也可以） |
| `turn.end` | reply, emotion, latency_ms | 本轮结束 |
| `error` | code, message, retryable | 错误 |

设计要求：客户端把"逐字显示"当成展示动画，与服务端是否流式无关。**本期服务端仍返回整段文本，但事件结构必须能无痛升级为真流式。**

`protocol/events.py` 用 pydantic 定义上述模型，server 用它序列化、client 用它反序列化。**禁止两边各写一份 dict。**

## 4. 事件循环：qasync 是可选增强，不是硬依赖

先做 **30–60 分钟 spike**：在真实窗口里同时跑 `QApplication` + `qasync.QEventLoop` + `Live2DWidget`（120fps timer），确认：

- 表情动作、打字机、TTS 播放正常；
- 连续 5 轮对话无卡顿、无 GL 报错。

结论规则：

- **spike 通过** → 采用 `qasync + httpx.AsyncClient + httpx_sse`。此时主线程内禁止任何阻塞调用（包括启动 server 的健康检查轮询，用 `asyncio.to_thread` 或短超时）。
- **spike 30 分钟内未跑通** → 直接用 `QThread + httpx.Client.stream() + iter_lines()`，不要继续调试 qasync。
- 两种实现都必须实现同一个 `Transport` 接口：UI 层只认 `on_event(event)` 回调 + `send(text)` + `interrupt()`。

`httpx` 是本项目必需依赖（目前通过 langchain 间接装了 `httpx` / `httpx_sse`），请在 `pyproject.toml` 中**显式声明**，不要依赖传递依赖。

## 5. 会话与历史

- 现有 `HistoryStore` 是全局单文件（`chat_history/default.json`）。改造后由 `core/session.py` 按 `session_id` 创建 `ChatAgent`，默认 session 继续沿用 `default.json`，保证老对话记录不丢。
- 同一 session 的请求必须串行（per-session 锁）；不同 session 可并行。本期 UI 仍为单轮阻塞，不做并发 turn。

## 6. 可观测性（"能评估 agent"的落地，必须做）

每轮对话在 server 侧追加一行 JSON 到 `logs/turns.jsonl`，字段至少：

`turn_id, session_id, mode, model, user_input_len, reply_len, emotion, tool_calls[{name,ok,duration_ms}], steps, latency_ms, first_event_ms, error`

由 `core/tracing.py` 采集，日志复用 `utils/logger_handler`。**不要打印用户原文全文**，只记录长度与截断摘要。

## 7. 启动方式

- `python main.py` → client 启动 → `server_launcher` 先探活（默认 `127.0.0.1:8765`）；不通则 `subprocess.Popen([sys.executable, "-m", "server", "--port", ...])` 拉起，健康检查超时 5s。失败时 UI 明确提示"后端未就绪"，但桌宠仍要能显示，不能黑屏或卡死。
- 支持 `--server-url` / 环境变量 `HADALI_SERVER_URL` 连接已运行的后端（为将来前后端分离部署留口）。
- `python -m server --port 8765` 必须能在**无 GUI、无显示器**环境独立跑通（P2 的验收标准）。

# 分阶段计划（确认文档后按此推进）

- **P1 core 去 UI 化**（不动 server/client）
  去掉 `live2d_model` 参数；`TurnResult` 结构化返回（reply/emotion/mode/tool_calls/latency）；`emotion_map` 迁出；`chatbot.py` 演化成 `core/facade.py`，可保留兼容薄壳供现有测试过渡。
  验收：`pytest` 全绿 + `python -c` 直接跑一轮对话拿到中文字段。
- **P2 server**（FastAPI + SSE + DI + token）
  验收：`pytest tests/test_server_api.py`（用 `httpx.ASGITransport` + 假 agent）；`curl -N` 能看到完整事件流；server 进程可独立运行。
- **P3 client**（transport + UI 拆分 + launcher + 打断）
  验收：下面「验收清单」逐条通过。
- **P4 打磨**（错误重试、README/docs、依赖声明、批量评测脚本）
  `bench/run_bench.py`：读 `bench/prompts.jsonl`（20 条）→ 打 SSE → 输出 `bench/result.csv`（含 P50/P95 延迟、工具调用率、错误率）。这是"能单独测试评估 agent 性能"的落地物。

每阶段结束必须汇报：改动的文件列表、验收结果、未做项及原因、下一阶段风险。

# 验收清单（P3 结束时逐条自测并打勾）

1. `python main.py` 正常显示桌宠；模型自适应、拖拽、滚轮缩放、托盘、右键菜单均正常
2. 输入 → 思考中 → 打字机回复 → 点击恢复输入
3. 表情按 emotion 播放，并在 1.5s 内平滑回常态；说话期间自动眨眼/呼吸的开关逻辑不变
4. 语音按现有 `TTS_MODE` 正常播报；新一轮回复能打断上一轮播报（session 机制不退化）
5. 杀掉 server 进程 → 客户端给出明确错误提示、不卡死；重启后恢复可用
6. 说话中途 `POST /v1/interrupt` → 语音与动作立即停止
7. `pytest -q` 全绿；`python -m server --port 0` 在无 GUI 环境可跑
8. `expression_tester.py` 仍可独立运行
9. `git log` 能看到分阶段提交；`git status` 干净

# 遇到以下情况必须先停下来问我

- 需要改 Agent 的核心语义（提示词格式、JSON 输出约定、工具白名单机制）
- 需要修改现有测试的断言（而不是 import 路径）
- 需要新增语言/框架依赖（除 fastapi / uvicorn / httpx）
- 发现现有功能有 bug（先记录，不要顺手改）
- 进度超出你预估的 1.5 倍

现在开始：**第一步只做调研和 `docs/项目现状与解耦执行方案.md`，然后停下来等我确认。**

