# LangGraph 情感陪伴主图执行文档

> 版本：v2（决策已确认，待开发）
> 日期：2026-11-21
> 状态：**仅调研与计划，未改动任何业务代码，未提交 git**
> 变更：v2 确认 D1–D5 推荐方案；新增 D6「时间相关函数迁至 `utils/`」并同步调整工具管理、时间注入与 P2 阶段计划。
> 对应需求：`langgrapph状态图提示词.md`
> 对应架构：`hadali新架构设计.txt`
> 配套记录：`langgraph状态图开发记录.md`

---

## 0. 结论摘要

本次改造在现有前后端分离项目上，增量引入一套 **LangGraph 情感陪伴主图**，替代当前 `agent/chat_agent.py` 的手写工具循环，作为陪伴对话的主执行引擎：

```text
START → perception_gate
perception_gate ──(FakeJev 游戏置信度 > 0.7)──> game_subgraph → END
perception_gate ──(其他)──> agent
agent ──(有 tool_calls)──> tools → agent
agent ──(无 tool_calls)──> END
```

核心取舍：

1. **陪伴是主体，办公不再是模式**：保留 `agent/mode_configs/` 作为兼容层，但新引擎只走单模式；原桌面办公能力后续以 `agent_tool` 分组按需挂载，不再做模式路由。
2. **不重建项目**：新增 `agent/graph/` 包，复用现有模型工厂、工具、日志、路径、情绪校验与 `TurnResult` 契约；`ChatAgent` 与 260 条既有测试保持可用。
3. **游戏子图是真子图**：`game_subgraph` 用独立 `StateGraph` 实现，当前只有 `game_notice` 一个占位节点，后续可原地替换为真实五子棋。
4. **时间能力集中到 utils**：时间相关函数迁至 `utils/time_utils.py` 纯函数，删除 `tools/common/get_time.py`，从 `ALL_TOOLS` 与模式白名单移除；用户消息加 `[YYYY-MM-DD HH:MM]` 前缀，AI 消息加同格式后缀，UI/SSE 只拿干净文本。
5. **流式与时间戳解耦**：时间后缀由节点在 LLM 生成完成后追加，因此 `stream_mode="messages"` 的原始 token 天然不含时间戳；只需过滤开头的情绪标签。

---

## 0.1 需求与项目现状的对齐结论

用户已明确调整项目方向：从「多模式 agent 助手」改为「情感陪伴为主体 + 工具按需加载 + 游戏互动子图」。提示词中的 `perception_gate`、`game_subgraph`、`agent_tools` 均按新方向理解，不再保留办公/编程模式路由。

| 维度 | 项目现状 | 新方向 / 提示词要求 | 本次处理 |
| --- | --- | --- | --- |
| 产品定位 | README 仍写「陪伴 + 桌面办公/编程多模式」 | 陪伴主体，办公降级为工具 | 新引擎单模式；文档同步修订，旧模式 API 暂保留兼容 |
| 顶层编排 | `agent/chat_agent.py` 手写 `bind_tools` 循环 | LangGraph 主图 + 游戏子图 | 新增 `agent/graph/`，由 `AGENT_ENGINE` 切换引擎 |
| 意图路由 | 无产品级路由；根目录 `root_graph.py` 是未接入原型的 Supervisor | `perception_gate` 用 FakeJev，>0.7 进游戏 | 新增感知门控；`root_graph.py` 仅作参考，不直接接入 |
| 工具 | 时间 / 天气 / 搜索，全部对 LLM 暴露 | 时间不再作为工具；MCP 可选；办公工具按需加载 | 时间能力迁至 `utils/time_utils.py` 并从工具层删除；`agent_tools` 只含天气/搜索/MCP |
| 记忆 | `chat_history/<session>.json` + 30 条滑动窗口 | checkpointer 保证同 `thread_id` 多轮连续 | `MemorySaver` + JSON 镜像，避免重启记忆回退 |
| 输出格式 | 严格 JSON `{"emotion","reply"}` | 人格化回复 + 时间后缀 + 流式干净 UI | 图引擎改为「情绪标签前缀 + 纯文本正文」，旧引擎 JSON 不动 |
| 流式 | server 一次性 `text.delta`，client 打字机 | `stream_mode="messages"` token 流 | server 透传 token；client 增量显示；保留一次性降级 |
| 时间感知 | LLM 调 `get_current_time` | 时间注入，不调工具 | 用户前缀 / AI 后缀；时间函数迁至 `utils/time_utils.py` |
| MCP | 未接入，`mcp` 依赖未安装 | 可选接入，失败只告警 | 新增适配层与配置读取，未配置返回空列表 |

---

## 0.2 已确认决策（2026-11-21 全部采用推荐方案）

| 编号 | 决策点 | 推荐方案 | 备选方案 |
| --- | --- | --- | --- |
| D1 | 新引擎如何接入现有 server/client | 新增 `CompanionGraphAgent`，`core/facade` 按 `.env` 的 `AGENT_ENGINE` 选择，默认 `graph`；`legacy` 可一键回滚 | 直接改写 `ChatAgent`（风险高，260 条测试需大改） |
| D2 | 情绪输出契约 | 图引擎用 `[emotion:happy]` 前缀 + 纯文本正文；旧引擎继续 JSON | 继续 JSON；代价是 token 流里会带 JSON 结构，UI 需复杂过滤 |
| D3 | 流式链路 | server 用 `text.delta` 多次下发 token，client 增量显示；无流式能力时自动退回一次性下发 | 仅 CLI 演示流式，server/UI 保持一次性 + 打字机 |
| D4 | FakeJev 依赖 | 安装 `langgraph-jev-router==0.2.0`；若实际 API 与 `root_graph.py` 不一致，写 `game_router` 适配层，失败回落本地关键词规则 | 不装依赖，纯本地关键词规则（偏离“采用 fake_jev”要求） |
| D5 | MCP 依赖 | 新增 `langchain-mcp-adapters` + `mcp`；配置缺失/启动失败只告警并返回空列表 | 本期不接 MCP，仅留接口（不满足验收 8） |
| D6 | 时间能力代码归属 | 迁至 `utils/time_utils.py` 纯函数；删除 `tools/common/get_time.py`，从 `ALL_TOOLS` 与模式白名单移除；图引擎直接 import | 保留在 `tools/common` 再过滤（用户明确认为是死代码，不采用） |

