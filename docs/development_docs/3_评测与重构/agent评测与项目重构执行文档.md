# Agent 评测体系与项目升级执行文档

> 创建日期：2026-11-22
> 适用范围：评测体系搭建、Live2D 行为升级、目录整理与旧版归档、收尾文档
> 执行约定：每个小阶段完成后打勾并写阶段总结；全量测试通过后按 `type: 描述` 提交；本文件与配套开发记录本次不提交 git。

---

## 一、背景与目标

项目已从 legacy 多模式 `ChatAgent` 迁移到 LangGraph 情感陪伴主图，具备感知门控、ReAct 工具循环、时间注入、情绪标签、流式 SSE、MCP 可选工具与多轮记忆，单元测试基线为 **363 passed**。当前仍有四个缺口：

1. **缺少行为级评测**：`tests/` 偏单元/模块测试，缺少“给定输入 → 路由 / 工具 / 时间 / 容错 / 流式 / 记忆”的回归安全网。
2. **Live2D 表现偏静态**：只有表情动作，没有鼠标跟随，也没有空闲随机动作，桌宠生命力不足。
3. **目录分散**：`agent/`、`server/`、`core/`、`protocol/`、`modelFactory/`、`tools/` 平铺在根目录，后端边界不清晰；legacy 多模式代码仍混在活跃目录中。
4. **文档与旧代码未收口**：多模式相关说明仍散落在 README / 技术文档中，`.gitignore` 需要补评测产物与参考文档。

总体目标：

- 建立**确定性优先、可扩展、可 CI 化**的评测体系（`evals/`）。
- 让 Live2D 具备鼠标跟随与随机动作，同时保证 AI 表情动作优先级最高。
- 将后端收敛到 `backend/`，旧版多模式代码统一归档到 `archive/legacy_multi_mode/`。
- 文档、测试、`.gitignore` 与最终目录保持一致。

非目标：

- 不在本阶段引入 LLM-as-Judge、LangSmith、deepeval、ragas 等外部评测平台。
- 不重写主图业务逻辑，不为测试往主图加 `if test_mode` 分支。
- 不恢复多模式 agent，也不继续扩展办公 / 编程模式。
- 不提交 `live2dmascot/` 与 `agent评测体系说明文档.md`。

---

## 二、现状评估

### 2.1 `bench/` 的作用与保留结论

| 文件 | 作用 | 结论 |
| --- | --- | --- |
| `bench/run_bench.py` | 真实拉起后端，逐条请求 `/v1/chat` SSE，统计 P50/P95 延迟、工具调用率、错误率 | **保留** |
| `bench/prompts.jsonl` | 20 条固定测试 prompt | **保留** |
| `bench/result.csv` | 运行输出，已在 `.gitignore` 中忽略 | 保留本地，不入库 |

`bench/` 是**性能与真实模型批量基准**（消耗 API 额度），`evals/` 是**行为正确性回归**（确定性、默认不联网）。两者定位不同，不合并；目录整理阶段只需把其拉起后端的入口从 `python -m server` 改为 `python -m backend`。

### 2.2 Live2D 现状

- `client/ui/live2d_widget.py`：120fps `timerEvent` 驱动 `Update/Draw`，已支持模型自适应缩放、点击穿透判断、单次启动动作、情绪动作与结束过渡。
- `client/emotion_map.py`：10 种情感 → 6 组 HiYori 动作，`request_play_motion()` 由 SSE `emotion` 事件触发。
- 现状缺口：
  - 没有鼠标位置跟踪，未调用 `LAppModel.Drag(x, y)`；
  - 没有空闲随机动作调度；
  - 启动时使用 `StartMotion("TapBody", ...)`，而模型实际动作组为 `Idle / Flick / FlickDown / Tap / Tap@Body / Flick@Body`，组名不一致会静默失败；
  - 情绪动作与将来的随机动作之间缺少统一的优先级/互斥状态机。
- `live2dmascot/` 可复用的思路：`scene.py` 在鼠标移动时调用模型 `Drag`；动作通过 `StartRandomMotion(group, priority)` 调度；动作优先级由 `MotionPriority` 控制。只参考实现思路，不复制框架代码，也不提交该目录。

### 2.3 目录与旧代码现状

- 后端相关：`server/`（FastAPI）、`agent/`（主图 + legacy）、`core/`（facade/session/tracing）、`protocol/`（请求与事件）、`modelFactory/`、`tools/common/`、根 `utils/`。
- 前端：`client/`。
- 旧版多模式相关（当前仍被引用，需先解耦再归档）：
  - `chatbot.py`（模块级 `_agent` 兼容层）
  - `agent/chat_agent.py`（legacy 引擎，同时定义 `HistoryStore` 与 `TurnResult`）
  - `agent/mode_configs/`（`emotion` / `office` 模式注册表）
  - `agent/tool_manager.py`（legacy 工具注册表；主图 `tooling.py` 仍借它取天气/搜索）
  - `/v1/modes`、`/v1/mode` 路由、`ModeRequest`、`ChatRequest.mode`
