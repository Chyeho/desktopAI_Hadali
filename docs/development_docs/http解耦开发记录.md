# 前后端 HTTP/SSE 解耦开发记录

> 配套文档：[http解耦执行文档.md](./http解耦执行文档.md)
> 记录规则：每个阶段（P1–P4）完成后，除更新验收勾选与提交 commit 外，必须在本文件追加该阶段遇到的值得记录的 bug / 设计冲突 / 环境问题，格式为「问题描述 → 解决方案 → 结果」。
> 原则：不打印任何密钥；不记录用户对话原文。

---

## 基线

- 日期：2026-11-09
- 命令：`.venv\Scripts\python.exe -m pytest -q`
- 结果：`186 passed in 16.05s`
- 环境：Python 3.13；`fastapi` / `uvicorn` 未安装；`httpx` / `httpx_sse` / `pydantic` 已安装（传递依赖）；`qasync` 未安装。
- Git：工作区有未跟踪的 `提示词_前后端HTTP解耦改造.md` 与 `docs/`。

---

## P1：core 去 UI 化

### 状态

- [x] 代码完成
- [x] `pytest -q` 全绿（`186 passed in 13.54s`）
- [x] 验收项逐条通过
- [x] commit

### 问题记录

| 编号 | 问题描述 | 解决方案 | 结果 |
|---|---|---|---|
| P1-1 | 直接删除 `agent/chat_agent.py` 的 `live2d_model` 与 `drive_expression` 会让 P3 之前的旧 UI 失去表情动画，违反“不改变现有功能” | 把“情感 → 动作组”迁到 `client/emotion_map.py`；根 `chatbot.py` 保留为**过渡适配器**：调用 core 拿到 `TurnResult` 后，若旧 UI 传入 `live2d_model`，再由适配器调 `drive_expression`。`core/` 不 import client | 已验证：传入 `live2d_model` 时 emit `FlickDown`（shy）正常；不传时不加载 client 模块 |
| P1-2 | `tests/test_chatbot.py` 用 `patch("chatbot.ChatModelFactory")` 与 `chatbot._agent` 依赖模块级全局；若把 `chatbot.py` 直接替换成 `sys.modules = core.facade`，适配器与 facade 的全局状态会分裂 | 放弃 `sys.modules` 替换；`chatbot.py` 保留自己的 `_agent` / `last_partial_reply` / `ChatModelFactory`，初始化时把 `ChatModelFactory` 作为 `factory_cls` 传给 `core.facade.create_agent()`。这样 patch 命中适配器，core 仍可独立测试 | 已验证：`tests/test_chatbot.py` 15 个用例零改动通过 |
| P1-3 | `ChatAgent.chat()` 返回结构化 `TurnResult` 后，现有测试用 `result["emotion"]` / `result["reply"]` 下标访问 | 用 `TypedDict` 定义 `TurnResult`（运行时就是 dict），既满足结构化要求，又保持 14 个测试零断言改动 | 已验证：`TypedDict` 实例在运行时为普通 dict，下标访问与 `isinstance(..., dict)` 均不变 |
| P1-4 | 执行文档原计划把 `chatbot.py` 改为 `sys.modules[__name__] = core.facade`；但 `tests/test_chatbot.py:141` 仍以 `chat_with_model(..., live2d_model=None)` 调用，facade 若不保留该形参会 `TypeError` | 采用 P1-2 的适配器方案：`chatbot.py` 保留同名函数签名并委托 `core.facade`；`core/facade.py` 只提供无状态函数（`load_env` / `create_agent` / `create_agent_from_env` / `chat` / `switch_mode`），不持有 `_agent` | 已验证：旧入口与旧 UI 调用方式均可用；已回写修正执行文档 P1 表格 |
| P1-5 | 全仓 grep `PySide6\|live2d\|httpx\|fastapi` 在 `core/ agent/ tools/ utils/ modelFactory/` 无命中，但 `import agent.chat_agent` 后 `sys.modules` 出现大量 `httpx.*` | 是 `langchain_openai → openai` SDK 的传递导入，非本层直接 import；验收口径按“本层代码不直接 import”判定 | 记录在案；P2 显式声明 `httpx` 后该传递关系不变，不影响依赖方向 |
| P1-6 | 执行文档称 `tests/test_chat_agent.py` 有 6 处 `live2d_model=None`，实际为 5 处（第 6 处位于 `tests/test_chatbot.py:141`，属适配器签名，需保留） | 只删除 agent 层 5 处实参，断言未动；同步修正文档计数 | `pytest -q` 186 passed |