> 用户已确认：D1–D5 全部采用推荐方案；D6 为本轮新增确认项，按“推荐方案”执行。
> 时间能力迁移的连带影响：`AGENT_ENGINE=legacy` 回滚路径也不再具备时间工具；legacy 仅用于结构回滚，如需连时间行为一起回退，需回退 P2 的 `refactor(utils)` commit。

---

## 1. 项目现状

### 1.1 进程与分层

```text
client（PySide6 + Live2D + TTS）
        │  HTTP + SSE（127.0.0.1:8765）
        ▼
server（FastAPI + uvicorn，无 GUI）
        │  同步调用（asyncio.to_thread）
        ▼
core（facade / session / tracing）
        │
agent（chat_agent / tool_manager / mode_configs）
modelFactory / tools / utils / protocol
```

- `main.py` 是 `client/main.py` 的 shim；真实入口在 `client/`。
- server 按 `session_id` 隔离会话，每会话一个 `ChatAgent` + 一把异步锁。
- 对话历史落盘到 `chat_history/<session_id>.json`（`default` 复用 `default.json`）。

### 1.2 对话链路（现状）

```text
用户输入
  → POST /v1/chat（SSE）
  → Services.chat → SessionManager.get_agent → ChatAgent.chat
  → 手写 bind_tools 循环（最多 6 轮）
  → parse_reply_json 解析 {"emotion","reply"}
  → SSE: turn.start / state / text.delta（整段）/ emotion / tool.* / turn.end
  → client：打字机显示、Live2D 表情、TTS 播报
```

关键事实：

- `text.delta` 当前只发一次完整回复；`window.py` 收到后调用 `ChatBox.finalize_ai_reply` 做客户端打字机。
- UI 不显示用户输入原文，提交后直接进入“思考中”，因此时间前缀天然不会出现在 UI。
- 情绪标签由 `agent/expression_driver.py` 校验，`client/emotion_map.py` 映射为 Live2D 动作。

### 1.3 工具与模式

- 全量工具：`tools/common/get_time.py`、`weather.py`、`web_search.py`，注册在 `agent/tool_manager.py` 的 `ALL_TOOLS`。
- 模式注册：`agent/mode_configs/` 目前有 `emotion`（默认）与 `office`（空工具 stub）。
- `emotion` 模式白名单包含 `get_current_time`，LLM 会主动调用时间工具。
- 项目内 **没有 MCP 接入代码**，也没有 `mcp` / `langchain-mcp-adapters` 依赖。

> 目标状态：时间能力迁至 `utils/time_utils.py`，`tools/common/get_time.py` 删除，`ALL_TOOLS` 与模式白名单同步移除；详见 2.5 / 2.6。

### 1.4 环境基线（本机实测）

| 项 | 现状 |
| --- | --- |
| Python | 3.13 |
| `langgraph` | 1.2.11 |
| `langgraph-prebuilt` | 1.1.0 |
| `langgraph-checkpoint` | 4.2.0 |
| `langchain-core` | 1.6.1 |
| `ToolNode` / `tools_condition` | 已确认可从 `langgraph.prebuilt` 导入 |
| `MemorySaver` | 已确认可从 `langgraph.checkpoint.memory` 导入 |
| `langgraph-jev-router` | **未安装**；PyPI 存在 0.2.0，但 `root_graph.py` 使用的低层 API 需安装后核验 |
| `mcp` / `langchain-mcp-adapters` | **未安装** |
| 测试基线 | `.venv\Scripts\python.exe -m pytest -q` → **260 passed** |
| 工作区 | `root_graph.py`、`hadali新架构设计.txt`、`langgrapph状态图提示词.md` 未跟踪 |

### 1.5 `root_graph.py` 原型的问题

- 依赖 `langgraph_jev_router.backends.FakeJev`、`settings`、`types.ChoiceRequest`，当前环境导入即失败。
- 拓扑仍是旧的 `companion / office` 双模式，与新方向不一致。
- 没有工具、时间注入、checkpointer、游戏子图。

结论：**只把它当作 FakeJev 用法参考**，不直接改造为产品主图；新主图放在 `agent/graph/`。

---

## 2. 目标设计

### 2.1 阶段范围

做：

1. LangGraph 情感陪伴主图 + ReAct 工具循环 + 流式输出。
2. `perception_gate` 用 FakeJev 做游戏意图门控（阈值 0.7）。
3. 游戏占位子图（真 `StateGraph`，单节点）。
4. `MemorySaver` 多轮上下文。
5. 时间注入（用户前缀 / AI 后缀 / UI 干净）。
6. 工具管理：时间能力迁出工具层、MCP 可选、办公工具分组预留。
7. 接入现有 server/client，保持 `TurnResult` 与会话隔离。

不做：

- 主动看屏幕 / 主动搭话
- UI 进度事件 / 自定义 progress 流
- `interrupt` / HITL / 任务审批
- 长期记忆 Store / 事实提取 / 向量库
- 真实游戏逻辑、棋盘、胜负判定
- 多模式路由（办公/编程不再作为独立模式）
- LangSmith 接入（只留环境变量占位）
- 重写 `ChatAgent`、删除既有模式配置

### 2.2 State 定义

新增 `agent/graph/state.py`：

```python
class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    route: str                      # "chat" | "game"
    game_request: str | None        # 游戏占位子图使用
    # 预留但不实现逻辑
    emotion_state: str | None
    task_brief: str | None
```

- 必须使用 `add_messages` reducer（已确认 `langgraph.graph.message.add_messages` 可用）。
- `emotion_state` / `task_brief` 只占位，不写业务逻辑。
- 游戏子图复用同一 State 结构，父子图共享主图 checkpointer。