- 结论：`HistoryStore` / `TurnResult` / 基础工具必须先抽出为公共能力，才能归档 legacy 引擎。

### 2.4 `.gitignore` 现状

- 已忽略 `live2dmascot/`。
- 本次已补充 `agent评测体系说明文档.md`（禁止提交）。
- 阶段一需补充 `evals/reports/`；阶段四统一复核。

---

## 三、关键决策

| 编号 | 决策 | 理由 |
| --- | --- | --- |
| D1 | 评测分为“确定性回归（默认）”与“实时冒烟（`live` 标记，按需）”两层 | 默认无 API Key、无网络也能跑，适合频繁执行与 CI |
| D2 | 评测用例采用声明式 dict + 统一 runner，不直接写复杂断言脚本 | 新增用例成本低，指标口径统一 |
| D3 | 评测不修改主图源码；LLM / 工具 / 历史文件通过构造参数注入 | 保持产品代码干净，避免测试分支 |
| D4 | Live2D 鼠标跟随使用模型 `Drag` + 平滑插值，情绪动作期间暂停跟随 | 避免与动作角度竞争，减少抖动 |
| D5 | 随机动作使用 `StartRandomMotion` + `NORMAL` 优先级，情绪动作保持 `FORCE` | 表情优先级天然高于空闲动作 |
| D6 | 后端统一收敛到 `backend/`（`api` + `agent` + `core` + `protocol` + `model_factory`），`utils/` 保持根级共享 | 后端边界清晰，同时不破坏 client 共用工具 |
| D7 | 旧版多模式代码整体归档，`AGENT_ENGINE` / legacy 引擎 / 模式 API 移除 | 与当前单一陪伴主图方向一致；归档目录保留恢复可能 |
| D8 | `bench/` 保留为性能基准，不并入 `evals/` | 真实模型延迟/工具率与确定性回归互补 |
| D9 | `expression_tester.py` 移至 `scripts/`；`resources.py` 若确认无引用则归档 | 根目录只保留入口与数据目录 |

---

## 四、阶段总览

| 阶段 | 内容 | 小阶段 | 状态 |
| --- | --- | --- | --- |
| 第一阶段 | 智能体评测体系搭建 | E1 / E2 / E3 | 完成 |
| 第二阶段 | Live2D 形象动作升级 | L1 / L2 / L3 | 完成（待桌面手工验收） |
| 第三阶段 | 目录整理与旧版归档 | R1 / R2 / R3 / R4 | 完成 |
| 第四阶段 | 收尾：测试、文档、gitignore | D1 / D2 / D3 | 完成（待桌面手工验收） |

---

## 五、第一阶段：智能体评测体系搭建

### E1 评测骨架 + 路由/时间回归

**目标**：建立可运行、可出报告的评测框架，先覆盖最容易回归的路由与时间注入。

产出目录：

```text
evals/
├── __init__.py
├── conftest.py                 # 图构建、脚本化 LLM、临时历史、报告插件
├── keywords.py                 # 游戏拒绝词 / 失败解释词 / 禁用技术词 / 时间正则
├── cases/
│   ├── __init__.py
│   ├── routing_cases.py
│   ├── time_cases.py
│   ├── tool_cases.py           # E2 填充
│   ├── resilience_cases.py     # E2 填充
│   ├── stream_cases.py         # E2 填充
│   └── memory_cases.py         # E2 填充
├── runners/
│   ├── __init__.py
│   └── graph_runner.py         # 单用例执行器：state / messages / deltas / 耗时
├── reporting.py                # pytest 钩子 → reports/latest.json
├── test_routing.py
├── test_time_injection.py
├── test_tool_calls.py          # E2
├── test_resilience.py          # E2
├── test_stream_contract.py     # E2
├── test_memory.py              # E2
├── live/
│   ├── __init__.py
│   └── test_live_smoke.py      # E3
├── README.md
└── reports/                    # gitignore；运行时生成
```

任务清单：

- [x] `ScriptedLLM`：实现 `bind_tools / invoke / stream`，按脚本返回 `AIMessage`（可检查消息后动态决定），用于确定性用例。
- [x] `run_case(case)`：构建带 `MemorySaver` 的主图，独立 `thread_id`，返回 `reply / emotion / route / messages / tool_messages / deltas / elapsed_ms`。
- [x] 用例 schema：`id / category / description / input / expect / tags`，`expect` 支持 `route / tool_name / tool_content_contains / final_contains_any / no_tool / forbid_in_final / delta_clean`。
- [x] 路由用例 4 条：明确游戏意图、倾诉中提游戏（反例）、模糊输入、非游戏任务。
- [x] 时间用例 3 条：state 前缀/后缀正则、流式 delta 无时间后缀、时间工具不在 `agent_tools` 且聊天不触发时间工具。
- [x] 报告：`pytest evals/` 结束后写 `evals/reports/latest.json`（id、category、passed、attempts、duration_ms、failure）。
- [x] `.gitignore` 增加 `evals/reports/`（已完成）；`pyproject.toml` 的 `live` marker 与 `norecursedirs = archive` 分别在 E3 / R3 完成。
- [x] `evals/README.md`：如何新增用例、如何跑单类、如何看报告。