### 验收结果

- `pytest -q`：`186 passed`。
- `import agent.chat_agent`：未加载 `PySide6` / `live2d`（`httpx` 为 langchain 传递依赖，见 P1-5）。
- `core/ agent/ tools/ utils/ modelFactory/` grep 无 `PySide6|live2d|httpx|fastapi`。
- 真实 Key 联调（验收项 2）留待本机手工执行，未在自动化环境中请求外部模型。

### 未做项

- `core/session.py` 的 `SessionManager` 推迟到 P2：P1 没有多会话调用方，提前实现会产生无调用方的抽象。P2 实现时同步补 `tests/test_session.py`。

---

## P2：server

### 状态

- [x] 代码完成（`protocol/`、`core/session.py`、`core/tracing.py`、`server/*`）
- [x] `pytest -q` 全绿（`244 passed in 15.16s`，新增 58 个用例）
- [x] 验收项逐条通过
- [x] commit

### 问题记录

| 编号 | 问题描述 | 解决方案 | 结果 |
|---|---|---|---|
| P2-1 | SSE 生成器的内部函数写成 `emit(name, model, **fields)`，调用 `emit(..., name=result["emotion"])` 时 `name` 与形参冲突，抛 `TypeError: emit() got multiple values for argument 'name'`，导致 `emotion` 事件被 `error` 事件替代 | 形参改名为 `event_name`，事件字段 `name` 继续通过 `**fields` 传入 | 修复后事件顺序与协议一致，`tests/test_server_api.py` 全绿 |
| P2-2 | FastAPI 的 `RequestValidationError` 默认返回 422，协议 v1 约定参数非法返回 400 | 在 `create_app()` 注册 `RequestValidationError` 异常处理器，统一返回 `400 {"code":"BAD_REQUEST"}` | 非法 `session_id`、空 `text` 均返回 400 |
| P2-3 | `uv add fastapi uvicorn httpx httpx-sse` 会重算依赖并改写 `uv.lock`（新增 71 行），且版本取自镜像最新 | 确认 `pyproject.toml` 显式出现四个依赖：`fastapi>=0.162.2`、`uvicorn>=0.54.0`、`httpx>=0.28.1`、`httpx-sse>=0.4.3`；锁定文件一并提交 | 环境可复现；`pytest` 全绿 |
| P2-4 | `asyncio.Lock` 在 `SessionManager` 中惰性创建：若在无事件循环的同步上下文创建，是否绑定错误 loop | Python 3.10+ 的 `Lock` 创建时不绑定 loop；统一在 `get_lock()`（路由内 / 测试 `asyncio.run` 内）创建，并用 `threading.Lock` 保护字典并发 | `tests/test_session.py` 的串行与隔离用例通过 |
| P2-5 | 手工冒烟时第一次 `GET /v1/health` 在 uvicorn 完成启动前执行，报 `WinError 10061 连接被拒绝` | 客户端改为重试轮询（40 × 250ms）；这是启动竞态，不是服务缺陷 | 重试后 200；P3 的 `server_launcher` 将采用同样的探活重试 |
| P2-6 | 成功分支若走真实 server 会请求外部大模型（费用 / 网络依赖），不适合自动化冒烟 | 成功分支由 `tests/test_server_api.py` 用 `httpx.ASGITransport` + 假服务覆盖；手工冒烟只验 `/v1/health`、`/v1/modes`、`/v1/chat` 错误分支（`mode=nonexistent` → `BAD_REQUEST`）与 `/v1/interrupt` | 事件流格式、seq/turn_id、错误码、idle 收敛均符合协议 |

### 验收结果