### 2.3 主图拓扑

```text
START → perception_gate
perception_gate ──(route == "game")──> game_subgraph → END
perception_gate ──(其他)──> agent
agent ──(有 tool_calls)──> tools → agent
agent ──(无 tool_calls)──> END
```

- 条件边：`route_after_perception`、`should_continue`。
- `tools` 使用 `ToolNode(agent_tools, handle_tool_errors=True)`，异常转 `ToolMessage`，不中断图。
- 编译：`builder.compile(checkpointer=MemorySaver())`；`thread_id = session_id`。

### 2.4 节点职责

**perception_gate**（`agent/graph/perception.py`）

- 输入：最后一条用户消息（去掉时间前缀后再判断，避免时间数字干扰）。
- 判断：FakeJev 规则后端，只区分 `game` / `chat`。
- `game` 置信度 **> 0.7** → `route="game"`，`game_request=原文`；否则 `route="chat"`，`game_request=None`。
- 只返回路由字段，**不写 messages、不调工具、不写记忆**。
- FakeJev 导入失败 / 调用异常 → 记录 warning，回落本地关键词规则，程序不崩。

游戏意图关键词（初版，可调）：`玩游戏`、`玩一局`、`来一局`、`来一盘`、`下一盘`、`下棋`、`五子棋`、`象棋`、`围棋`、`棋`、`game`。

**agent**（`agent/graph/agent_node.py`）

- system prompt 从 `prompts/graph_companion_prompt.txt` 加载，人格延续哈达莉设定。
- 每轮按用户文本选择工具（`select_tools_for()`），`llm.bind_tools(tools).invoke(messages)`。
- 有 `tool_calls` → 原样返回 `AIMessage`（不手动执行工具）。
- 无 `tool_calls` → 解析并剥离开头情绪标签，得到 `ai_reply`；追加 ` [YYYY-MM-DD HH:MM]` 后作为最终 `AIMessage.content`；情绪写入 `AIMessage.additional_kwargs["emotion"]`。
- 时间后缀只加一次；工具轮次不加。

**tools**

- `ToolNode`，工具列表 = 当前 `agent_tools`（时间能力已迁出 + 可选 MCP）。
- 工具异常由 ToolNode 转 `ToolMessage`；提示词要求模型用陪伴语气解释，不抛技术错误。

**game_subgraph**（`agent/graph/game_subgraph.py`）

- 真正的 `StateGraph`：`START → game_notice → END`。
- `game_notice`：LLM 基于 `game_request` 与最近对话，生成一句“游戏还在开发中”的陪伴式回应；同样追加时间后缀。
- 子图结束直接回主图 `END`；本阶段不做“游戏结束回主图继续”。
- 共享主图 checkpointer，不另建命名空间。

### 2.5 工具管理（含时间能力迁出）

**时间能力迁移（P2 先做）**

- 新增 `utils/time_utils.py`，只放纯函数，不依赖 LangChain，不作为 `@tool`。
- 删除 `tools/common/get_time.py`。
- `agent/tool_manager.py` 的 `ALL_TOOLS` 移除 `get_current_time`，只保留 `get_weather` / `web_search`。
- `agent/mode_configs/emotion_mode.py` 的 `allowed_tools` 移除 `get_current_time`。
- `prompts/system_prompt.txt`（legacy 提示词）删除时间工具说明；图引擎使用新的 `prompts/graph_companion_prompt.txt`。
- 同步更新 `tests/test_get_time.py`（改为 `tests/test_time_utils.py`）、`tests/test_tool_manager.py`、`tests/test_mode_configs.py`、`tests/README.md`。

新增 `agent/graph/tooling.py`：

1. `BASE_TOOL_NAMES = ["get_weather", "web_search"]`（从 `ToolManager` 注册表取对象，时间能力已不在注册表）。
2. **防御性校验**：构造 `agent_tools` 后检查名称，若出现 `get_current_time` 则告警并剔除，防止后续误注册；同时打印 `agent_tools` 名称供验收 7 确认。
3. `MCP` 工具：从 `config/mcp_servers.json`（路径可用 `MCP_CONFIG_PATH` 覆盖）读取；未配置、导入失败、连接超时、工具为空都只打 warning 并返回 `[]`。
4. 工具分组（为“办公按需加载”留口）：
   - `general`：天气、搜索、MCP（默认挂载）
   - `office`：预留空列表，后续放文件读写/表格等轻量工具
   - `select_tools_for(text)`：命中办公关键词时追加 `office` 组；本阶段 office 为空，行为等价于 general
5. 所有工具对象来自现有 `ToolManager`，**不改已有工具实现**（仅改注册表与白名单）。

### 2.6 时间注入

时间相关纯函数统一放在 `utils/time_utils.py`，`agent/graph` 不再新增 `time_inject.py`：

- `now_str(dt=None, fmt="%Y-%m-%d %H:%M")`：返回格式化时间；`dt` 可注入，便于测试。
- `with_user_time(text, dt=None, fmt=...)` → `f"[{now}] {text}"`。
- `with_reply_time(reply, dt=None, fmt=...)` → `f"{reply} [{now}]"`。
- `strip_reply_time(text)`：正则去掉尾部 ` [YYYY-MM-DD HH:MM]`，供 UI 兜底。
- `GRAPH_TIME_FORMAT` 由 runner 读取后作为 `fmt` 传入；utils 不直接读环境变量，保持纯函数与可测性。

写入规则：

| 位置 | 是否带时间 | 说明 |
| --- | --- | --- |
| `state.messages` 的 HumanMessage | 前缀 | `[2026-11-21 14:30] 用户原话` |
| `state.messages` 的 AIMessage | 后缀 | `回复正文 [2026-11-21 14:31]` |
| LLM 原始 token 流 | 不含 | 后缀在节点内生成完成后才追加 |
| SSE `text.delta` / `turn.end.reply` | 不含 | runner 返回干净 `reply` |
| UI 显示 | 不含 | UI 不显示用户原文；AI 回复使用干净文本 |