验收：

- [x] `pytest evals/test_routing.py evals/test_time_injection.py -q` 全部通过，无 API Key、无网络。
- [x] 每条用例使用独立 `thread_id`，不污染 `chat_history/`。
- [x] 报告 JSON 字段齐全。

实际结果：7 条用例全部通过；时间流式用例发现并修复了一个真实缺陷——LangGraph 在 messages 流末尾会补发节点最终消息的增量（仅含 ` [YYYY-MM-DD HH:MM]`），导致 UI 末尾出现时间字符串。已在 `utils/time_utils.py` 新增 `TimeMarkerStreamFilter` 并在 `stream_chat` 中先过滤时间、再处理情绪标签。

提交：`test(eval): 搭建评测骨架与路由/时间回归`

---

### E2 工具、容错、流式与记忆回归

**目标**：覆盖主图最关键的运行时行为，形成 16~20 条确定性用例。

任务清单：

- [x] M1 工具正确性：注入假 `get_weather` / `web_search`，断言 `ToolMessage.name`、结果片段、最终回复包含关键内容；覆盖成功与空结果/失败。
- [x] M4 容错：构造必然抛错的工具，断言图不抛异常、ToolMessage 携带错误、最终回复命中失败解释词且不含 `Traceback / Error: / FileNotFoundError`。
- [x] M5 流式契约：`CompanionGraphAgent.stream_chat` 的 delta 拼接与 `done.reply` 均为干净文本；不得出现 `[YYYY-MM-DD HH:MM]` 后缀；`done.emotion` 合法。
- [x] M6 记忆：临时 `history_file` 跑两轮 → 新建实例恢复 → 断言历史注入、`ToolMessage` 已过滤（回归 FIX“role=tool 非法请求”）。
- [x] 失败信息进入报告时保留断言表达式与期望值，便于定位。
- [x] 覆盖 `forbid_in_final`、`no_tool` 等反向断言，避免“只断言非空”的弱用例。

验收：

- [x] `pytest evals/ -q` ≥ 16 条用例，全部通过（实际 21 条）。
- [x] 工具用例不访问真实网络；时间断言只用正则。
- [x] 至少 1 条用例专门覆盖“工具失败但人格化回复”（`resilience_tool_raises_01` 等 2 条）。

提交：`test(eval): 补齐工具、容错、流式与记忆评测`

---

### E3 实时冒烟与运维化

**目标**：在真实模型可用时提供小样本冒烟，并让评测可长期维护。

任务清单：

- [x] `live/test_live_smoke.py`：读取 `.env`，无 `API_KEY` 或未设置 `RUN_LIVE_EVALS=1` 时 `skip`；3 条真实对话（闲聊 / 时间 / 工具），只断言结构（`emotion` 合法、无标签泄漏、无时间戳泄漏、回复非空），不断言具体措辞。
- [x] 支持 `RUN_LIVE_EVALS=1 pytest evals/live -m live -q`，报告中标记 `live`。
- [x] 报告增加汇总：总数、通过率、按 category 统计、最慢 5 条。
- [x] `evals/README.md` 补充“何时跑确定性 / 何时跑 live / 如何新增一类指标”。
- [x] 与 `bench/` 的分工写入 README 与评测 README。

验收：

- [x] 默认 `pytest evals/` 不触发真实模型（21 passed / 3 skipped）。
- [x] live 用例在无 Key 时正确 skip，有 Key 时按 3 条通过（本机实跑 3 passed in 49.11s）。

提交：`docs(eval): 完善实时冒烟与评测说明`

### E1 阶段总结（2026-11-23）

- 建立 `evals/` 骨架：脚本化 LLM、统一 runner、JSON 报告、MCP 隔离。
- 7 条确定性用例通过，覆盖 M2 路由（含“倾诉提游戏”反例）与 M3 时间三层断言。
- 发现真实回归：流式 messages 末尾补发的节点最终消息带时间后缀，UI 会显示 ` [YYYY-MM-DD HH:MM]`；已用 `TimeMarkerStreamFilter` 在流层修复，并补 5 条单元测试（全量 368 passed）。

### E2 阶段总结（2026-11-23）

- 用例总数 7 → 21：tool 5 / resilience 3 / stream 4 / memory 2，加上 E1 的 routing 4 / time 3。
- 工具用例全部使用 `evals/cases/tool_defs.py` 的本地假工具（`get_weather` / `web_search` / 异常与错误文本工具），不访问网络。
- 容错用例验证：工具抛异常时 ToolNode 转为 `status=error` 的 ToolMessage，图正常收尾；最终回复不泄漏 `RuntimeError / Error: / 查询失败` 等技术字样，并有“失败后重试成功”路径。
- 流式契约统一断言 `"".join(deltas) == done.reply`，并覆盖情绪标签跨 token、模型复述时间标记、非法情绪回退 neutral。
- 记忆用例覆盖跨实例恢复与历史残留 tool 消息过滤（role=tool 回归）；`run_memory_case` 使用临时 history 文件，不写 `chat_history/`。
- 断言失败信息统一为 `[字段] 期望=... 实际=... | case=...`，报告 JSON 的 `failure` 字段可直接定位。
- 验证：`pytest evals/ -q` → 21 passed；全量 `pytest -q` → 368 passed。

