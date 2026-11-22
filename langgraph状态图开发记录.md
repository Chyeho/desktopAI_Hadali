# LangGraph 状态图开发记录

> 配套文档：[langgraph状态图执行文档.md](./langgraph状态图执行文档.md)
> 记录规则：每个阶段（P0–P8）完成后，除更新执行文档勾选与提交 commit 外，必须在本文件追加该阶段值得记录的 bug / 设计冲突 / 环境问题，格式为「问题描述 → 解决方案 → 结果」。
> 原则：不打印任何密钥；不记录用户对话原文。

---

## 基线

- 日期：2026-11-21
- 命令：`.venv\Scripts\python.exe -m pytest -q`
- 结果：`260 passed in 50.27s`
- 环境：Python 3.13；`langgraph 1.2.11`、`langgraph-prebuilt 1.1.0`、`langgraph-checkpoint 4.2.0`、`langchain-core 1.6.1`。
- 依赖缺口：`langgraph-jev-router`、`mcp`、`langchain-mcp-adapters` 均未安装。
- 代码基线：
  - 对话引擎仍是 `agent/chat_agent.py` 手写 `bind_tools` 循环；
  - `text.delta` 一次性下发整段回复，客户端做打字机；
  - 工具为时间 / 天气 / 搜索，时间工具对 LLM 暴露；
  - 记忆为 `chat_history/<session>.json` 滑动窗口；
  - `root_graph.py` 为未接入的旧原型，导入 `langgraph_jev_router` 会失败。
- Git：工作区有未跟踪的 `root_graph.py`、`hadali新架构设计.txt`、`langgrapph状态图提示词.md`；本次新增两份文档不提交。

---

## 计划阶段

| 阶段 | 内容 | 状态 |
| --- | --- | --- |
| P0 | 依赖与 FakeJev / MCP API 核验 | 已完成 |
| P1 | 主图骨架 + perception_gate（仅 chat） | 已完成 |
| P2 | 时间能力迁移 + ReAct 工具循环 | 已完成 |
| P3 | 时间注入 + 流式输出 + 情绪标签 | 已完成 |
| P4 | MemorySaver + 多轮上下文 + JSON 镜像 | 已完成 |
| P5 | 游戏占位子图 + FakeJev 0.7 路由 | 已完成 |
| P6 | 接入 server/client，流式 SSE | 已完成 |
| P7 | MCP 可选接入与降级 | 已完成 |
| P8 | 测试、README、技术文档、gitignore 收尾 | 已完成 |

---

## 设计决策记录

| 编号 | 决策 | 原因 | 影响 |
| --- | --- | --- | --- |
| D1 | 新增 `CompanionGraphAgent`，`AGENT_ENGINE` 切换 | 保留 260 条既有测试与一键回滚 | 旧 `ChatAgent` 不动 |
| D2 | 图引擎用 `[emotion:xxx]` 前缀 + 纯文本 | 避免 JSON 结构污染 token 流；时间后缀由节点追加，天然不入流 | 新旧引擎输出契约不同，runner 负责转换 |
| D3 | server 逐 token 发 `text.delta`，client 增量显示 | 满足“流式输出”且 UI 不显示时间戳 | 需改 ChatBox 显示逻辑，保留一次性降级 |
| D4 | FakeJev 优先，失败回落关键词规则 | 依赖 API 未核验，需保证可运行 | `perception.py` 内做适配层 |
| D5 | MCP 可选依赖，失败只告警 | 未配置时不能影响启动 | `tooling.py` 内隔离导入 |
| D6 | 时间相关函数迁至 `utils/time_utils.py`，删除 `tools/common/get_time.py` | 时间不再作为 agent 工具，避免死代码；统一内部调用入口 | `ALL_TOOLS`、模式白名单、legacy 提示词同步移除；legacy 回滚路径失去时间工具 |
| D7 | 记忆用 MemorySaver + JSON 镜像 | 满足 checkpointer，同时不回退“重启仍记得” | 首次注入 + 每轮写回 |

---

## 阶段问题记录

### P0：依赖与 API 核验

- [x] 代码完成
- [x] `pytest -q` 全绿
- [x] 验收项通过
- [x] commit

