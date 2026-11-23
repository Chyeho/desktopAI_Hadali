# Agent 评测与项目重构开发记录

> 创建日期：2026-11-22
> 配套文档：`agent评测与项目重构执行文档.md`
> 记录方式：按阶段追加“问题 / 定位 / 方案 / 结果”；每阶段结束写总结与提交记录。
> 本文件本次不提交 git；

---

## 一、当前状态

| 阶段 | 小阶段 | 状态 | 提交 |
| --- | --- | --- | --- |
| 第一阶段 评测体系 | E1 骨架 + 路由/时间 | 已完成 | `test(eval): 搭建评测骨架与路由/时间回归` |
|  | E2 工具/容错/流式/记忆 | 已完成 | `test(eval): 补齐工具、容错、流式与记忆评测` |
|  | E3 实时冒烟与运维 | 已完成 | `docs(eval): 完善实时冒烟与评测说明` |
| 第二阶段 Live2D | L1 鼠标跟随 | 已完成 | `feat(client): Live2D 眼睛与身体随鼠标倾斜` |
|  | L2 随机动作与优先级 | 已完成 | `feat(client): Live2D 随机动作组与表情优先级` |
|  | L3 联调调参 | 已完成 | `docs(client): 补充 Live2D 行为状态机说明` |
| 第三阶段 目录与归档 | R1 解耦公共能力 | 已完成 | `refactor(agent): 抽出历史与回合类型并解除旧引擎依赖` |
|  | R2 收敛 backend | 已完成 | `refactor: 后端目录收敛为 backend 包` |
|  | R3 归档旧版多模式 | 已完成 | `refactor: 归档旧版多模式 agent`（`1111186`） |
|  | R4 根目录收尾 | 已完成 | `chore: 整理根目录与开发脚本位置`（`52b5e86`） |
| 第四阶段 收尾 | D1 测试 | 已完成 | `test: 更新目录调整后的测试与用例统计` |
|  | D2 文档 | 已完成 | `docs: 更新项目文档至最新结构` |
|  | D3 最终检查 | 已完成 | `chore: 收尾检查与 gitignore 补齐` |

基线：R3 后单元测试 **306 passed**，D1 补齐 HistoryStore 后 **321 passed**；评测体系第一/二/三阶段全部完成（确定性 21 条 + live 3 条）；目录已收敛为 `backend/` + `client/` + `utils/` + `evals/` + `bench/` + `archive/`。

---

## 二、调研结论（开发前）

### 2.1 `bench/` 是否有必要保留

**结论：保留。**

- `bench/run_bench.py` 会真实拉起后端、按 `bench/prompts.jsonl`（20 条）请求 `/v1/chat` SSE，统计 P50/P95 延迟、工具调用率、错误率，输出 `bench/result.csv`（已 gitignore）。
- 它衡量的是**性能与真实模型联通性**，需要 API Key 与网络；`evals/` 衡量的是**行为正确性**，默认确定性、无网络。两者互补，不重复。
- 目录调整阶段唯一需要改的是后端启动命令（`python -m server` → `python -m backend`）。

### 2.2 Live2D 参考实现要点

- `live2dmascot` 在鼠标移动/每帧时调用模型 `Drag` 实现视线与身体倾斜；动作通过 `StartRandomMotion(group, priority)` 调度，优先级区分空闲与主动动作。
- 本项目 `Live2DWidget` 已有 120fps 循环、情绪动作与过渡，但未调用 `Drag`，也没有随机动作调度。
- 现有启动动作使用 `StartMotion("TapBody", ...)`，而 Hiyori 动作组为 `Idle / Flick / FlickDown / Tap / Tap@Body / Flick@Body`，组名不匹配会静默失败，需一并修正。
- 只借鉴思路，不引入 `live2dmascot` 框架代码，也不提交该目录。

### 2.3 目录与旧代码耦合

- `HistoryStore`、`TurnResult` 定义在 `agent/chat_agent.py`，但被主图 runner、session、server 使用 → **必须先抽出**才能归档 legacy。
- 主图 `agent/graph/tooling.py` 仍通过 `ToolManager` 获取天气/搜索 → 归档 `tool_manager.py` 前需让主图自持工具注册表。
- `core/facade.py` 仍从 `MODE_REGISTRY[DEFAULT_MODE]` 取生成参数 → 需迁到图配置常量。
- `/v1/modes`、`/v1/mode`、`ModeRequest`、`ChatRequest.mode` 与客户端无调用关系，可整体移除。
- `resources.py` 未被代码引用（仅 README/文档提及），可在 R4 归档或删除。
- 根目录两份 LangGraph 阶段文档与 `docs/development_docs/` 存在内容重复，D2 统一归位。