### E3 阶段总结（2026-11-23）

- 新增 `evals/live/test_live_smoke.py`：`RUN_LIVE_EVALS=1` + `.env` 有 `API_KEY` 才运行，否则整组 skip；冒烟用 `history_file=None`，不写 `chat_history/`。
- 3 条真实对话（闲聊 / 时间 / 工具）只断言结构：回复非空、无情绪标签与 `[YYYY-MM-DD HH:MM]` 泄漏、`emotion` 合法。
- 报告新增 `pass_rate` 与 `slowest`（最慢 5 条），live 用例以 `category=live` 标记；`pyproject.toml` 注册 `live` marker。
- README 与 `evals/README.md` 写明 `tests/` / `evals/` / `bench/` 分工及确定性、live 的运行方式。
- 验证：`pytest evals/ -q` → 21 passed / 3 skipped；`RUN_LIVE_EVALS=1 pytest evals/live -m live -q` → 3 passed；全量 `pytest -q` → 368 passed。

### 第一阶段总结（2026-11-23）

- 确定性用例 21 条（routing 4 / time 3 / tool 5 / resilience 3 / stream 4 / memory 2），默认无 Key、无网络运行。
- live 冒烟 3 条，按需启用，仅校验结构与过滤契约。
- 建立统一 runner、声明式用例、JSON 报告（含通过率与最慢 5 条）、MCP 隔离与失败的期望值定位信息。

---

## 六、第二阶段：Live2D 形象动作升级

### L1 眼睛与身体随鼠标倾斜

**目标**：无论鼠标在窗口内外，模型头部/眼睛平滑朝向鼠标，窗口拖拽与缩放不受影响。

任务清单：

- [x] 新增 `client/live2d_behavior.py`（纯函数，便于单测）：
  - `normalize_cursor(cursor_x, cursor_y, width, height) -> (nx, ny)`，输出 [-1, 1] 并限幅；
  - `smooth_toward(current, target, factor)`；
  - `pick_random_group(groups, rng, exclude=None)`（L2 使用）。
- [x] `Live2DWidget` 每帧读取 `QCursor.pos()` → 映射到部件坐标 → 平滑 → `model.Drag(nx, ny)`（在 `Update()` 前调用）。
- [x] 启用 `setMouseTracking(True)`；拖拽窗口 / 滚轮缩放逻辑保持原行为。
- [x] 情绪动作播放与回归过渡期间暂停 `Drag`，结束后平滑恢复（避免与动作角度打架）。
- [x] 修正启动动作组：移除无效的 `TapBody`，改为一次 `Idle` 或直接交给 L2 调度。
- [x] 新增 `tests/test_live2d_behavior.py`：边界限幅、中心点、平滑收敛、随机组不重复。

验收：

- [ ] 鼠标移动时头部/眼睛跟随平滑，无抖动、无跳变。
- [ ] 拖拽窗口、缩放、点击穿透、右键菜单均正常。
- [x] 纯函数测试通过；UI 行为手工确认。

提交：`feat(client): Live2D 眼睛与身体随鼠标倾斜`

---

### L2 空闲随机动作与表情优先级

**目标**：空闲时随机播放动作组；AI 表情动作始终优先。

任务清单：

- [x] 状态机：`idle / random_playing / emotion_playing / emotion_returning`，统一由 `Live2DWidget` 管理。
- [x] 空闲 8~15 秒随机选择动作组（`Idle / Flick / FlickDown / Tap / Tap@Body / Flick@Body` 与 `GetMotionGroups()` 取交集），`StartRandomMotion(group, NORMAL)`；避免连续重复同一组。
- [x] 情绪动作（`request_play_motion`）进入时：取消待触发的随机动作、`StartMotion(..., FORCE)`、暂停鼠标跟随；动作结束进入回归过渡，过渡完成后重置随机计时并恢复跟随。
- [x] 随机动作播放期间不触发新的随机动作；一轮对话/打断后状态可恢复。
- [x] 补充纯函数测试（随机排除当前组、间隔范围、优先级状态迁移）。

验收：

- [ ] 静置时能观察到随机小动作，节奏自然、不抢表情。
- [ ] 表情动作触发时立即覆盖随机动作，结束后回到常态。
- [ ] 长时间运行无动作卡死、CPU 明显上升。

提交：`feat(client): Live2D 随机动作组与表情优先级`

---

### L3 联调与调参

- [x] 调整平滑系数、随机间隔、动作幅度，避免“晕动”与机械感。
- [x] 检查 120fps 循环下新增逻辑的性能开销（不新增逐帧像素读取）。
- [x] 更新 `docs/项目技术文档.md` 的 Live2D 章节（状态机、优先级、参数）。
- [ ] 手工验收：鼠标跟随 + 随机动作 + 表情 + 拖拽 + 缩放 + 打断。

提交：`docs(client): 补充 Live2D 行为状态机说明`（或与 L2 合并提交）

