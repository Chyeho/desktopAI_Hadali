# 行为评测（evals）

面向 LangGraph 情感陪伴主图的**行为回归**，与 `tests/` 的单元测试、`bench/` 的性能基准互补。

| 目录 | 定位 | 依赖 |
| --- | --- | --- |
| `tests/` | 模块/单元测试，覆盖纯逻辑与接口细节 | 无网络 |
| `evals/` | 给定输入 → 路由 / 工具 / 时间 / 容错 / 流式 / 记忆 | 默认无网络、无 API Key |
| `bench/` | 真实模型批量请求，统计延迟与工具率 | 需 API Key 与网络 |

## 运行

```powershell
# 全部确定性评测
uv run pytest evals/ -q

# 按指标类别
uv run pytest evals/test_routing.py -q
uv run pytest evals/test_time_injection.py -q
uv run pytest evals/test_tool_calls.py -q
uv run pytest evals/test_resilience.py -q
uv run pytest evals/test_stream_contract.py -q
uv run pytest evals/test_memory.py -q

# 单条用例
uv run pytest evals/ -q -k routing_game_confide_02
```

默认运行是**确定性回归**：不需要 API Key 与网络，`evals/live` 会被跳过。
运行后生成 `evals/reports/latest.json`（已 gitignore）：包含 id、category、outcome、duration_ms、failure，
以及汇总（总数、通过率 `pass_rate`、按类别统计、最慢 5 条 `slowest`）。

### 实时冒烟（按需）

```powershell
# 需要 .env 中配置 API_KEY；未设置时自动 skip
$env:RUN_LIVE_EVALS = "1"
uv run pytest evals/live -m live -q
```

live 用例只断言结构（回复非空、无情绪标签/时间标记泄漏、emotion 合法），不断言具体措辞；
报告中以 `category=live` 区分。`bench/` 负责批量性能基准（延迟/工具率），live 只做最小连通性冒烟。

## 目录

```text
evals/
├── conftest.py            # 隔离 MCP、收集报告
├── keywords.py            # 游戏拒绝词 / 失败解释词 / 禁用词 / 时间正则
├── cases/                 # 声明式用例（每个指标一个文件）
│   ├── routing_cases.py   # M2 路由
│   ├── time_cases.py      # M3 时间
│   ├── tool_cases.py      # M1 工具
│   ├── resilience_cases.py# M4 容错
│   ├── stream_cases.py    # M5 流式契约
│   ├── memory_cases.py    # M6 记忆
│   └── tool_defs.py       # 本地假工具（不联网）
├── runners/graph_runner.py# 脚本化 LLM + 主图运行 + 统一断言 + 记忆用例执行器
├── reporting.py           # JSON 报告
├── test_routing.py        # M2 路由
├── test_time_injection.py # M3 时间注入
├── test_tool_calls.py     # M1 工具
├── test_resilience.py     # M4 容错
├── test_stream_contract.py# M5 流式契约
├── test_memory.py         # M6 记忆
├── live/
│   └── test_live_smoke.py # E3 实时冒烟（RUN_LIVE_EVALS=1）
└── reports/               # 运行产物（gitignore）
```

## 用例格式

```python
{
    "id": "routing_game_explicit_01",
    "category": "routing",              # routing / time / tool / resilience / stream / memory
    "description": "明确请求来一局五子棋 → game",
    "input": "陪我玩一局五子棋吧",
    "scripted_reply": "我还在学习下棋呢，暂时还不能陪你玩。",
    "streaming": False,                 # True 时走 stream_chat，验证增量
    "use_agent_tools": False,           # True 时注入真实工具列表（MCP 已被隔离）
    "expect": {
        "route": "game",
        "final_contains_any": ("还在学", "暂时"),
        "no_tool": ["get_current_time"],
    },
}
```

可用断言：`route` / `emotion` / `emotion_valid` / `human_prefix` / `ai_suffix` /
`tool_name` / `tool_message_count` / `tool_content_contains` / `tool_status_error` /
`no_tool` / `tool_not_called` / `bound_tools_contain` / `bound_tools_exact` /
`no_tool_messages` / `final_contains_any` / `forbid_in_final` / `deltas_clean` /
`deltas_join_equals_reply` / `deltas_no_emotion_tag` / `final_clean` / `no_tech_terms`。

记忆用例（`test_memory.py`）使用 `run_memory_case(case, history_file)`，额外支持：
`restored_contains_all` / `restored_no_tool_messages` / `restored_no_tool_calls`；
用例字段为 `first_turns` / `first_steps` / `second_steps`，或用 `seed_history` 直接构造历史文件。

约定：

- 用例只放数据，关键词引用 `evals/keywords.py`；
- 每个用例独立 `thread_id`，不写 `chat_history/`；
- 确定性用例的 LLM 由 `ScriptedLLM` 提供，工具通过参数注入，不访问网络；
- 不修改主图源码，不为评测加测试分支。

## 指标

- M2 路由：游戏意图进入 `game`，倾诉/模糊提到游戏仍为 `chat`（核心反例必测）。
- M3 时间：state 前缀/后缀、UI 增量与最终回复无时间标记、时间工具不在白名单且不被调用。
- M1 工具：注入本地假 `get_weather` / `web_search`，断言 ToolMessage 名称与结果片段，覆盖成功与空结果。
- M4 容错：工具抛异常/返回错误文本时图不中断、ToolMessage 标记 error、最终回复人格化且无技术字样。
- M5 流式契约：增量拼接等于 `done.reply`，无情绪标签与时间标记，`emotion` 合法（非法回退 neutral）。
- M6 记忆：跨实例从 JSON 恢复历史，恢复时剥离 tool 中间消息（回归 role=tool 非法请求）。
- live：真实模型的闲聊 / 时间 / 工具三条冒烟，仅校验结构与过滤契约。

## 新增一类指标

1. 在 `evals/cases/` 新建 `<指标>_cases.py`，用例只放数据（`id / category / description / input / scripted_steps / tools / expect`）；
2. 在 `evals/test_<指标>.py` 里用 `parametrize` 调 `run_case` + `assert_expect`；
3. 需要新断言时，在 `evals/runners/graph_runner.py` 的 `assert_expect` 增加字段，并通过 `_fail` 输出期望值；
4. 同步更新本 README 的断言清单与指标说明。