- `python -m server --port 8799` 无 GUI 正常启动；`GET /v1/health` → `{"status":"ok","version":"0.1.0","model":"deepseek-chat"}`。
- `GET /v1/modes` 返回 `emotion` / `office` 两个模式及 `display_name`。
- `POST /v1/chat`（`mode=nonexistent`）返回 `turn.start → state(thinking) → error(BAD_REQUEST) → state(idle)`。
- `POST /v1/interrupt` 返回 `{"ok": true}`。
- token：未配置 `HADALI_TOKEN` 放行并只打一条 warning；配置后无/错 token 返回 401（见 `tests/test_server_api.py::TestAuthAndInterrupt`）。
- 未在冒烟中请求真实大模型；成功分支的事件顺序由假服务测试保证。

---

## P3：client

### 状态

- [x] 代码完成（`client/transport`、`client/ui`、`client/voice`、`client/server_launcher.py`、`client/main.py`；根 `main.py` 改为 shim）
- [x] `pytest -q` 全绿（`255 passed in 28.47s`，新增 11 个 transport 用例，旧断言零改动）
- [x] 自动冒烟：后端起停、真实 SSE 端到端、UI 事件映射、窗口与模型渲染
- [x] commit
- [ ] 图形界面手工验收（拖拽 / 滚轮 / 托盘 / 语音 / 表情观感，见文末清单）

### 问题记录

| 编号 | 问题描述 | 解决方案 | 结果 |
|---|---|---|---|
| P3-1 | 要求先做一次不写入依赖的 qasync spike：验证 qasync 与 `QOpenGLWidget` + 120fps `timerEvent` 共存 | 用 `uv pip install --python .venv\Scripts\python.exe qasync`（0.28.0，**未改** `pyproject.toml` / `uv.lock`），临时脚本在 `QEventLoop` 下跑 2.5s，与纯 `QApplication.exec()` 基线对比；spike 后立即 `uv pip uninstall`，环境恢复 | qasync：`ticks=165 frames=158 gl_ok=True`；基线：`ticks=159 frames=154 gl_ok=True`。无 GL 报错、帧数无明显差异。结论：**共存可行，但无收益且需新增依赖**，P3 仍按方案 B（QThread）实施 |
| P3-2 | `SseWorker` 的信号直接连到普通 Python 回调时，PySide6 以**排队方式**投递；测试里 `worker.wait()` 返回后立即断言，事件列表还是空的 | 测试改为 `worker.wait()` 后再 `processEvents()` 轮询（`_wait_until`）。这也从侧面证明：UI 槽函数确实在主线程执行，满足 live2d 单线程约束 | `tests/test_transport.py` 由 3 failed 变为全绿 |
| P3-3 | 若把 `SseWorker.event` 直接接到 UI 方法，跨线程调用依赖 AutoConnection 推断；显式写 `QueuedConnection` 又会与 Qt 的线程亲和性重复 | `worker.event` → `transport.event_received`（信号→信号直连），再由 `ImageWindow` 在主线程接收；`Transport` 只暴露信号，不暴露 worker | 传输线程不触碰任何控件 / `Model.*` |
| P3-4 | 执行文档约定“拉起后健康检查轮询上限 5s”，但本机实测 `python -m server --port 0` 从进程创建到输出 `HADALI_SERVER_READY` 需要 **13.5s**（langchain 等重依赖导入） | `READY_TIMEOUT` 改为 20s；等待期间窗口照常显示，用户提交时提示“后端正在启动，请稍候再试” | 同端口重跑 launcher 冒烟：`ready` 正常、`probe=True`、退出后 `probe=False` |
| P3-5 | 第一次 launcher 冒烟直接报“后端启动失败”，`logs/server.log` 为空 | 根因是 P3-4：5s 超时后在子进程仍在 import 阶段就 `terminate()`，进程来不及写任何日志。修正超时后复现不出；同时补上 `stop()` 里关闭日志文件句柄 | 冒烟通过；失败提示保留“请查看 logs/server.log”便于排查 |
| P3-6 | 复用“已在运行的外部后端”时 token 未知：若客户端自己生成 token 去探活，会被 401 误判为后端不可用，进而重复拉起导致端口冲突 | 探活分两步：先带 token、再不带 token；任一成功即复用，并把实际可用的 token（可能为空串）通过 `ready` 信号回填给传输层 | 手工 `python -m server`（无 token）与自动拉起（带 token）两种场景均可用 |
| P3-7 | `chatbotTTS.py` 迁移到 `client/voice/tts.py` 后，原来的 `_MODULE_DIR` + `.env` 相对定位会失效（读到 `client/voice/.env`） | 改为 `utils.path_tool.get_abs_path('.env')`（项目根定位）；`tests/test_tts.py` 仅改 import 为 `from client.voice import tts as chatbotTTS` | TTS 21 个用例断言零改动通过；`DASHSCOPE_MODEL` 等默认值不变 |
| P3-8 | 执行文档写“P3 移除根 `chatbot.py` 适配器”，但 `tests/test_chatbot.py` 依赖 `chatbot._agent` / `chatbot.ChatModelFactory` 这些模块级全局（15 个用例），删除会使测试断言失效 | **保留** `chatbot.py` 过渡适配器：它只依赖 `core.facade` + `modelFactory`，不 import Qt / live2d / httpx，不违反依赖方向；删除时机改为“测试不再依赖模块级全局之后” | `pytest` 全绿；`client` 无 langchain/openai import |
| P3-9 | 若在 `state=idle` 时一律 `ChatBox.to_input_state()`，会清空正在打字机显示的回复，违反“打字机回复 → 点击恢复输入”的既有交互 | `idle` 只做两件事：`_turn_active=False`；仅当聊天框仍处于 `thinking`（异常路径没收到 text/error）才兜底回输入态。回复态保留，由用户点击恢复 | 事件映射冒烟：`after_idle_state = reply` |
| P3-10 | 迁移后 `MODEL_PATH` 仍按 `chatbotUI.py` 所在目录拼接，拆到 `client/ui/` 后路径会指向不存在的位置 | 改用 `get_abs_path("Resources/v3/hiyori/hiyori_free_t08.model3.json")` | UI 冒烟：`MODEL_PATH_EXISTS=True`、`MODEL_LOADED=True`、`FIT_DONE=True` |