| 编号 | 问题描述 | 解决方案 | 结果 |
| --- | --- | --- | --- |
| P0-1 | 项目由 uv 管理，`.venv` 内没有 pip，`python -m pip list` 直接失败 | 改用 `uv add` 安装并锁定依赖 | 成功，`pyproject.toml` + `uv.lock` 同步 |
| P0-2 | `langgraph-jev-router` 实际 API 与 `root_graph.py` 是否一致未知 | 导入后检查签名：`FakeJev(rules=None, *, decide=None, latency_ms=0.0, fail_with=None)`、`ChoiceRequest(question, options, state, model)`、`settings.configure(**kwargs)` | 与原型完全一致，无需适配层 |
| P0-3 | FakeJev 关键词规则置信度能否稳定越过 0.7 阈值 | 阅读源码：`_keyword_decide` 单命中为 `0.70 + jitter(0~0.05)`，`jitter=0` 时等于 0.70 不满足 `>0.7`；2 命中为 `0.78 + jitter`，3 命中为 `0.86 + jitter` | 规则设计结论：游戏关键词需让单条输入至少命中 2 个（如「五子棋」+「棋」），P1/P5 按此覆盖测试 |
| P0-4 | MCP 适配器导入路径与调用方式未知 | 检查 `langchain_mcp_adapters.client`：`MultiServerMCPClient(connections=None)` 可构造，`get_tools(*, server_name=None) -> list[BaseTool]` 为同步方法 | P7 可直接用同步调用，失败降级为 `[]` |

### P1：主图骨架 + perception_gate

- [x] 代码完成
- [x] `pytest -q` 全绿
- [x] 验收项通过
- [x] commit

| 编号 | 问题描述 | 解决方案 | 结果 |
| --- | --- | --- | --- |
| P1-1 | FakeJev 中 chat 关键词会稀释游戏置信度：配置「陪我」后，「陪我下盘棋」只有 0.56，无法过 0.7 | chat 规则不配任何关键词，只保留 game 规则；无命中时 FakeJev 天然返回低置信度 | 「来下盘五子棋」0.89、「陪我下盘棋」0.78、「来一局」0.78，均可稳定进游戏 |
| P1-2 | 系统提示词若写入 state.messages 会污染持久化历史，且每轮重复累积 | 节点内每轮临时拼 `SystemMessage`，只把 AI 回复写回 state | state 中仅 human / ai 消息，测试已覆盖 |
| P1-3 | P1 尚未接入 checkpointer，runner 无持久化上下文 | runner 暂存 `self.messages`，每轮以完整消息列表 invoke；P4 改为 MemorySaver + thread_id | 多轮上下文测试通过，P4 再替换 |

### P2：时间能力迁移 + ReAct 工具循环

- [x] P2-A 时间能力迁移（`utils/time_utils.py`，删除 `tools/common/get_time.py`）
- [x] P2-B ReAct 工具循环
- [x] 代码完成
- [x] `pytest -q` 全绿
- [x] 验收项通过
- [x] commit

| 编号 | 问题描述 | 解决方案 | 结果 |
| --- | --- | --- | --- |
| P2-1 | 删除时间工具后，legacy 工具循环测试失去“本地无网络工具”，若改用天气工具会发起真实网络请求 | 测试注入 `_fake_echo` 本地假工具 + `ToolManager` 桩 | `test_chat_agent` 两个工具循环用例保持离线并通过 |
| P2-2 | 时间后缀重复追加会污染历史消息 | `with_reply_time` 先 `strip_reply_time` 再追加；`with_user_time` 同理 | 幂等性测试通过 |
| P2-3 | `utils/time_utils.py` 若读取环境变量会降低可测性 | 全部函数通过 `dt` / `fmt` 参数注入，不读环境 | 单测可用固定时间断言 |
| P2-4 | `AgentNode` 绑定的工具与 `ToolNode` 执行的工具若不一致，会出现“模型请求了 ToolNode 没有的工具” | `build_main_graph` 统一解析一次 `agent_tools`，同时传给 `AgentNode` 与 `ToolNode`；测试可直接注入 `tools` | 工具循环与注入测试通过 |
| P2-5 | 工具异常若直接抛出会中断整张图 | `ToolNode(..., handle_tool_errors=True)` 把异常转 `ToolMessage`，agent 再组织陪伴式回复 | 异常工具测试通过，图正常结束 |

### P3：时间注入 + 流式输出

- [x] 代码完成
- [x] `pytest -q` 全绿
- [x] 验收项通过
- [x] commit