提示词中明确：

- 用户消息开头的 `[时间]` 是系统注入的当前时间，回答“现在几点/今天几号”直接使用它，**不要调用时间工具**。
- AI 自己历史回复末尾的时间戳也是系统加的，不要模仿输出时间戳。

### 2.7 输出与情绪契约（对应 D2）

图引擎不再要求 JSON，改为：

```text
[emotion:happy]
今天也想陪用户聊聊天呀。
```

- 解析正则：`^\s*\[emotion\s*[:=]\s*([A-Za-z_]+)\s*\]\s*`。
- 合法情绪沿用 `agent/expression_driver.py` 的 10 个标签；非法/缺失回退 `neutral`，正文保留。
- 最终 `AIMessage.content` = 纯正文 + 时间后缀；情绪存入 `additional_kwargs`。
- 流式过滤：runner 内做一个小型状态机，缓冲并剥离开头的情绪标签；标签跨 token 也能处理。
- 旧 `ChatAgent` 的 JSON 契约完全不动，`parse_reply_json` 与相关测试不受影响。

### 2.8 记忆与 checkpointer

- 图编译时挂 `MemorySaver`，`thread_id = session_id`。
- 首次访问某 `thread_id` 时，从现有 `HistoryStore`（`chat_history/<session>.json`）加载历史消息作为初始 `messages`，保证升级后老对话不丢。
- 每轮结束把图中 `messages` 镜像回 `HistoryStore` 并保存；写入前做去重（按消息 id）与滑动窗口裁剪。
- 重启后 MemorySaver 为空，但 JSON 镜像会重新注入，维持“关闭程序后仍记得”的既有体验。
- 游戏子图共享同一 checkpointer，不单独命名空间。

### 2.9 与现有 server/client 的接口

新增 `agent/graph/runner.py` 的 `CompanionGraphAgent`，对 server 暴露与 `ChatAgent` 相同的最小接口：

```python
class CompanionGraphAgent:
    mode_config = {"name": "emotion", "display_name": "情感陪伴"}

    def chat(self, user_input: str) -> TurnResult: ...
    def set_mode(self, mode_name: str) -> None: ...      # 单模式，记录日志后忽略
    def stream_chat(self, user_input: str): ...          # 可选：逐 token 产出
```

- `TurnResult` 字段保持：`emotion / reply / mode / steps / tool_calls / latency_ms`。
- `core/facade` 读取 `AGENT_ENGINE`：
  - `graph`（默认）：构造 `CompanionGraphAgent`
  - `legacy`：构造原 `ChatAgent`
- `SessionManager` 不改，仍按 `session_id` 持有 agent 与锁。
- `server/routes/chat.py`：
  - `Services` 若有 `stream_chat`，用 `asyncio.to_thread` + 队列桥接逐 token 发 `text.delta`；
  - 无流式能力或异常时退回当前“一次性 `text.delta` + `text.done`”路径。
- `client/ui/chat_box.py` + `window.py`：
  - 新增 `begin_ai_reply()` / `append_ai_reply(text)` / `mark_reply_done()`；
  - 首个 `text.delta` 开始回复，后续增量追加，`text.done` 收尾；
  - 若后端仍一次性下发，行为与现在等价。

### 2.10 新增目录结构

```text
utils/
  time_utils.py       # 时间格式化、消息前后缀、后缀剥离（纯函数，无 LangChain 依赖）
agent/graph/
  __init__.py
  state.py            # AgentState
  emotion.py          # 情绪标签解析与流式过滤器
  perception.py       # FakeJev 游戏路由 + fallback 规则 + 门控节点
  tooling.py          # agent_tools、MCP、工具分组（时间能力已迁出）
  agent_node.py       # ReAct agent 节点
  game_subgraph.py    # 游戏占位子图
  main_graph.py       # 主图构建与编译
  runner.py           # CompanionGraphAgent（TurnResult / 流式）
  demo.py             # CLI 多轮演示（stream_mode="messages"）
prompts/
  graph_companion_prompt.txt
  graph_game_notice_prompt.txt
tests/
  test_time_utils.py          # 替代原 test_get_time.py
  test_graph_state.py
  test_graph_emotion.py
  test_graph_perception.py
  test_graph_tooling.py
  test_graph_flow.py
  test_graph_game_subgraph.py
  test_graph_runner.py
删除：
  tools/common/get_time.py    # 时间能力迁至 utils，不再作为 agent 工具
```

> `agent/graph/time_inject.py` 不再新增；时间前缀/后缀/剥离统一由 `utils/time_utils.py` 提供。

---

## 3. 分阶段开发计划

> 规则：每个阶段完成后在本文件打勾、写阶段总结；`pytest -q` 全绿后 git commit。
> 基线：260 passed；任何阶段不得让既有用例回退。

### P0 依赖与 API 核验

- [x] 安装并锁定依赖：`langgraph-jev-router==0.2.0`、`langchain-mcp-adapters`、`mcp`
- [x] 核验 FakeJev 实际 API（`backends.FakeJev` / `ChoiceRequest` / `settings.configure` 是否与 `root_graph.py` 一致）
- [x] 核验 MCP 适配器导入路径与 `get_tools()` 调用方式
- [x] `pyproject.toml` 记录依赖；`.env` 只补文档说明，不写入真实密钥
- [x] `pytest -q` 保持 260 passed
- [x] 记录版本假设到开发记录
- [x] commit：`chore(deps): 安装 LangGraph 路由与 MCP 适配依赖`

