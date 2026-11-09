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

- [ ] 代码完成
- [ ] `pytest -q` 全绿
- [ ] 验收项逐条通过
- [ ] commit

### 问题记录

| 编号 | 问题描述 | 解决方案 | 结果 |
|---|---|---|---|
| P1-1 | 直接删除 `agent/chat_agent.py` 的 `live2d_model` 与 `drive_expression` 会让 P3 之前的旧 UI 失去表情动画，违反“不改变现有功能” | 把“情感 → 动作组”迁到 `client/emotion_map.py`；根 `chatbot.py` 保留为**过渡适配器**：调用 core 拿到 `TurnResult` 后，若旧 UI 传入 `live2d_model`，再由适配器调 `drive_expression`。`core/` 不 import client | 待验证 |
| P1-2 | `tests/test_chatbot.py` 用 `patch("chatbot.ChatModelFactory")` 与 `chatbot._agent` 依赖模块级全局；若把 `chatbot.py` 直接替换成 `sys.modules = core.facade`，适配器与 facade 的全局状态会分裂 | 放弃 `sys.modules` 替换；`chatbot.py` 保留自己的 `_agent` / `last_partial_reply` / `ChatModelFactory`，初始化时把 `ChatModelFactory` 作为 `factory_cls` 传给 `core.facade.create_agent()`。这样 patch 命中适配器，core 仍可独立测试 | 待验证 |
| P1-3 | `ChatAgent.chat()` 返回结构化 `TurnResult` 后，现有测试用 `result["emotion"]` / `result["reply"]` 下标访问 | 用 `TypedDict` 定义 `TurnResult`（运行时就是 dict），既满足结构化要求，又保持 14 个测试零断言改动 | 待验证 |

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