### 自动冒烟结果

- 后端起停：`ServerLauncher` 自动拉起 → `ready(http://127.0.0.1:1864)` → `probe=True` → `shutdown()` 后 `probe=False`（子进程已终止）。
- 真实 SSE 端到端（非法 mode，不请求大模型）：`['turn.start','state','error','state']`，`error.code=BAD_REQUEST`，传输层 `failed` 为空。
- UI 事件映射（注入假 TTS）：
  - `turn.start` → `thinking`；`text.delta` → `reply`（“哈达莉：”）
  - `turn.end` → `speak("你好呀")`；`state=idle` → 仍为 `reply`、`_turn_active=False`
  - `error` → 显示“哈达莉：（出错了）模型超时”、`allow_reset=True`、不播报
  - `interrupt_turn()` → `input`，TTS `stop()` 被调用 1 次
- 窗口渲染：模型加载、自动适配收敛、聊天框初始为 `input`。

### 依赖方向

- `client/**` 无 `langchain` / `openai` / 旧 `chatbot` 门面 import。
- `core/ agent/ tools/ utils/ modelFactory/` 仍无 `PySide6|live2d|httpx|fastapi`。
- 全仓已无 `chatbotUI` / `chatbotTTS` 的代码引用（仅历史注释与测试变量名保留）。

### 待手工验收（需要显示器与声音）

1. `python main.py` 显示桌宠；拖拽、滚轮缩放、托盘、右键菜单。
2. 真实对话：思考中 → 打字机 → 点击恢复输入。
3. 表情动作播放与 1.5s 平滑回常态；说话期间自动眨眼/呼吸开关。
4. 语音按 `TTS_MODE` 播报；新一轮可打断上一轮。
5. 对话中杀掉 server 进程 → 明确错误提示、不卡死；重启客户端后恢复。
6. 说话/动作中按 Esc 或右键“停止当前回复” → 语音与动作立即停止。


---

## P4：打磨与评测

### 状态