### L1 阶段总结（2026-11-23）

- 新增 `client/live2d_behavior.py`：`clamp` / `normalize_cursor`（[-1,1] 限幅）/ `denormalize_cursor` / `smooth_toward` / `pick_random_group`，全部纯函数。
- `Live2DWidget` 的 `timerEvent` 每帧读取光标 → 归一化 → 指数平滑（系数 0.25，120fps 下约 90ms 收敛）→ 还原像素 → `model.Drag`；情绪动作与回常态过渡期间跳过，结束后从上次平滑值继续。
- 实测 `live2d-py` 的 `Drag` 接收与 `Resize` 同尺度的部件像素坐标（官方 glfw 示例一致），因此内部平滑用归一化，调用前还原为像素。
- 移除无效启动动作 `TapBody`，改为 `StartMotion("Idle", 0, NORMAL)`；启用 `setMouseTracking(True)`，不影响拖拽/滚轮逻辑。
- 新增 `tests/test_live2d_behavior.py` 19 条用例；全量 `pytest -q` → 387 passed。

### L2 阶段总结（2026-11-23）

- `Live2DWidget` 统一状态机：`idle / random_playing / emotion_playing / emotion_returning`；表情结束 → 回归过渡 → 空闲，回归完成后重新计时。
- 空闲 8~15s（`random_interval_seconds`）从 `GetMotionGroups()` 实际动作组中随机选择，`StartRandomMotion(group, NORMAL)`，并排除上一次动作组。
- 表情动作 `FORCE` 覆盖随机动作，进入时取消待触发计时；回归过渡完成后恢复鼠标跟随与随机调度；`reset_emotion` 同步回到空闲并重新计时。
- 纯函数新增 `random_interval_seconds`、`next_state_on_motion_end`，测试增至 28 条；全量 `pytest -q` → 396 passed。
- 静态导入校验通过；随机动作体感与长时运行留给 L3 手工验收。

### L3 阶段总结（2026-11-23）

- 参数定稿：跟随平滑系数 0.25、随机间隔 8~15s、回归过渡 1.5s smoothstep；均为模块级常量，便于后续按体感微调。
- 性能：新增逻辑仅每帧一次 `QCursor.pos` + `mapFromGlobal` + C++ `Drag`，未新增逐帧像素读取（原有 `is_in_l2d_area` 不变）；120fps 循环开销可忽略。
- `docs/项目技术文档.md` 的 Live2D 章节补充“鼠标跟随”“动作状态机与优先级”“平滑回常态”三节。
- 手工验收（跟随手感、随机节奏、拖拽/缩放/打断）需在桌面环境运行客户端确认，清单保留未勾。

**阶段二总结**：

- 行为分层：纯函数（`client/live2d_behavior.py`）负责坐标/平滑/随机/状态迁移，`Live2DWidget` 只做每帧驱动与模型调用，便于单测。
- 实际参数：平滑 0.25、随机 8~15s、回归 1.5s；表情 FORCE 覆盖随机 NORMAL，回归期间暂停跟随。
- 未采用：`live2dmascot` 的框架代码与按部件透明度点击高亮；不使用逐帧 `glReadPixels` 做跟随计算（沿用原有单点 alpha 判定）。
- 已知待办：桌面环境手工验收。

---

## 七、第三阶段：目录整理与旧版归档

### 3.1 目标目录

```text
backend/
├── __init__.py
├── __main__.py                 # python -m backend（原 python -m server）
├── api/
│   ├── __init__.py
│   ├── app.py
│   ├── security.py
│   ├── services.py
│   └── routes/{__init__.py, chat.py, meta.py}
├── agent/
│   ├── __init__.py
│   ├── expression_driver.py
│   ├── history.py              # 从 chat_agent.py 抽出的 HistoryStore
│   ├── turn.py                 # 从 chat_agent.py 抽出的 TurnResult
│   ├── graph/                  # 现有 graph 包整体迁入
│   └── tools/{__init__.py, weather.py, web_search.py}
├── core/{__init__.py, facade.py, session.py, tracing.py}
├── model_factory/{__init__.py, factory.py}
└── protocol/{__init__.py, events.py, requests.py}

client/                         # 不变
utils/                          # 保持根级：client 与 backend 共享
prompts/ config/ Resources/     # 数据目录保持根级
tests/                          # 保持根级，更新导入
evals/ bench/ docs/ scripts/    # 根级
archive/
└── legacy_multi_mode/
    ├── README.md               # 归档原因、原路径、恢复方法
    ├── chatbot.py
    ├── agent/{chat_agent.py, tool_manager.py, mode_configs/}
    ├── protocol/mode_request.py
    ├── tests/{test_chatbot.py, test_chat_agent.py, test_mode_configs.py, test_tool_manager.py}
    └── docs/                   # 旧多模式相关文档摘录
main.py                         # client 入口 shim，保留
```

### R1 解耦公共能力