阶段总结（2026-11-21）：已通过 `uv add` 安装 `langgraph-jev-router==0.2.0`、`langchain-mcp-adapters==0.3.2`、`mcp==1.30.0`（附带 jsonschema / pyjwt / pywin32 等 12 个传递依赖），`pyproject.toml` 与 `uv.lock` 已同步。核验结论：`FakeJev(rules=...)` / `ChoiceRequest(question, options, state, model)` / `settings.configure(backend=...)` 与 `root_graph.py` 用法一致，无需写适配层；`langchain_mcp_adapters.client.MultiServerMCPClient` 支持 `connections=None` 构造，`get_tools()` 为同步方法并返回 `list[BaseTool]`。重要发现：FakeJev 关键词规则单命中置信度为 `0.70 + jitter(0~0.05)`，恰好 0.70 时不满足 `>0.7`，因此游戏规则需保证至少 2 个关键词命中才能稳定进入游戏子图（已记入开发记录，P1/P5 按此设计）。全量测试 260 passed。

### P1 主图骨架 + perception_gate（先只走 chat）

- [x] 新增 `agent/graph/state.py`、`main_graph.py`
- [x] 新增 `perception.py`：FakeJev 优先、关键词 fallback；仅返回 `route/game_request`
- [x] 新增占位 `agent` 节点：直接调用 LLM 生成纯文本回复（暂不绑工具）
- [x] 新增 `runner.py` 的最小 `chat()`，返回 `TurnResult`
- [x] 新增 `demo.py`，跑通“聊天 → 结束”
- [x] 单元测试：state reducer、perception 阈值/降级、chat 分支
- [x] `pytest -q` 全绿；commit：`feat(graph): 搭建情感陪伴主图骨架与感知门控`

阶段总结（2026-11-21）：新增 `agent/graph/` 包（`__init__` / `state` / `perception` / `agent_node` / `main_graph` / `runner` / `demo`）与 `prompts/graph_companion_prompt.txt`。主图最小拓扑为 `START → perception_gate → agent → END`，`game` 路由在 P1 暂由 agent 回复。感知门控使用 FakeJev 规则后端，阈值严格 `>0.7`；关键调整：**chat 不配置关键词**，避免普通词稀释游戏置信度（实测「陪我下盘棋」在 chat 含「陪我」时仅 0.56），同时游戏关键词保留包含关系（五子棋/棋、下盘/棋）保证常见说法至少 2 命中。系统提示词每轮临时拼入、不写入 state。runner 已返回完整 `TurnResult`（emotion 暂固定 neutral）。新增 20 条测试，全量 280 passed。

### P2 时间能力迁移 + ReAct 工具循环

**P2-A 时间能力迁移（先做，独立 commit）**

- [x] 新增 `utils/time_utils.py`：`now_str` / `with_user_time` / `with_reply_time` / `strip_reply_time`，支持注入 `dt` 与 `fmt`
- [x] 删除 `tools/common/get_time.py`
- [x] `agent/tool_manager.py` 移除 `get_current_time` 注册，`ALL_TOOLS` 只剩天气/搜索
- [x] `agent/mode_configs/emotion_mode.py` 白名单移除 `get_current_time`
- [x] `prompts/system_prompt.txt` 删除时间工具说明
- [x] 更新测试：`tests/test_get_time.py` → `tests/test_time_utils.py`；同步 `test_tool_manager.py`、`test_mode_configs.py`、`tests/README.md`
- [x] 验证：`ALL_TOOLS` 无 `get_current_time`；legacy 路径不再具备时间工具（已知回滚差异）
- [x] commit：`refactor(utils): 将时间能力从工具层迁移至 utils`

P2-A 阶段总结（2026-11-21）：新增 `utils/time_utils.py`（`now_str` / `strip_user_time` / `strip_reply_time` / `with_user_time` / `with_reply_time`，均支持注入 `dt` 与 `fmt`，前后缀写入幂等），删除 `tools/common/get_time.py` 与 `tests/test_get_time.py`；`ALL_TOOLS` 只剩天气/搜索，`emotion` 白名单与 legacy 提示词同步移除时间工具；`perception` 的时间前缀剥离改为复用 `strip_user_time`。legacy 工具循环测试原本借用时间工具作为“本地无网络工具”，改用 `_fake_echo` + `ToolManager` 桩，保持离线。全量 285 passed。

**P2-B ReAct 工具循环**

- [x] `tooling.py`：`agent_tools` = 天气 + 搜索 + MCP，从注册表构造，天然不含时间工具
- [x] 防御性校验：`agent_tools` 名称中出现 `get_current_time` 时告警并剔除
- [x] `agent_node.py`：`bind_tools` + 有/无 `tool_calls` 分支
- [x] `main_graph.py`：`tools` 节点用 `ToolNode(..., handle_tool_errors=True)` + 条件边
- [x] 系统提示词加入工具使用原则与“工具失败用陪伴语气解释”
- [x] 测试：正常工具调用、工具异常回传、`ALL_TOOLS` / `agent_tools` 均无时间工具
- [x] 日志打印 `agent_tools` 名称，供验收 7 断点确认
- [x] `pytest -q` 全绿；commit：`feat(graph): 接入 ReAct 工具循环`

阶段总结（P2-B，2026-11-21）：新增 `agent/graph/tooling.py`（`get_agent_tools` 惰性构建天气/搜索工具并缓存、`_sanitize_tools` 防御性剔除时间工具、`select_tools_for` 预留 office 分组）；`agent_node` 改为 `bind_tools` 后调用，工具选择按本轮用户文本；主图新增 `tools` 节点（`ToolNode(..., handle_tool_errors=True)`）与 `tools_condition` 条件边，形成 `agent ⇄ tools` 循环；提示词加入工具使用原则与失败时的陪伴式解释。工具异常会转成 `ToolMessage`，图不中断。runner 现在统计本轮模型轮数与工具调用记录（`ok` 依据 ToolMessage 状态）。新增 `tests/test_graph_tooling.py` 与工具循环/异常用例，全量 295 passed。

### P3 时间注入 + 流式输出