| 编号 | 问题描述 | 解决方案 | 结果 |
| --- | --- | --- | --- |
| P3-1 | 节点内用 `llm.invoke` 时，真实 ChatOpenAI 不产生 token 回调，`stream_mode="messages"` 只能拿到整段文本 | 节点优先 `llm.stream` 聚合成一条消息，失败再回落 `invoke` | `stream_chat` 可逐 token 产出；非流式桩模型自动回落 |
| P3-2 | 情绪标签可能跨 token，且标签后的换行会漏到 UI | `EmotionStreamFilter` 缓冲未闭合的 `[`，剥离标签后用 `_after_tag` 吞掉紧随的空白 | 跨 token 标签测试通过，delta 中无前导换行 |
| P3-3 | 最终 AIMessage 带时间后缀，若直接下发会把时间戳暴露到 UI | 流式 token 来自 LLM 原始片（天然无后缀）；`reply` 统一 `strip_reply_time` | UI/SSE 只拿到干净正文，历史仍保留后缀 |

### P4：checkpointer + 多轮上下文

- [x] 代码完成
- [x] `pytest -q` 全绿
- [x] 验收项通过
- [x] commit

| 编号 | 问题描述 | 解决方案 | 结果 |
| --- | --- | --- | --- |
| P4-1 | 历史注入若用 `update_state` 需处理 `as_node` 语义，容易把下一步路由弄错 | 改为首次 invoke 时把 restored messages 与新用户消息一起传入；后续仅传新消息，由 checkpointer 累积 | 跨实例恢复测试通过 |
| P4-2 | 用裁剪后的 `self.messages` 计算 `base_len` 会与 checkpointer 全量消息错位，导致每轮 metrics 虚高 | `self.messages` 始终保存全量状态；裁剪只发生在 `HistoryStore.replace` 的 JSON 副本上 | 第二轮 `steps` 仍为 1，工具统计正确 |
| P4-3 | 编译图挂了 MemorySaver 后，直接 `graph.invoke(state)` 因缺少 `thread_id` 报错 | runner 统一传 `{"configurable": {"thread_id": session_id}}`；测试直接调图时补 `CFG` | 全量测试通过 |

### P5：游戏子图 + FakeJev 路由

- [x] 代码完成
- [x] `pytest -q` 全绿
- [x] 验收项通过
- [x] commit

| 编号 | 问题描述 | 解决方案 | 结果 |
| --- | --- | --- | --- |
| P5-1 | 子图内模型 token 的 `messages` 事件挂在父节点 `game_subgraph`，且只包含带时间后缀的最终消息，转发会让 UI 看到时间戳 | 本期不转发子图 token，消费者用 `done.reply` 一次性降级显示；`demo.py` 已按“无 delta 则打印 reply”处理 | 游戏回复在 UI 侧仍干净；P6 server 同样走一次性降级 |
| P5-2 | 提示词里写的 `calm` / `confused` 不在 `expression_driver.VALID_EMOTIONS` 中，会被回退成 neutral | 陪伴提示词与游戏提示词统一为实际支持的 10 个标签 | 情绪标签校验无告警，测试覆盖 relaxed/thinking |
| P5-3 | 子图若单独 `compile(checkpointer=...)` 会与主图各存一份状态，导致上下文割裂 | `build_game_subgraph` 不带 checkpointer，作为主图节点共享主图检查点 | 子图与主图消息连续，路由测试通过 |

### P6：接入 server/client

- [x] 代码完成
- [x] `pytest -q` 全绿
- [ ] 验收项通过（UI 手工验收留到 P8）
- [x] commit

| 编号 | 问题描述 | 解决方案 | 结果 |
| --- | --- | --- | --- |
| P6-1 | 图执行是同步阻塞的，直接在 `event_stream` 里迭代会卡住整个 server 事件循环 | `_iterate_sync_generator` 用工作线程生产 + `asyncio.Queue` 消费，异常也经队列回传主线程 | 流式期间其他请求仍可响应 |
| P6-2 | legacy `ChatAgent` 没有 `stream_chat`，路由不能假设一定有流 | `services.stream_chat` 探测方法可调用性，不支持返回 `None`；路由退回 `asyncio.to_thread` + 一次性 `text.delta` | 新旧引擎共用同一 SSE 契约，现有一次性用例保持通过 |
| P6-3 | 流式生成器正常结束但没有 `done` 时，若静默返回会导致缺 `text.done`/`turn.end` | 路由在 `result is None` 时抛 `RuntimeError("流式对话未返回最终结果")`，由统一错误分支映射为 `INTERNAL` 并收敛 idle | `test_stream_without_done_emits_internal_error` 覆盖 |
| P6-4 | `CompanionGraphAgent` 单模式，但 server 的模式接口会调用 `set_mode` | 保留同签名方法，仅记录日志后忽略 | 切换 office 不报错，回复仍是陪伴模式 |

### P7：MCP 接入与降级

- [x] 代码完成
- [x] `pytest -q` 全绿
- [x] 验收项通过
- [x] commit