- [x] `bench/prompts.jsonl`（20 条）、`bench/run_bench.py`、`bench/result.csv`（运行时生成，已加入 `.gitignore`）
- [x] `client/transport/client.py`：连接失败重试一次 + 显式超时（connect 3s / read 60s）
- [x] `server/routes/chat.py`：错误码细化（连接类异常 → `LLM_ERROR`）、`turn.end` 增加 `first_event_ms`
- [x] 测试补齐：transport 重试 / 5xx 不重试；server 错误码映射与 `first_event_ms`
- [x] README 增加前后端分离启动、独立后端、性能评测章节
- [x] `pytest -q` 全绿（`260 passed in 29.82s`）
- [x] commit

### 问题记录

| 编号 | 问题描述 | 解决方案 | 结果 |
|---|---|---|---|
| P4-1 | 首版 bench 的“首事件延迟”P50 高达 697.9ms，但 SSE 首个 `turn.start` 本应立即下发 | 逐项排除后实测 `httpx.Client()` 在本机初始化需 **1410ms**（证书上下文加载）；`SseWorker` 每轮新建 Client、bench 每条新建 Client、launcher 每次探活也新建 Client，全都被算进了首帧延迟 | 传输层改为整条链路共享一个 Client（`_get_client()`）；打断时只 `response.close()` 不关 Client，避免下一轮重建；bench 与 launcher 复用探活 Client。首事件 P50 **697.9ms → 3.3ms** |
| P4-2 | 修完 P4-1 后，首条 prompt 整轮仍要 5.3s，与后续 1.0–1.6s 差距明显 | 定位为首个 session 首次创建 Agent 的冷启动（P2 已记录约 3s，叠加模型首 token），非链路开销 | bench 汇总与 README 均标注“首轮冷启动，非链路开销”，避免误读为性能回归 |
| P4-3 | “重连一次”若实现不当会重放已发送的 turn，导致同一句话调用两次大模型 | 仅当异常是 `httpx.ConnectError` / `httpx.ConnectTimeout` **且一个事件都没收到**时重试一次（连接从未建立，不可能重复生成）；一旦收到任意帧（含 `turn.start`）失败就上报；HTTP 5xx 不重试 | 新增 2 个用例：`ConnectError` 后重试成功（调用 2 次）、500 只调用 1 次并发出 `failed` |
| P4-4 | 执行文档要求 `first_event_ms` 统计，但没说放在哪个事件、按谁的时钟 | 定义：**请求进入路由 → 首个事件被拼装写出**（服务端 `perf_counter`），放在 `turn.end`；客户端首帧延迟则由 bench 独立计时（端到端） | `protocol/events.py` 的 `TurnEndEvent.first_event_ms` 默认 0.0，向后兼容；新增断言 `>= 0.0` |
| P4-5 | 想把 `retryable` 收紧为“仅 LLM_TIMEOUT/LLM_ERROR/TOOL_ERROR 可重试”，但既有测试断言 `INTERNAL → retryable=True` | 保持 `retryable = code != BAD_REQUEST` 不变，P4 只细化错误码映射（新增连接类异常 → `LLM_ERROR`），不动既有断言 | 既有 server 测试零改动通过 |
| P4-6 | bench 直连真实大模型，若无会话隔离会污染 `chat_history/default.json` | 默认 `--session-id bench`，历史写入 `chat_history/bench.json`；`--limit` 便于先验证连通性；CSV 用 `utf-8-sig` 便于 Excel 打开 | 20 条跑完，`default.json` 未被写入 |
| P4-7 | 服务端探活若每次新建 Client，launcher 的 20s 就绪窗口会被探活自身的 1.4s/次吃掉 | `_LaunchWorker` 懒加载一个探活专用 Client，退出时关闭；`probe()` 支持传入 Client | 探活轮询间隔恢复为 0.2s 级别，就绪判定不再被探活拖慢 |

### 评测结果（DeepSeek，20 条，独立 `bench` 会话）

| 指标 | P50 | P95 |
|---|---|---|
| 首事件延迟 | 3.3 ms | 5.0 ms |
| 整轮总延迟 | 1743.1 ms | 5288.2 ms |

- 工具调用率：45%（9/20，时间 1 条、天气 4 条、搜索 4 条）
- 错误率：0%
- 结果文件：`bench/result.csv`（不入库）