- [x] 接入 `utils/time_utils.py`：user 前缀、AI 后缀、UI 剥离兜底
- [x] `emotion.py`：标签解析、校验、流式过滤器
- [x] `agent` 节点：剥离标签 → 追加时间后缀 → 写 `additional_kwargs`
- [x] `runner.stream_chat()`：`graph.stream(..., stream_mode="messages")`，过滤标签后逐 token 产出
- [x] `demo.py` 改为流式打印；验证 UI 侧无时间戳
- [x] 测试：时间格式、前后缀、标签跨 token、无标签回退、流式干净
- [x] `pytest -q` 全绿；commit：`feat(graph): 实现时间注入与流式回复`

阶段总结（P3，2026-11-21）：新增 `agent/graph/emotion.py`（`parse_emotion_tag` 复用 `expression_driver` 的标签集合、`EmotionStreamFilter` 处理跨 token 标签并吞掉标签后的换行）。`AgentNode` 改为优先 `llm.stream` 聚合并回落 `invoke`——否则真实 ChatOpenAI 的 `invoke` 不会产生 token 回调，LangGraph `stream_mode="messages"` 只能收到整段；无工具调用的最终消息会剥离标签、追加 ` [YYYY-MM-DD HH:MM]`，情绪写入 `additional_kwargs["emotion"]`，工具轮次不加时间。runner 对用户消息加 `[时间] ` 前缀，`chat()/stream_chat()` 的 `reply` 统一 `strip_reply_time`，`stream_chat()` 通过 `stream_mode=["messages","values"]` 产出 `("delta", 文本)` / `("done", TurnResult)`，只转发 `langgraph_node=="agent"` 的 token。`demo.py` 改为流式打印。新增 `tests/test_graph_emotion.py` 与流式/时间注入用例，全量 311 passed。

### P4 checkpointer + 多轮上下文

- [x] `main_graph` 编译挂 `MemorySaver`
- [x] `runner` 用 `thread_id=session_id`；首次从 `HistoryStore` 注入历史
- [x] 每轮镜像回 `HistoryStore`，去重 + 裁剪
- [x] 验证：同会话多轮上下文连续；`state.messages` 中 Human 带前缀、AI 带后缀
- [x] 验证：重启后从 JSON 恢复
- [x] 测试：多轮、跨重启、时间戳持久化
- [x] `pytest -q` 全绿；commit：`feat(graph): 接入检查点与多轮上下文`

阶段总结（P4，2026-11-21）：`build_main_graph` 默认 `compile(checkpointer=MemorySaver())`；runner 所有 `invoke/stream` 都带 `{"configurable": {"thread_id": session_id}}`，不再手动拼接完整历史。首次使用某 thread 时从 `HistoryStore.messages`（过滤 SystemMessage）注入 prior 消息，之后由 checkpoint 维持上下文；每轮结束把完整状态镜像回 JSON（新增 `HistoryStore.replace`，裁剪 30 条非 system 消息）。`self.messages` 保持全量以正确切分本轮新增消息，裁剪只作用于 JSON 副本。新增跨实例恢复与时间戳持久化测试；直接调用编译图的测试统一补 `thread_id`。全量 314 passed。

### P5 游戏子图 + FakeJev 路由

- [x] `game_subgraph.py`：`START → game_notice → END`
- [x] `game_notice` 提示词：一句“游戏开发中”的陪伴式回应
- [x] `main_graph`：`route == "game"` 条件边进入子图，结束回 `END`
- [x] FakeJev 阈值 0.7；低于阈值/非游戏 → `agent`
- [x] 测试：“来下盘五子棋”进子图、普通聊天不进、子图输出带情绪与时间后缀
- [x] `pytest -q` 全绿；commit：`feat(game): 新增游戏占位子图与 FakeJev 路由`

阶段总结（P5，2026-11-21）：新增 `agent/graph/game_subgraph.py`，`build_game_subgraph` 编译出真正的 `START → game_notice → END` 子图（不单独挂 checkpointer，由主图共享），`GameNoticeNode` 复用 `invoke_llm / finalize_reply`，回复带情绪标签解析与时间后缀。主图条件边改为 `{"chat": "agent", "game": "game_subgraph"}`，子图结束直接 `END`。修复提示词与 `expression_driver.VALID_EMOTIONS` 不一致的问题（原写 calm/confused 均为非法标签，统一为 10 个合法标签）。实测子图内的 `messages` 流事件挂在父节点 `game_subgraph` 且只包含带时间后缀的最终消息，本期不转发子图 token，由 `done.reply` 一次性下发（demo 已加降级打印）。全量 316 passed。

### P6 接入现有 server/client（流式 SSE）

- [x] `core/facade` 按 `AGENT_ENGINE` 选择引擎，默认 `graph`，保留 `legacy`
- [x] `CompanionGraphAgent` 补齐 `set_mode` 兼容与 `TurnResult`
- [x] `server/services.py` 增加 `stream_chat` 桥接；`routes/chat.py` 逐 token 发 `text.delta`
- [x] 无流式/异常时退回一次性 `text.delta`
- [x] `client` ChatBox 支持增量追加；`text.done` 收尾
- [ ] 验证：UI 多轮连续、表情正常、TTS 正常、无时间戳泄漏（待 P8 手工验收）
- [x] 测试：server SSE token 顺序、一次性降级、client 不在自动化范围（手工验收）
- [x] `pytest -q` 全绿；commit：`feat(server): 切换 LangGraph 陪伴引擎并支持流式 SSE`

阶段总结（P6，2026-11-21）：`core/facade.py` 新增 `DEFAULT_ENGINE="graph"` / `VALID_ENGINES` / `resolve_engine()`（显式参数 > `AGENT_ENGINE` > 默认），`create_agent*` 按引擎返回 `CompanionGraphAgent` 或 `ChatAgent`，`CompanionGraphAgent.set_mode` 仅记录日志以兼容 server 的模式切换调用。`services.py` 新增 `_resolve_agent` 与 `stream_chat`（legacy 无该方法时返回 `None`）；`routes/chat.py` 用工作线程 + `asyncio.Queue` 把同步图执行桥接进事件循环，graph 引擎逐 token 发 `text.delta`，无流式时退回 `asyncio.to_thread` + 一次性 delta；缺 `done` 时抛错并被映射为 `INTERNAL`。client 侧 `ChatBox` 新增 `begin_ai_reply/append_ai_delta/finish_ai_reply`，`window` 在 `turn.start` 重置、`text.delta` 增量追加、`text.done` 有增量则收尾、无增量则回退打字机。新增 `test_facade_engine.py` 与 SSE 流式用例，全量 331 passed。