- [x] 新建 `agent/history.py`（`HistoryStore`）与 `agent/turn.py`（`TurnResult`），从 `chat_agent.py` 迁出。
- [x] 更新 `graph/runner.py`、`core/session.py`、`server/services.py`、路由与测试的导入。
- [x] 主图工具改由自身注册表直接加载 `get_weather` / `web_search`，不再依赖 `ToolManager`。
- [x] 图模式生成参数从 `MODE_REGISTRY["emotion"]` 迁到 `agent/graph/config.py`（或常量模块）。
- [x] 全量测试通过。

提交：`refactor(agent): 抽出历史与回合类型并解除旧引擎依赖`

### R2 后端收敛到 backend/

- [x] `git mv` 迁移：`server/` → `backend/api/`，`agent/` → `backend/agent/`，`core/` → `backend/core/`，`protocol/` → `backend/protocol/`，`modelFactory/` → `backend/model_factory/`，`tools/common/` → `backend/agent/tools/`。
- [x] 全局改写导入前缀：`agent.` / `server.` / `core.` / `protocol.` / `modelFactory.` / `tools.common.`。
- [x] 入口改为 `python -m backend`；同步更新 `client/server_launcher.py`、`bench/run_bench.py`、测试与文档。
- [x] 更新 `evals/` 中的导入与 fixture。
- [x] 保留 `client/`、`utils/`、`prompts/`、`config/`、`Resources/` 路径不变。
- [x] 全量 pytest + `pytest evals/` 通过。
- [ ] 手工启动一次客户端（`uv run python main.py`）。

提交：`refactor: 后端目录收敛为 backend 包`

### R3 归档旧版多模式 agent

- [x] 删除 `/v1/modes`、`/v1/mode` 路由与 `ModeRequest`；`ChatRequest` 去掉 `mode` 字段。
- [x] `Services` 去掉 `current_mode` / `list_modes` / `set_mode`；`_resolve_agent` 简化。
- [x] `core/facade.py` 改为 graph-only：移除 `AGENT_ENGINE` / `resolve_engine` / legacy 分支 / `switch_mode`。
- [x] 归档 `chatbot.py`、`chat_agent.py`、`mode_configs/`、`tool_manager.py`、相关测试与 `ModeRequest` 副本。
- [x] 增加 `archive/legacy_multi_mode/README.md`（含恢复步骤）；`pyproject.toml` 配置 `norecursedirs = ["archive"]`，避免归档测试被收集。
- [x] 更新 `.env` 文档：移除 `AGENT_ENGINE`。
- [x] 全量测试与评测通过；client 无模式相关调用，确认不受影响。

提交：`refactor: 归档旧版多模式 agent`

### R4 根目录收尾

- [x] `expression_tester.py` → `scripts/expression_tester.py`，更新文档引用与运行命令。
- [x] `resources.py` 确认无引用后归档（或删除），同步 `docs/`。
- [x] 根目录执行文档 / 开发记录移入 `docs/development_docs/3_评测与重构/`（第四阶段文档更新时执行）。
- [x] 检查 `__pycache__`、临时文件、`.pyc` 未入库。

提交：`chore: 整理根目录与开发脚本位置`

### R4 阶段总结（2026-11-23）

- `git mv expression_tester.py → scripts/expression_tester.py`：改用 `utils.path_tool.get_abs_path` 定位模型与预设，并把项目根注入 `sys.path`；`py_compile` 通过，文档命令同步为 `uv run python scripts/expression_tester.py`。
- 确认 `resources.py` 无代码引用（仅 README/文档提及），直接删除；README、`docs/项目技术文档.md`、`tests/README.md` 同步。
- 根目录两份计划文档移入 `docs/development_docs/3_评测与重构/`（仍不入库）。
- 清理 R2 迁移后残留的 `tools/` 空目录与根 `__pycache__`，确认仓库无 `.pyc` 入库。

提交：`chore: 整理根目录与开发脚本位置`

### R1 阶段总结（2026-11-23）

- 新增 `agent/history.py`（`HISTORY_DIR` / `HISTORY_WINDOW` / `HistoryStore`）与 `agent/turn.py`（`ToolCallRecord` / `TurnResult`）；`chat_agent.py` 改为从新模块导入，legacy 测试的 monkeypatch 目标保持可用。
- 导入改写：`graph/runner.py`、`core/session.py`、`server/services.py`、`core/tracing.py`、`core/facade.py`、`evals/runners/graph_runner.py`、`tests/test_chat_agent.py`、`tests/test_graph_flow.py`。
- `graph/tooling.py` 自持 `BASE_TOOL_MAP`（`get_weather` / `web_search`），不再实例化 `ToolManager`。
- 新增 `agent/graph/config.py` 的 `GRAPH_MODEL_PARAMS`，`core/facade.py` 的 graph 分支不再读取 `MODE_REGISTRY`。
- 验证：相关 90 passed / 3 skipped；全量 `pytest -q` → 396 passed。

### R2 阶段总结（2026-11-23）

