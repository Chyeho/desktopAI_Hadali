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

# 单条用例
uv run pytest evals/ -q -k routing_game_confide_02
```

运行后生成 `evals/reports/latest.json`（已 gitignore）：包含 id、category、outcome、duration_ms、failure，以及按类别汇总。

## 目录

```text
evals/
├── conftest.py            # 隔离 MCP、收集报告
├── keywords.py            # 游戏拒绝词 / 失败解释词 / 禁用词 / 时间正则
├── cases/                 # 声明式用例（每个指标一个文件）
├── runners/graph_runner.py# 脚本化 LLM + 主图运行 + 统一断言
├── reporting.py           # JSON 报告
├── test_routing.py        # M2 路由
├── test_time_injection.py # M3 时间注入
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

可用断言：`route` / `emotion` / `human_prefix` / `ai_suffix` / `tool_name` /
`tool_content_contains` / `no_tool` / `no_tool_messages` / `final_contains_any` /
`forbid_in_final` / `deltas_clean` / `final_clean` / `no_tech_terms`。

约定：

- 用例只放数据，关键词引用 `evals/keywords.py`；
- 每个用例独立 `thread_id`，不写 `chat_history/`；
- 确定性用例的 LLM 由 `ScriptedLLM` 提供，工具通过参数注入，不访问网络；
- 不修改主图源码，不为评测加测试分支。

## 指标

- M2 路由：游戏意图进入 `game`，倾诉/模糊提到游戏仍为 `chat`（核心反例必测）。
- M3 时间：state 前缀/后缀、UI 增量与最终回复无时间标记、时间工具不在白名单且不被调用。

后续阶段补充 M1 工具、M4 容错、M5 流式契约、M6 记忆，以及 `live` 真实模型冒烟。
