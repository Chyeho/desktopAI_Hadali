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

（待开始）

---

## P3：client

（待开始）

---

## P4：打磨与评测

（待开始）