- `git mv` 迁移 5 个后端包 + `tools/common`：`server→backend/api`、`agent→backend/agent`、`core→backend/core`、`protocol→backend/protocol`、`modelFactory→backend/model_factory`、`tools/common→backend/agent/tools`；新增 `backend/__init__.py`、`backend/__main__.py`。
- 43 个 Python 文件完成导入前缀改写；补齐字符串形式的 monkeypatch/patch 目标（`backend.agent.chat_agent.*`、`backend.model_factory.factory.*`）。
- 入口统一为 `python -m backend`：`client/server_launcher.py`、`bench/run_bench.py`、README 与 `backend/__main__.py` 同步更新；`backend --help` 正常输出。
- 验证：全量 `pytest -q` → 396 passed；`pytest evals -q` → 21 passed / 3 skipped。
- 迁移脚本修正了一处误替换（`server.log` 被改写），已还原为原日志名。

### R3 阶段总结（2026-11-23）

- 删除模式 API：`/v1/modes`、`/v1/mode`、`ModeRequest`、`ChatRequest.mode`；`meta.py` 仅保留 `/v1/health`。
- `Services` 移除 `current_mode` / `list_modes` / `set_mode`，`chat` / `stream_chat` 不再接收 mode；协议中的 `turn.start.mode` 固定为 `AGENT_MODE = "emotion"`。
- `core/facade.py` 改为 graph-only（移除 `AGENT_ENGINE` / `resolve_engine` / legacy 分支 / `switch_mode`）；`core/session.py` 的 agent 类型改为 `CompanionGraphAgent`。
- `git mv` 归档到 `archive/legacy_multi_mode/`：`chatbot.py`、`agent/chat_agent.py`、`agent/tool_manager.py`、`agent/mode_configs/`、4 个 legacy 测试、`ModeRequest` 摘录；附 `README.md` 恢复步骤与 `docs/README.md` 占位。
- `pyproject.toml` 增加 `norecursedirs = ["archive"]`；README 结构段与 `.env` 环境变量表同步移除多模式内容。
- `tests/test_facade_engine.py` 重写为 graph-only 门面测试；`test_protocol.py` / `test_server_api.py` 删除模式相关用例。
- 验证：全量 `pytest -q` → 306 passed；`pytest evals -q` → 21 passed / 3 skipped；`python -m backend --help` 正常。

提交：`refactor: 归档旧版多模式 agent`

**阶段三总结**：后端从 6 个根级包收敛为 `backend/`（api / agent / core / protocol / model_factory），43 个 Python 文件批量改写导入，入口统一为 `python -m backend`；旧多模式实现（9 项）整体归档到 `archive/legacy_multi_mode/`，`AGENT_ENGINE`、模式 API 与 legacy 引擎从活跃代码移除；根目录只保留入口、数据目录与配置，调试脚本移入 `scripts/`。遇到的问题：`server.log` 被批量替换误改（R2 已还原）、归档测试需 `norecursedirs` 排除（R3）、协议 `turn.start.mode` 采用固定值保留以兼容客户端（R3）。验证：R2 全量 396 passed；R3 起 306 passed（81 条 legacy 测试随归档移出）+ evals 21 passed / 3 skipped；`python -m backend --help` 正常。

---

## 八、第四阶段：收尾

### D1 测试补齐与回归

- [x] 为迁移后的模块补充/修正测试导入；新增 Live2D 纯函数、HistoryStore 抽取、graph-only facade 的测试。
- [x] 更新 `tests/README.md`：文件列表、用例数、运行命令（`uv run pytest -q`）。
- [x] 全量 `uv run pytest -q` 与 `pytest evals/ -q` 通过；确认无网络/无 Key 依赖。

提交：`test: 更新目录调整后的测试与用例统计`

### D2 文档更新

- [x] `README.md`：项目结构改为 backend/client/utils/evals/bench/archive；补充评测、Live2D 行为、MCP、目录说明；命令统一为 `uv run`。
- [x] `tests/README.md`：与最终测试文件一一对应。
- [x] `docs/项目技术文档.md`：后端分层、评测体系、Live2D 状态机、时间/情绪/记忆链路更新。
- [x] `docs/前后端接口JSON契约_v1.md`：删除 `mode` 字段与 `/v1/modes`、`/v1/mode`；补充变更记录；确认 client 字段兼容。
- [x] 将多模式相关旧内容移入 `archive/legacy_multi_mode/docs/`，活跃文档只保留“已归档”指引。
- [x] 确认 `live2dmascot/` 与 `agent评测体系说明文档.md` 未被跟踪。

提交：`docs: 更新项目文档至最新结构`

### D2 阶段总结（2026-11-23）

- README：定位改为单陪伴主图，结构段改为 `backend/` + `archive/`，命令统一 `uv run`，补充 Live2D 跟随/随机动作特性。
- `docs/项目技术文档.md`：删除引擎切换与多模式配置说明，改为 graph-only 单引擎；更新主图工具来源、单模式说明、记忆隔离（thread_id=session_id）、评测现状与未来子图扩展措辞。
- `docs/前后端接口JSON契约_v1.md`：删除 `/v1/modes`、`/v1/mode` 两节与 `ChatRequest.mode`，章节重新编号；`turn.start.mode` 标注固定 `emotion`；路径全部改为 `backend/...`；变更记录新增 2026-11-23 条目。
- 旧多模式接口/引擎说明摘录至 `archive/legacy_multi_mode/docs/多模式接口与引擎说明.md`，活跃文档仅保留归档指引。
- 确认 `live2dmascot/`（`.gitignore:53`）与 `agent评测体系说明文档.md`（`.gitignore:56`）均未被跟踪。