| 编号 | 问题描述 | 解决方案 | 结果 |
| --- | --- | --- | --- |
| P7-1 | 实测 `MultiServerMCPClient.get_tools` 是 `async def`（与 P0 记录的“同步方法”不符），而工具装配发生在同步构造路径，且可能已在事件循环线程内 | 新增 `_run_coro`：在独立守护线程里 `asyncio.run(client.get_tools())`，主线程 `join(timeout)`；超时抛 `TimeoutError` 并被降级捕获 | 同步/异步调用场景均可用，未配置时零开销 |
| P7-2 | MCP 配置格式不统一（`{"mcpServers": {...}}` 与直接 connections 两种常见写法） | `_read_mcp_connections` 优先取 `mcpServers`，否则把根对象当 connections；非对象/空对象按失败或跳过处理 | 两种配置均可加载，坏配置只告警 |
| P7-3 | 多个 MCP 服务可能出现同名工具，与天气/搜索冲突 | `MultiServerMCPClient(..., tool_name_prefix=True)` 给工具名加服务前缀 | 合并后工具名唯一 |
| P7-4 | 测试若读取开发者本地真实 MCP 配置会让用例结果不稳定 | `test_graph_tooling.py` 的 autouse fixture 把 `MCP_CONFIG_PATH` 指向 `tmp_path` 下不存在的文件，并前后清空工具缓存 | 用例离线、可重复 |

### P8：测试与文档收尾

- [x] 代码/测试完成
- [x] `pytest -q` 全绿（收尾时 341 passed；后续修复后 343 passed）
- [ ] CLI/UI 手工验收 8 条（需真实 API Key，留待人工执行）
- [x] commit

| 编号 | 问题描述 | 解决方案 | 结果 |
| --- | --- | --- | --- |
| P8-1 | `tests/README.md` 仍停留在 186 条用例、包含已删除的 `test_get_time.py`，与当前测试集不符 | 按 `pytest --collect-only` 重新统计 25 个文件 / 341 条，补齐图引擎、facade、server、MCP 等行与离线隔离说明 | 测试文档与实际一致 |
| P8-2 | 技术文档仍在描述手写工具循环、JSON 严格输出与“时间工具” | 重写对话流程，补充引擎切换、主图结构、感知门控、时间注入、情绪契约、MemorySaver + JSON 镜像、MCP 降级 | 文档与新架构一致 |
| P8-3 | 8 条验收中的“答对 / 人格化 / UI 干净”依赖真实模型与 GUI，无法在无 Key 的自动化环境完成 | 拆分验收：可自动化的（工具列表、路由、降级、时间注入/剥离）以单测覆盖；真实模型与 UI 项记录为待人工验收 | 自动化项全部通过，手工项已在执行文档标注 |

### 上线后修复：第二次启动报 tool 消息错误

| 编号 | 问题描述 | 解决方案 | 结果 |
| --- | --- | --- | --- |
| FIX-1 | 第一次启动聊天正常，第二次启动 AI 输出报错：`Messages with role 'tool' must be a response to a preceding message with 'tool_calls'`（`invalid_request_error`） | 根因是 JSON 历史镜像完整保存了 `AIMessage(tool_calls)` + `ToolMessage`，重启后 `HistoryStore._trim` 可能从中间截断，恢复出的历史以孤立的 `ToolMessage` 开头。在 `agent/graph/runner.py` 新增 `_clean_history()`：恢复时与写镜像前都剥离 `ToolMessage` 和带 `tool_calls` 的 `AIMessage`，只保留纯对话消息；`HistoryStore` 的通用行为不变（legacy 仍完整保留） | 二次启动不再注入非法工具消息；工具结果仍通过最终 AI 回复进入记忆。新增 2 条回归用例，全量 343 passed |
| FIX-2 | 对话中时间字符串泄漏到 UI（流式增量未按最终文本校正），且提示词加载路径散落在 `agent/graph/agent_node.py`、`.env` 解析在 `facade` 与 `client/voice/tts.py` 各写一份 | ① `utils/time_utils.py` 新增 `strip_time_markers()`，清除任意位置的方括号时间；`finalize_reply` 先清再追加后缀，`_build_result` 统一输出干净 reply；`text.done` 时用最终文本覆盖流式展示。② 提示词统一走 `utils/prompt_loader.py`：新增 `load_prompt_by_config(key)` / `load_graph_prompt()`，路径由 `config/prompts_config.yml` 的 `graph_system_prompt_path` 提供，删除 `agent_node` 里的本地实现。③ `.env` 解析上移到 `utils/env_utils.py`，`core/facade` 与 `client/voice/tts` 复用 | 时间戳不再出现在回复/历史正文（仅保留系统后缀）；提示词与 env 加载只有一处实现。新增 14 条用例，全量 357 passed |
| FIX-3 | 前端窗口与 Live2D 先显示、后端仍在启动，用户快速输入时会长时间等待 | `client/main.py` 改为“先启后端、再显示窗口”：新增 `wait_for_backend()`，用 `QEventLoop` 等待 `ServerLauncher.ready/failed`（上限 `READY_TIMEOUT + 5s`），就绪后才创建并 `show()` 主窗口；失败时仍显示窗口并展示错误，同时回收 launcher | 冷启动期间用户无法提前对话；等待时长仅发生在窗口出现前。GUI 启动路径无自动化测试，随手工验收 |
| FIX-4 | 配置 MCP 后仍无法调用工具：适配器返回的工具只支持 `ainvoke`，主图同步执行时 ToolNode 走 `invoke`，结果变成 `NotImplementedError('StructuredTool does not support sync invocation.')` 的 ToolMessage | ① `tooling._to_sync_tool()` 把 async-only 工具包装成同步 `StructuredTool`（内部 `_run_coro` 独立线程 `asyncio.run(tool.ainvoke)`，超时 30s）；② MCP 配置读取改用 `utf-8-sig`，兼容 PowerShell/记事本 BOM；③ 示例配置的 HTTP 传输改为合法的 `streamable_http`。用本地最小 stdio MCP 服务（`add` 工具）跑通完整主图：ToolMessage 返回 `5` | MCP 工具可被同步主图调用；新增 2 条用例，全量 359 passed |

