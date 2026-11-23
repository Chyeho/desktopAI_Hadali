# 旧版多模式 Agent 归档（legacy_multi_mode）

## 归档原因

项目已统一为 **LangGraph 情感陪伴主图**（单引擎、单模式）。原多模式实现
（`emotion` / `office` 切换、`ChatAgent` 引擎、`AGENT_ENGINE` 回滚开关、
`/v1/modes` 与 `/v1/mode` 接口）全部下线，代码保留在此目录仅供追溯与必要时恢复。

## 原路径对照

| 归档路径 | 原仓库路径 |
| --- | --- |
| `chatbot.py` | `chatbot.py` |
| `agent/chat_agent.py` | `backend/agent/chat_agent.py` |
| `agent/tool_manager.py` | `backend/agent/tool_manager.py` |
| `agent/mode_configs/` | `backend/agent/mode_configs/` |
| `protocol/mode_request.py` | `backend/protocol/requests.py` 中的 `ModeRequest` 摘录 |
| `tests/test_chatbot.py` | `tests/test_chatbot.py` |
| `tests/test_chat_agent.py` | `tests/test_chat_agent.py` |
| `tests/test_mode_configs.py` | `tests/test_mode_configs.py` |
| `tests/test_tool_manager.py` | `tests/test_tool_manager.py` |

## 归档时同步发生的改动

- `backend/api/routes/meta.py` 删除 `/v1/modes`、`/v1/mode`，仅保留 `/v1/health`。
- `backend/protocol/requests.py` 删除 `ModeRequest` 与 `ChatRequest.mode`。
- `backend/api/services.py` 删除 `current_mode` / `list_modes` / `set_mode`。
- `backend/core/facade.py` 改为 graph-only，移除 `AGENT_ENGINE` / `resolve_engine` /
  legacy 分支 / `switch_mode`。
- `backend/core/session.py` 的 agent 类型改为 `CompanionGraphAgent`。
- `pyproject.toml` 增加 `norecursedirs = ["archive"]`，归档测试不会被收集。

## 恢复步骤（非必要不建议）

1. 将 `agent/chat_agent.py`、`agent/tool_manager.py`、`agent/mode_configs/`
   移回 `backend/agent/`。
2. 将 `chatbot.py` 移回仓库根目录。
3. 将 `tests/*.py` 移回 `tests/`。
4. 恢复 `ModeRequest` / `ChatRequest.mode`、`/v1/modes`、`/v1/mode` 路由与
   `Services` 的模式方法。
5. 恢复 `core/facade.py` 的 `resolve_engine` 与 legacy 分支（可参考 git 历史
   提交 `refactor: 归档旧版多模式 agent` 的父提交）。
6. 从 `pyproject.toml` 移除 `norecursedirs`（如仍保留 archive 目录可保留该配置）。

## 注意

- 归档代码不参与任何测试与运行路径，**不要**在活跃代码中导入本目录模块。
- 本目录中的文件可能引用了已删除的模块或接口，直接运行会失败，属预期。