### 2.4 `.gitignore`

- 已含 `live2dmascot/`。
- 本次已新增 `agent评测体系说明文档.md`，避免误提交。
- E1 再补 `evals/reports/`；D3 统一复核。

---

## 三、决策记录

| 编号 | 决策 | 说明 |
| --- | --- | --- |
| D1 | 评测默认确定性，live 冒烟单独标记 | 无 Key 也能跑，可进 CI |
| D2 | 用例声明式 dict + 统一 runner | 降新增用例成本 |
| D3 | 不改主图源码，依赖注入 | 避免测试分支污染产品代码 |
| D4 | Drag + 平滑；情绪动作期间暂停跟随 | 防抖动与角度冲突 |
| D5 | 随机动作 NORMAL，情绪 FORCE | 表情优先 |
| D6 | 后端收敛 `backend/`，`utils/` 留根共享 | 清晰且不破坏 client |
| D7 | legacy 多模式整体归档，移除 `AGENT_ENGINE` | 与单陪伴主图方向一致 |
| D8 | `bench/` 保留 | 性能基准与行为回归互补 |
| D9 | `expression_tester.py` 移 `scripts/`；`resources.py` 归档 | 根目录只留入口与数据 |

---

## 四、问题与解决方案

> 格式：现象 → 定位 → 方案 → 结果。开发过程中按阶段追加。

### 第一阶段（评测）

| 编号 | 现象 | 定位 | 方案 | 结果 |
| --- | --- | --- | --- | --- |
| E-01 | 流式回复末尾出现 ` [YYYY-MM-DD HH:MM]` 时间标记 | LangGraph `stream_mode=["messages","values"]` 在流末尾补发节点最终消息增量，runner 未过滤 | `utils/time_utils.py` 新增 `TimeMarkerStreamFilter`（跨 token 缓冲未完成标记）；`stream_chat` 先过滤时间再处理情绪标签 | 已修复，新增 5 条单测，全量 368 passed |

### 第二阶段（Live2D）

| 编号 | 现象 | 定位 | 方案 | 结果 |
| --- | --- | --- | --- | --- |
| L-01 | 启动动作组 `TapBody` 不生效 | 模型动作组为 `Tap@Body` | 移除无效启动动作，改为 `StartMotion("Idle", 0, NORMAL)`；空闲调度交给 L2 | 已修复 |
| L-02 | `model.Drag(x, y)` 的坐标口径不明 | 官方 glfw 示例传入与 `Resize` 同尺度的部件像素坐标；live2d-py 的 C++ 层自行归一化 | 纯函数内部用 [-1,1] 平滑，调用前 `denormalize_cursor` 还原为像素再 Drag | 已确认 |

### 第三阶段（目录与归档）

| 编号 | 现象 | 定位 | 方案 | 结果 |
| --- | --- | --- | --- | --- |
| R-01 | legacy 无法直接归档 | `HistoryStore` / `TurnResult` 被主图与 server 引用 | R1 抽出到 `agent/history.py`、`agent/turn.py` 并改写 8 处导入 | 已修复 |
| R-02 | 主图依赖 legacy 工具注册表 | `tooling.py` 使用 `ToolManager` | R1 改为主图自持 `BASE_TOOL_MAP` | 已修复 |
| R-03 | 图生成参数依赖模式注册表 | `facade.py` 读 `MODE_REGISTRY["emotion"]` | 新增 `agent/graph/config.py` 的 `GRAPH_MODEL_PARAMS` | 已修复 |
| R-04 | 归档的 legacy 测试仍会被 pytest 收集并导入已删除模块 | `testpaths=["tests"]` 默认不扫描 `archive/`，但显式传入路径或 rootdir 扫描仍可能命中 | `pyproject.toml` 增加 `norecursedirs = ["archive"]` | 已修复 |
| R-05 | 移除多模式后协议 `turn.start.mode` 字段何去何从 | 客户端按 `EVENT_MODEL_MAP` 反序列化，字段缺失不影响；但删字段需同步协议契约与测试 | 保留字段，`chat.py` 固定填 `AGENT_MODE="emotion"`，避免协议破坏性变更 | 已处理 |
| R-06 | 调试台移入 `scripts/` 后模型路径与预设路径失效 | 原实现用 `__file__` 相对定位，移动后指向 `scripts/Resources` | 改用 `utils.path_tool.get_abs_path`，运行时把项目根注入 `sys.path` | 已修复 |

### 第四阶段（收尾）