### P7 MCP 工具接入与降级

- [x] `tooling.py` 读取 `MCP_CONFIG_PATH`（默认 `config/mcp_servers.json`）
- [x] 用 `MultiServerMCPClient.get_tools()` 加载；超时/异常/未配置 → warning + `[]`
- [x] MCP 工具合并进 `agent_tools`，参与 `bind_tools` 与 `ToolNode`
- [x] 提供 `config/mcp_servers.example.json`（不含密钥），真实配置 gitignore
- [x] 测试：未配置启动正常、坏配置不崩、工具列表合并
- [x] `pytest -q` 全绿；commit：`feat(mcp): 接入可选 MCP 工具并支持降级`

阶段总结（P7，2026-11-21）：`agent/graph/tooling.py` 新增 `mcp_config_path()`（`MCP_CONFIG_PATH` 优先，相对路径按项目根解析）与 `load_mcp_tools()`；配置兼容 `{"mcpServers": {...}}` 与直接 connections 两种写法，工具名统一加服务前缀避免冲突。适配器缺失、配置不存在、JSON 损坏、配置为空、客户端构造/加载异常、10s 超时均只告警并返回空列表，不影响启动。`MultiServerMCPClient.get_tools` 实测为异步方法，新增 `_run_coro` 在独立线程 `asyncio.run`，避免调用方已有事件循环时报错。MCP 工具与天气/搜索合并后仍过 `_sanitize_tools` 剔除 `get_current_time`。新增 `config/mcp_servers.example.json`，真实 `config/mcp_servers.json` 已写入 `.gitignore`。新增 MCP 降级/合并/时间工具剔除等测试，全量 341 passed。

### P8 测试、文档与收尾

- [x] 补全图相关单元测试与测试说明（`tests/README.md` 更新为 25 个文件 / 343 条）
- [x] 更新 `README.md`：产品定位改为“情感陪伴主体 + 工具按需加载 + 游戏子图”
- [x] 更新 `docs/项目技术文档.md`：新架构、时间注入、情绪契约、MCP 降级
- [x] 检查 `.gitignore`：`config/mcp_servers.json`、运行时缓存、日志
- [ ] 全量 `pytest -q` + CLI 手工验收 8 条（pytest 已 343 passed；CLI/UI 验收需真实 API Key，留待人工执行）
- [x] commit：`test: 补充图编排与时间注入单元测试`、`docs: 更新陪伴主图技术文档`

阶段总结（P8，2026-11-21）：`tests/README.md` 补齐 25 个测试文件清单与 341 条用例统计，新增图引擎、facade、server SSE、MCP 等说明与离线隔离策略；`README.md` 产品定位更新为 LangGraph 陪伴主图（感知门控 + ReAct 工具循环 + 游戏占位子图），补充 `AGENT_ENGINE` 回滚与 MCP 可选配置；`docs/项目技术文档.md` 重写对话流程，补充引擎切换、主图结构、感知门控、时间注入、情绪契约、MemorySaver + JSON 镜像、MCP 降级与当前进度。`.gitignore` 已忽略 `config/mcp_servers.json`。全量 343 passed（含上线后修复的 2 条回归）；CLI/UI 的 8 条验收需真实 API Key，已记录为待人工执行。

**上线后修复（2026-11-22）**：第二次启动报 `Messages with role 'tool' must be a response to a preceding message with 'tool_calls'`。原因是 JSON 历史镜像保存了工具调用中间消息，裁剪/恢复后出现孤立 `ToolMessage`。`runner._clean_history()` 在恢复与写镜像前剥离 `ToolMessage` 与带 `tool_calls` 的 `AIMessage`，`HistoryStore` 通用行为不变；新增 2 条回归用例，全量 343 passed。

**上线后修复（2026-11-22，第二批）**：① 对话中时间字符串泄漏——`strip_time_markers()` 清除模型复述的任意位置时间标记，`text.done` 用最终干净文本覆盖流式展示；② 提示词加载统一到 `utils/prompt_loader.py`，路径由 `config/prompts_config.yml` 的 `graph_system_prompt_path` 提供，删除 `agent_node.py` 本地实现；③ `.env` 解析上移到 `utils/env_utils.py`，facade 与 TTS 复用。新增 14 条用例，全量 357 passed。

**启动顺序调整（2026-11-22）**：`client/main.py` 改为先启动并等待后端就绪（`wait_for_backend()` + `QEventLoop`），再创建/显示主窗口；后端失败时仍显示窗口并提示错误，避免“窗口先出现、用户提前对话、等待后端拉起”的体验问题。

**MCP 可调用修复（2026-11-22）**：MCP 适配器工具是 async-only，同步主图经 ToolNode 调用会得到 `StructuredTool does not support sync invocation`。`tooling._to_sync_tool()` 将其包装为同步工具；配置读取兼容 UTF-8 BOM；示例传输名修正为 `streamable_http`。已用本地 stdio MCP 服务跑通完整主图，新增 2 条用例，全量 359 passed。

**MCP 加载隔离（2026-11-22）**：多服务配置下 `get_tools()` 是全有或全无，任一服务包名错误或冷启动超时都会导致全部工具被丢弃（日志仅显示 `TaskGroup` / 超时）。改为按 `server_name` 逐个并发加载、单服务隔离失败，默认单服务超时提升到 30s（`MCP_LOAD_TIMEOUT` 可覆盖），并展开 ExceptionGroup 打印真实原因。新增 3 条用例，全量 362 passed。