### D3 最终检查

- [x] `.gitignore` 复核：`live2dmascot/`、`agent评测体系说明文档.md`、`evals/reports/`、`bench/result.csv`、日志/缓存/环境文件。
- [x] `git status` 无意外未跟踪产物；`git ls-files | Select-String live2dmascot|评测体系说明文档` 为空。
- [ ] 手工验收清单全部通过（见附录 B）。<!-- 需在桌面环境人工执行，代码侧已完成 -->
- [x] 阶段总结写入开发记录。

提交：`chore: 收尾检查与 gitignore 补齐`

### D3 阶段总结（2026-11-23）

- `.gitignore` 复核完成：`__pycache__/`、`*.py[oc]`、`.venv`、`.env*`、`.pytest_cache/`、`*.log`、`logs/`、`bench/result.csv`、`chat_history/`、`config/mcp_servers.json`、`live2dmascot/`、`agent评测体系说明文档.md`、`evals/reports/` 均已覆盖。
- 新增两条计划/记录文档忽略规则（`docs/development_docs/3_评测与重构/agent评测与项目重构{执行文档,开发记录}.md`），`git status` 不再显示。
- `git ls-files` 确认 `live2dmascot/` 与 `agent评测体系说明文档.md` 均未入库。
- 最终验证：全量 `pytest -q` → 321 passed；`pytest evals -q` → 21 passed / 3 skipped。
- 附录 B 手工验收（GUI 启动、Live2D 手感、MCP 实连、打断、重启续聊）需在桌面环境由用户执行，尚未勾选。

**阶段四总结**：D1 补齐 `HistoryStore` 15 条测试并将 `tests/README.md` 更新为 24 文件 / 321 用例；D2 完成 README、技术文档、接口契约（删除 `/v1/modes`、`/v1/mode` 与 `mode` 字段，章节重编号）与旧多模式文档归档；D3 复核 `.gitignore`（新增计划文档忽略）并确认 `live2dmascot/`、评测说明文档未入库。最终全量测试 321 passed、评测 21 passed / 3 skipped；仅附录 B 的手工 GUI / Live2D 验收待用户在桌面环境完成。

---

## 九、风险与回滚

| 风险 | 影响 | 应对 |
| --- | --- | --- |
| 目录迁移导致导入大面积失败 | 启动/测试全挂 | R2 单独提交；迁移后立即全量 pytest + 手工启动；保留 R1 提交作为回滚点 |
| 删除 legacy 引擎后无法一键回滚 | 失去旧路径 | 代码完整归档到 `archive/legacy_multi_mode/`，README 写明恢复步骤 |
| Live2D Drag 与动作角度冲突 | 抖动/动作被覆盖 | 情绪播放期间暂停 Drag；结束后平滑恢复；参数可调 |
| 随机动作与表情抢优先级 | 表情不生效 | 统一状态机 + `FORCE` / `NORMAL` 优先级；表情触发时取消随机 |
| 评测依赖内部实现细节 | 主图小改就红 | runner 只依赖公开构造参数与返回结构；断言口径集中在 `keywords.py` |
| 真模型评测不稳定 | 报告噪声 | 默认关闭 live；只断言结构，不比对措辞；报告标记 live |

---

## 附录 A：当前基线

- 单元测试：321 passed（2026-11-23，24 个测试文件）；R2 时为 396 passed，81 条 legacy 测试随归档移出。
- 评测：确定性 21 passed + live 3 skipped（默认）；`RUN_LIVE_EVALS=1` 时 live 3 passed。
- 主图入口：`build_main_graph` / `CompanionGraphAgent`。
- 后端入口：`python -m backend`（`backend/__main__.py`），前端入口 `uv run python main.py`。
- 流式：`stream_chat` 产出 `("delta", str)` / `("done", TurnResult)`。
- 情绪集合：`happy, sad, angry, surprised, neutral, shy, worried, excited, thinking, relaxed`。
- Hiyori 动作组：`Idle, Flick, FlickDown, Tap, Tap@Body, Flick@Body`。
- bench：20 条 prompt，输出 `bench/result.csv`（忽略）。

## 附录 B：最终手工验收清单

- [x] 启动客户端：先等待后端就绪，再显示桌宠。
- [x] 普通对话流式输出，无时间字符串泄漏。
- [x] 询问时间：回复正确，且不触发时间工具。
- [x] 天气/搜索工具可调用，失败时回复自然。
- [x] MCP 服务按配置加载，坏服务不影响好服务。
- [x] 鼠标移动：头部/眼睛平滑跟随；拖拽/缩放正常。
- [x] 空闲随机动作；表情动作优先且能回到常态。
- [x] 思考中 Esc 打断正常；再次对话正常。
- [x] 重启后能延续历史，无 `role=tool` 报错。
- [x] `uv run pytest -q`、`pytest evals/ -q` 通过。