| 编号 | 现象 | 定位 | 方案 | 结果 |
| --- | --- | --- | --- | --- |
| D-01 | 归档 legacy 测试后 `HistoryStore` 失去独立测试覆盖 | 原 HistoryStore 用例位于 `test_chat_agent.py`，随归档移出；其代码仍被主图与 session 使用 | 新建 `tests/test_history.py`，迁入 15 条加载/保存/裁剪/替换/system prompt 用例 | 已补齐 |
| D-02 | 契约文档章节重编号易漏内部引用 | 删除多模式两节后，原 §6.6 / §7.1 / §8 等引用仍指向旧编号 | 全量重命名标题并同步改「见 §4.7 状态机」「§6 audio」「§5.1 提示」等引用 | 已修复 |

---

## 五、阶段总结

### 第一阶段总结

#### 完成情况（2026-11-23）

- 确定性用例 21 条 + live 冒烟 3 条；默认无网络、无 Key，live 按需启用。
- 统一 runner、声明式用例、JSON 报告（通过率 / 最慢 5 条）、MCP 隔离。
- 发现并修复 E-01 流式时间标记泄漏；报告失败信息包含断言字段与期望值。

#### E1（2026-11-23）

- 建立 `evals/` 骨架：`ScriptedLLM` 脚本化模型、`run_case` 统一执行器、JSON 报告（`evals/reports/latest.json`）、MCP 环境隔离。
- 7 条确定性用例通过：routing 4 条（含“倾诉提游戏”反例）、time 3 条（state 前缀/后缀、流式干净、时间工具隔离）。
- 发现并修复真实缺陷 E-01（流式时间标记泄漏），补充 5 条单元测试；全量 368 passed。
- 待 E3 补充：live 真实模型冒烟与运维说明。

#### E2（2026-11-23）

- 新增 14 条用例（tool 5 / resilience 3 / stream 4 / memory 2），评测总数 21 条。
- 本地假工具集中在 `evals/cases/tool_defs.py`；`run_memory_case` 支持跨实例恢复与残留 tool 消息过滤。
- 断言失败统一输出 `[字段] 期望=... 实际=... | case=...`，报告 `failure` 可直接定位。
- 验证：`pytest evals/ -q` → 21 passed；全量 `pytest -q` → 368 passed。

#### E3（2026-11-23）

- live 冒烟 3 条（闲聊 / 时间 / 工具），`RUN_LIVE_EVALS=1` + `.env` API_KEY 双条件，否则 skip；`history_file=None` 不写历史。
- 报告新增 `pass_rate` 与 `slowest`，live 以 `category=live` 标记；注册 pytest `live` marker。
- README 与 `evals/README.md` 写明 tests/evals/bench 分工与运行方式。
- 验证：默认 `pytest evals/` 21 passed / 3 skipped；实跑 live 3 passed in 49.11s；全量 368 passed。

### 第二阶段总结

#### L1（2026-11-23）

- 新增 `client/live2d_behavior.py` 纯函数模块：`clamp` / `normalize_cursor` / `denormalize_cursor` / `smooth_toward` / `pick_random_group`。
- `Live2DWidget` 每帧读取 `QCursor.pos()`，归一化后按 0.25 系数平滑（120fps 约 90ms 收敛），再还原像素调用 `model.Drag`；情绪动作与回常态过渡期间暂停跟随。
- 启动动作由无效的 `TapBody` 改为 `Idle`；启用 `setMouseTracking(True)`。
- 新增 `tests/test_live2d_behavior.py` 19 条用例；全量 `pytest -q` → 387 passed。
- 待 L3 手工验收跟随手感与拖拽/缩放兼容。

#### L2（2026-11-23）

- 状态机统一为 `idle / random_playing / emotion_playing / emotion_returning`，状态常量与迁移函数（`next_state_on_motion_end`）放在 `client/live2d_behavior.py`，Widget 只做驱动。
- 空闲 8~15s 随机动作：从 `GetMotionGroups()` 实际组中选择，`StartRandomMotion(group, NORMAL)`，排除上一次组；播放结束回空闲并重新计时。
- 表情动作进入 `emotion_playing`：取消随机计时、`FORCE` 覆盖、暂停 Drag；结束后进入 `emotion_returning` 平滑回常态，完成再恢复跟随与随机调度。
- `reset_emotion`（用户打断）直接回空闲、停止动作并重新计时。
- 新增 `random_interval_seconds` / `next_state_on_motion_end` 测试，`tests/test_live2d_behavior.py` 28 条；全量 `pytest -q` → 396 passed。

#### L3（2026-11-23）