**MCP 接入问题定位（2026-11-22）**：`fetch` / `dokumen_pintar` 因 uvx 首次安装依赖超过 30s 超时；`duckduckgo-mcp` 依赖 Bun 且本机 npm 缓存目录不可写；`git` 的 `--repository` 指向了非 Git 仓库。已实测 `uvx duckduckgo-mcp-server` 与「有效仓库 + `uvx mcp-server-git`」可用；超时日志增加 `MCP_LOAD_TIMEOUT` 提示，README 记录常见坑。新增 1 条用例，全量 363 passed。

---

## 4. 验收核对表（对应提示词 8 条）

| # | 验收项 | 验证方式 | 结果 |
| --- | --- | --- | --- |
| 1 | 多轮聊天上下文连续，回复流式输出 | CLI `agent.graph.demo` 多轮；UI 手工 | 自动化通过（`test_graph_flow` / `test_server_api`）；UI 待手工 |
| 2 | 问“现在几点了”不调用时间工具，但能答对 | 启动日志 `ALL_TOOLS` 无 `get_current_time`；回复时间与当前一致 | 工具侧自动化通过；真实模型答对需手工 |
| 3 | 触发天气/搜索等工具，回复带结果且人格化 | 手工问天气；查看 `tool.call/tool.result` | 自动化覆盖工具循环；人格化回复待手工 |
| 4 | 工具失败用陪伴语气解释，程序不崩 | 注入失败工具/断网；查看 ToolMessage 与回复 | 自动化通过（`handle_tool_errors=True`） |
| 5 | “来下盘五子棋”进入 `game_subgraph`，输出开发中回应 | 日志路由 + 子图输出 | 自动化通过 |
| 6 | `state.messages` Human 带前缀、AI 带后缀；UI 两边都干净 | 打印 state；UI 手工 | 自动化通过（时间注入/剥离）；UI 待手工 |
| 7 | `ALL_TOOLS` / `agent_tools` 均不包含时间工具 | 启动日志 / 断点；时间能力在 `utils/time_utils.py` | 自动化通过 |
| 8 | 未配置 MCP 正常启动仅告警；配置后 MCP 进工具列表 | 删除配置启动；配置 example 启动 | 自动化通过（未配置/坏配置/合并） |

---

## 5. 测试计划

- 基线：`260 passed`，每阶段结束必须保持。
- 新增测试全部不依赖真实 API Key / 网络 / GUI：
  - 假 LLM：自定义 `FakeChatModel`，支持 `bind_tools`、`invoke`、`stream`；按脚本返回 `AIMessage` / `AIMessageChunk` / `tool_calls`。
  - 假工具：`@tool` 定义成功/抛异常两个工具，验证 ToolNode 回传。
  - FakeJev：优先用真实 `FakeJev`；同时测“导入失败回落关键词”。
  - MCP：monkeypatch 加载函数，覆盖未配置、异常、正常三种。
- 重点用例：
  1. `perception_gate` 置信度 0.7 边界（>0.7 才 game）。
  2. 时间前后缀格式、剥离、二次写入不重复。
  3. 情绪标签跨 token、缺失、非法值。
  4. `ALL_TOOLS` / `agent_tools` 均不含 `get_current_time`，时间函数由 `utils/time_utils.py` 覆盖。
  5. 多轮 checkpointer 连续性。
  6. 游戏子图路由与单句输出。
  7. `TurnResult.reply` 干净、`state.messages` 带时间。
  8. SSE 流式 token 顺序与一次性降级。

---

## 6. 风险与回滚

| 风险 | 影响 | 应对 |
| --- | --- | --- |
| `langgraph-jev-router` 低层 API 与 `root_graph.py` 不一致 | 感知门控无法按原型实现 | P0 先核验；写适配器；最终回落本地关键词规则 |
| `langchain-mcp-adapters` 安装失败 / Python 3.13 不兼容 | 验收 8 无法完成 | 依赖隔离在 `tooling.py` 内，导入失败只告警；必要时降级为本期不接 MCP |
| 流式改造导致 UI 闪烁/重复 | 体验回退 | 保留一次性 `text.delta` 降级；`text.done` 统一收尾 |
| MemorySaver 重启丢失 | 记忆回退 | JSON 镜像 + 首次注入；测试覆盖 |
| 时间能力迁出后 legacy 回滚路径失去时间工具 | legacy 无法回答时间问题 | 已确认接受；legacy 仅结构回滚，完整回退需回退 P2-A 的 `refactor(utils)` commit |
| 情绪标签模型不遵守 | 表情退化 | 正则容错 + 回退 neutral；提示词给示例 |
| 旧测试被破坏 | 回归风险 | `AGENT_ENGINE=legacy` 保留旧路径；每阶段跑全量 |
| 时间戳重复追加 | messages 脏数据 | 统一走 `with_reply_time`，测试幂等性 |
| 工具分组误挂载办公工具 | 误调用 | 本阶段 office 组为空；后续按关键词 + 白名单双控 |

回滚：`.env` 设 `AGENT_ENGINE=legacy` 即可回到 `ChatAgent`（不含时间工具）；如需连时间能力一起回退，回退 P2-A 的 `refactor(utils)` commit。新增包与旧代码无循环依赖。

---

## 7. 确认结果与执行约定

已于 2026-11-21 确认：

1. **D1–D5 全部采用推荐方案**。
2. **D6 时间能力迁至 `utils/`**：新增 `utils/time_utils.py`；删除 `tools/common/get_time.py`；从 `ALL_TOOLS` 与 `emotion` 模式白名单移除；图引擎与时间注入直接 import。
3. 命名：新增包用 `agent/graph/`，执行文档/开发记录放根目录（本文件与配套记录）。
4. 提交粒度：P2 拆两个 commit（先 `refactor(utils): ...`，再 `feat(graph): ...`）；其余阶段各一个 commit，格式 `type: 描述`。
5. 已知取舍：legacy 回滚路径不再具备时间工具；`agent/mode_configs/office` 暂保留但不再参与路由。

> 本次仅修改文档，不做 git commit、不开始开发；确认后按 P0 开始。