---

## Commit 记录

| 阶段 | commit message | 备注 |
| --- | --- | --- |
| P0 | `chore(deps): 安装 LangGraph 路由与 MCP 适配依赖` | 已执行 |
| P1 | `feat(graph): 搭建情感陪伴主图骨架与感知门控` | 已执行（5671867） |
| P2 | `refactor(utils): 将时间能力从工具层迁移至 utils` | 已执行（1c16fba，P2-A） |
| P2 | `feat(graph): 接入 ReAct 工具循环` | 已执行（b0e525f，P2-B） |
| P3 | `feat(graph): 实现时间注入与流式回复` | 已执行（99c4fe6） |
| P4 | `feat(graph): 接入检查点与多轮上下文` | 已执行（06a9b4b） |
| P5 | `feat(game): 新增游戏占位子图与 FakeJev 路由` | 已执行（f0db20b） |
| P6 | `feat(server): 切换 LangGraph 陪伴引擎并支持流式 SSE` | 已执行（be8b23e） |
| P7 | `feat(mcp): 接入可选 MCP 工具并支持降级` | 已执行（37c2e45） |
| P8 | `test: 补充图编排与时间注入单元测试` / `docs: 更新陪伴主图技术文档` | 已执行 |
| FIX-1 | `fix(graph): 修复重启后恢复工具消息导致的非法请求` | 已执行 |
| FIX-2 | `fix(graph): 修复时间戳泄漏并统一提示词与 env 加载` | 已执行 |
| FIX-3 | `feat(client): 后端就绪后再显示主窗口` | 已执行 |
| FIX-4 | `fix(mcp): 支持同步主图调用 MCP 工具` | 已执行 |

---

## 验收结果（开发完成后填写）

| # | 验收项 | 结果 | 证据 |
| --- | --- | --- | --- |
| 1 | 多轮连续 + 流式 | 自动化通过，UI 待手工 | `test_graph_flow.py` 多轮/流式；`test_server_api.py` 逐 token |
| 2 | 时间问题不调工具且答对 | 工具侧通过，答对需手工 | `ALL_TOOLS` / `agent_tools` 无 `get_current_time` |
| 3 | 工具调用人格化 | 循环自动化通过，人格化待手工 | `test_graph_flow.py` 工具循环 |
| 4 | 工具失败不崩 | 通过 | `handle_tool_errors=True` 异常工具用例 |
| 5 | 游戏意图进子图 | 通过 | `test_graph_perception.py` / `test_graph_flow.py` |
| 6 | messages 带时间、UI 干净 | 自动化通过，UI 待手工 | 时间前后缀与 `strip_reply_time` 用例 |
| 7 | `ALL_TOOLS` / `agent_tools` 无时间工具 | 通过 | `test_tool_manager.py` / `test_graph_tooling.py` |
| 8 | MCP 可选降级 | 通过 | `test_graph_tooling.py` 未配置/坏配置/合并 |