- 参数定稿：跟随平滑 0.25、随机间隔 8~15s、回归过渡 1.5s；均为模块级常量。
- 性能：每帧仅新增 `QCursor.pos` + `mapFromGlobal` + C++ `Drag`，未新增像素读取。
- 文档：`docs/项目技术文档.md` 补充鼠标跟随、动作状态机与优先级、平滑回常态。
- 未采用 `live2dmascot` 框架代码；手工验收待桌面环境运行客户端。

### 第三阶段总结

#### R1（2026-11-23）

- 抽出 `agent/history.py`（`HistoryStore` / `HISTORY_DIR` / `HISTORY_WINDOW`）与 `agent/turn.py`（`TurnResult` / `ToolCallRecord`）；`chat_agent.py` 仅保留 legacy 引擎与 `parse_reply_json`。
- 导入改写 8 处：`graph/runner.py`、`core/session.py`、`server/services.py`、`core/tracing.py`、`core/facade.py`、`evals/runners/graph_runner.py`、`tests/test_chat_agent.py`、`tests/test_graph_flow.py`。
- `agent/graph/tooling.py` 自持 `BASE_TOOL_MAP`；`core/facade.py` graph 分支改用 `GRAPH_MODEL_PARAMS`，不再依赖 `MODE_REGISTRY`。
- 验证：定向 90 passed / 3 skipped；全量 396 passed。

#### R2（2026-11-23）

- `git mv`：`server→backend/api`、`agent→backend/agent`、`core→backend/core`、`protocol→backend/protocol`、`modelFactory→backend/model_factory`、`tools/common→backend/agent/tools`；新增 `backend/__init__.py`、`backend/__main__.py`。
- 43 个 Python 文件批量改写导入前缀，并同步字符串形式的 patch 目标；`client/server_launcher.py`、`bench/run_bench.py` 启动命令改为 `-m backend`。
- 踩坑：正则把 `"server.log"` 误改为 `"backend.api.log"`，已还原；`backend --help` 验证入口正常。
- 验证：全量 396 passed；`pytest evals -q` → 21 passed / 3 skipped；手工启动客户端确认 UI 链路。

#### R3（2026-11-23）

- 移除模式 API：`/v1/modes`、`/v1/mode`、`ModeRequest`、`ChatRequest.mode`；`meta.py` 只保留 `/v1/health`。
- `Services` 删除 `current_mode` / `list_modes` / `set_mode` 与 `_resolve_agent`，`chat` / `stream_chat` 去掉 mode 参数；`turn.start.mode` 固定为 `AGENT_MODE="emotion"`。
- `core/facade.py` 改 graph-only（删 `AGENT_ENGINE` / `resolve_engine` / legacy 分支 / `switch_mode`）；`core/session.py` 类型改为 `CompanionGraphAgent`。
- 归档 9 项到 `archive/legacy_multi_mode/`：`chatbot.py`、`chat_agent.py`、`tool_manager.py`、`mode_configs/`、4 个 legacy 测试、`ModeRequest` 摘录；补 `README.md`（原因 / 路径对照 / 恢复步骤）与 `docs/README.md`。
- 客户端 `SseTransport.send` 移除 mode 参数与 payload 字段；全仓已无模式相关调用。
- 测试调整：`test_facade_engine.py` 重写为 graph-only；`test_protocol.py` / `test_server_api.py` 删除模式用例；`pyproject.toml` 增加 `norecursedirs`。
- 验证：全量 `pytest -q` → 306 passed；`pytest evals -q` → 21 passed / 3 skipped；`python -m backend --help` 正常。

#### R4（2026-11-23）

- `git mv expression_tester.py → scripts/expression_tester.py`；改用 `get_abs_path` 定位 `Resources/...` 与 `expression_presets.json`，并把项目根注入 `sys.path`（`py_compile` 通过）。
- `resources.py` 确认无代码引用（仅 README / 技术文档 / tests README 提及），直接删除并同步文档。
- 根目录两份计划文档移入 `docs/development_docs/3_评测与重构/`，仍不提交。
- 清理 R2 后残留的 `tools/`（仅 `__pycache__`）与根 `__pycache__`；`git ls-files` 确认无 `.pyc` 入库。

### 第四阶段总结

#### D1（2026-11-23）

- 新增 `tests/test_history.py`（15 条），从归档的 `test_chat_agent.py` 迁出 `HistoryStore` 覆盖：加载容错、保存 roundtrip（含 ToolMessage）、裁剪窗口、`replace`、system prompt、`clear`。
- `tests/README.md` 全量重写：24 个文件 / 321 条用例、模块路径统一为 `backend/...`、移除 legacy 文件与环境说明、补充 `archive/` 排除与 `evals/` 分工。
- 验证：全量 `pytest -q` → 321 passed（53.62s）；`pytest evals -q` → 21 passed / 3 skipped；无网络、无 API Key。

#### D2（2026-11-23）

- README 定位改为单陪伴主图；结构段列出 `backend/`（api/agent/core/protocol/model_factory）、`archive/legacy_multi_mode/`、`evals/`、`bench/`、`scripts/`；环境变量表移除 `AGENT_ENGINE`。
- 技术文档删除引擎切换与 `mode_configs` 说明，改为 graph-only；工具来源改为 `BASE_TOOL_MAP`；单模式说明、记忆隔离、评测现状与未来子图扩展措辞同步。
- 契约文档删除 `/v1/modes`、`/v1/mode` 两节与 `ChatRequest.mode`，章节 5~14 顺延为 3~12，修正 `§4.7` / `§6` / `§5.1` 等内部引用；`turn.start.mode` 标注固定 `"emotion"`；示例与路径改 `backend/...`；新增 2026-11-23 变更记录。
- 旧多模式接口/引擎说明摘录到 `archive/legacy_multi_mode/docs/多模式接口与引擎说明.md`。
- 确认 `live2dmascot/` 与 `agent评测体系说明文档.md` 均被 `.gitignore` 覆盖、未被跟踪。

#### D3（2026-11-23）

- 复核 `.gitignore`：Python 缓存、虚拟环境、`.env*`、测试缓存、日志、`bench/result.csv`、`chat_history/`、`config/mcp_servers.json`、`live2dmascot/`、`agent评测体系说明文档.md`、`evals/reports/` 全覆盖。
- 新增两条计划/记录文档忽略规则，避免 `docs/development_docs/3_评测与重构/` 下计划文档被误提交。
- `git status` 仅剩预期修改；`git ls-files` 确认 `live2dmascot/` 与评测说明文档未入库。
- 最终验证：全量 `pytest -q` → 321 passed；`pytest evals -q` → 21 passed / 3 skipped。
- 附录 B 手工验收（GUI 启动、Live2D 跟随/随机动作、MCP 实连、Esc 打断、重启续聊）待用户在桌面环境完成，未代为勾选。

### 阶段四总结（收尾）

- 测试：新增 `test_history.py` 15 条，总数 24 文件 / 321 用例；`tests/README.md` 全量同步。
- 文档：README（结构 / 特性 / 命令）、`docs/项目技术文档.md`（单引擎 / 工具来源 / 记忆隔离 / 评测）、`docs/前后端接口JSON契约_v1.md`（删模式接口与字段、重编号、变更记录）、`archive/legacy_multi_mode/docs/` 摘录。
- 仓库：`.gitignore` 补齐计划文档；确认 `live2dmascot/`、`agent评测体系说明文档.md`、评测产物均未入库。
- 遗留：附录 B 的桌面手工验收未执行，代码与自动化验证均已通过。

---

## 六、提交记录

| 阶段 | 提交信息 | 状态 |
| --- | --- | --- |
| 基线 | `9c8287e docs: 重构运行指南并新增前置依赖与 MCP 配置小节` | 已完成 |
| E1 | `test(eval): 搭建评测骨架与路由/时间回归` | 已完成 |
| E2 | `test(eval): 补齐工具、容错、流式与记忆评测` | 已完成 |
| E3 | `docs(eval): 完善实时冒烟与评测说明` | 已完成 |
| L1 | `feat(client): Live2D 眼睛与身体随鼠标倾斜` | 已完成（`76d361d`） |
| L2 | `feat(client): Live2D 随机动作组与表情优先级` | 已完成（`583ac34`） |
| L3 | `docs(client): 补充 Live2D 行为状态机说明` | 已完成（`666ca7f`） |
| R1 | `refactor(agent): 抽出历史与回合类型并解除旧引擎依赖` | 已完成（`341f0e4`） |
| R2 | `refactor: 后端目录收敛为 backend 包` | 已完成（`6fcca86`） |
| R3 | `refactor: 归档旧版多模式 agent` | 已完成（`1111186`） |
| R4 | `chore: 整理根目录与开发脚本位置` | 已完成（`52b5e86`） |
| D1 | `test: 更新目录调整后的测试与用例统计` | 已完成（`c439ef4`） |
| D2 | `docs: 更新项目文档至最新结构` | 已完成（`8245859`） |
| D3 | `chore: 收尾检查与 gitignore 补齐` | 已完成（`0cfc6e5`） |
