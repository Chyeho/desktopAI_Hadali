# 单元测试说明

本项目使用 [pytest](https://docs.pytest.org/) 作为单元测试框架，所有测试代码**平铺**存放于 `tests/` 目录（一个模块对应一个 `test_*.py` 文件）。

测试围绕「无需 API Key / 网络 / GUI 即可运行」的原则设计：涉及外部依赖（大模型、网络请求、Live2D 渲染）的部分均通过 `unittest.mock` 打桩隔离，保证测试可重复、可在任意环境一键执行。

## 运行方式

### 1. 安装测试依赖

项目通过 `uv` 管理，pytest 已在 `[dependency-groups].dev` 中声明：

```bash
uv sync --all-groups
```

### 2. 运行全部测试

在项目根目录执行：

```bash
uv run pytest tests/ -v
```

### 3. 常用运行选项

```bash
# 只跑某个测试文件
uv run pytest tests/test_chat_agent.py -v

# 只跑某个测试类
uv run pytest tests/test_chat_agent.py::TestParseReplyJson -v

# 只跑某个测试方法
uv run pytest tests/test_chat_agent.py::TestParseReplyJson::test_standard_json -v

# 显示详细输出 + 失败时打印局部变量
uv run pytest tests/ -v --tb=short

# 生成覆盖率报告（需先 uv add --dev pytest-cov）
uv run pytest tests/ --cov --cov-report=term-missing
```

## 测试文件清单

共 **25 个测试文件、341 条用例**，覆盖纯逻辑模块与 LangGraph 陪伴主图。

| 测试文件 | 被测模块 | 用例数 | 覆盖要点 |
| --- | --- | ---: | --- |
| `test_path_tool.py` | `utils/path_tool.py` | 7 | `get_root_path` / `get_abs_path` 路径拼接与目录定位 |
| `test_config_handler.py` | `utils/config_handler.py` | 5 | yaml 配置加载、嵌套结构、缺失文件异常 |
| `test_prompt_loader.py` | `utils/prompt_loader.py` | 4 | 提示词文件读取、默认系统提示词加载 |
| `test_logger_handler.py` | `utils/logger_handler.py` | 6 | 日志器幂等创建、控制台/文件处理器、日志级别 |
| `test_time_utils.py` | `utils/time_utils.py` | 13 | `now_str` / `with_user_time` / `with_reply_time` / `strip_user_time` / `strip_reply_time` 与幂等性 |
| `test_expression_driver.py` | `agent/expression_driver.py` | 16 | 10 种情感标签集合、情感→动作映射、`drive_expression` 各分支 |
| `test_tool_manager.py` | `agent/tool_manager.py` | 11 | 全量工具注册表（无时间工具）、白名单过滤、未注册工具忽略 |
| `test_mode_configs.py` | `agent/mode_configs/` | 16 | `MODE_REGISTRY` 结构、emotion/office 配置字段完整性、默认模式 |
| `test_chat_agent.py` | `agent/chat_agent.py` | 39 | `HistoryStore`（加载/保存/裁剪/替换/system prompt）、`parse_reply_json`、`set_mode`、legacy 工具循环 |
| `test_facade_engine.py` | `core/facade.py` | 10 | `resolve_engine`（参数/环境变量/默认/非法值）、graph/legacy 引擎构造、`.env` 读取 |
| `test_graph_state.py` | `agent/graph/state.py` | 3 | `AgentState` 字段与 `add_messages` 归并 |
| `test_graph_perception.py` | `agent/graph/perception.py` | 10 | FakeJev 路由、0.7 阈值边界、关键词兜底、时间前缀剥离 |
| `test_graph_emotion.py` | `agent/graph/emotion.py` | 13 | 情绪标签解析、跨 token 过滤、非法标签回退 |
| `test_graph_tooling.py` | `agent/graph/tooling.py` | 17 | 工具装配、时间工具剔除、MCP 配置读取/合并/失败降级 |
| `test_graph_flow.py` | `agent/graph/` | 17 | 主图 chat/game 分支、工具循环、流式 token、多轮与 JSON 镜像、时间注入 |
| `test_weather.py` | `tools/common/weather.py` | 17 | 天气/风向中文映射、`get_weather` mock 网络请求的成功/回退/异常分支 |
| `test_web_search.py` | `tools/common/web_search.py` | 13 | `_strip_tags`、`web_search` mock Bing 搜索的成功/无结果/异常分支 |
| `test_chatbot.py` | `chatbot.py` | 15 | `_load_env`、`init_api_key*`（mock 工厂）、`chat_with_model` / `switch_mode` |
| `test_tts.py` | `chatbotTTS.py` | 21 | `_clean_text`、配置默认值、`speak` 空文本、`_StreamPlayer` 会话丢弃 |
| `test_factory.py` | `modelFactory/factory.py` | 9 | `ChatModelFactory` 参数传递、`EmbeddingModelFactory` 桩、抽象基类 |
| `test_server_api.py` | `server/` | 25 | 健康检查、模式接口、SSE 事件顺序、graph 流式与 legacy 一次性降级、错误映射、鉴权 |
| `test_session.py` | `core/session.py` | 12 | session_id 校验、agent 惰性创建、按会话锁隔离 |
| `test_protocol.py` | `protocol/` | 23 | 请求模型校验、SSE 事件字段与序列化 |
| `test_transport.py` | `client/transport/` | 13 | SSE 解析、事件分发、错误与中断 |
| `test_tracing.py` | `core/tracing.py` | 6 | 回合指标统计与 JSONL 落盘 |

## 测试策略说明

### 隔离真实数据

- **对话历史隔离**：`test_chat_agent.py` 中的 `patched_history` fixture 通过 `monkeypatch` 将 `HistoryStore` 默认路径重定向到 `tmp_path` 临时文件，避免读写真实的 `chat_history/default.json`，防止污染用户对话记忆。
- **图引擎缓存**：`test_graph_tooling.py` 每个用例前后清空 `_agent_tools` 缓存，并把 `MCP_CONFIG_PATH` 指向 `tmp_path` 下不存在的文件，保证不读取本地真实 MCP 配置、不发起网络请求。
- **全局 Agent 清理**：`test_chatbot.py` 中每个测试用例结束后将 `chatbot._agent` 置为 `None`，避免全局状态在测试间串扰。

### Mock 外部依赖

| 外部依赖 | Mock 方式 |
| --- | --- |
| 大模型（ChatOpenAI） | `test_chat_agent.py` 用 `_FakeFactory` + `MagicMock`；`test_graph_flow.py` 用 `_FakeLLM` / `GenericFakeChatModel`；`test_factory.py` 用 `patch("modelFactory.factory.ChatOpenAI")` |
| 网络请求（urllib） | `test_weather.py` / `test_web_search.py` 用 `patch("urllib.request.urlopen")` 返回构造的假响应 |
| MCP 客户端 | `test_graph_tooling.py` 用假客户端替换 `MultiServerMCPClient`，覆盖正常返回、构造异常、适配器缺失 |
| Live2D Widget | `test_expression_driver.py` 用 `MagicMock()` 模拟 `request_play_motion.emit` 信号 |
| 模块级配置加载 | `test_chatbot.py` 用 `patch("chatbot.ChatModelFactory")` 拦截工厂实例化 |

### 不参与测试的模块

以下模块强依赖 GUI / 硬件 / 模型资源，不纳入单元测试：

- `chatbotUI.py` — 依赖 PySide6 + OpenGL + Live2D 运行时，属 UI 层，适合手动 / E2E 测试
- `client/ui/` — 聊天框增量显示与窗口事件处理，随 UI 手工验收
- `main.py` — 程序入口，整合 GUI 启动
- `expression_tester.py` — Live2D 表情调试台，需 GUI
- `resources.py` — 仅路径常量，无逻辑分支

## 测试结果

```
341 passed in 23.10s
```

环境：Windows + Python 3.13 + uv 管理依赖。

```
========================= test session starts =========================
platform win32 -- Python 3.13.x, pytest-9.x, pluggy-1.x
rootdir: .../desktopAI_Hadali
configfile: pyproject.toml: [tool.pytest.ini_options]
collected 341 items

tests/test_chat_agent.py ....................................... [11%]
tests/test_chatbot.py ...............                              [16%]
tests/test_config_handler.py .....                                 [17%]
tests/test_expression_driver.py ................                   [22%]
tests/test_facade_engine.py ..........                             [25%]
tests/test_factory.py .........                                    [27%]
tests/test_graph_emotion.py .............                          [31%]
tests/test_graph_flow.py .................                         [36%]
tests/test_graph_perception.py ..........                          [39%]
tests/test_graph_state.py ...                                      [40%]
tests/test_graph_tooling.py .................                      [45%]
tests/test_logger_handler.py ......                                [47%]
tests/test_mode_configs.py ................                        [51%]
tests/test_path_tool.py .......                                    [53%]
tests/test_prompt_loader.py ....                                   [55%]
tests/test_protocol.py .......................                     [61%]
tests/test_server_api.py .........................                 [69%]
tests/test_session.py ............                                 [72%]
tests/test_time_utils.py .............                             [76%]
tests/test_tool_manager.py ...........                             [79%]
tests/test_tracing.py ......                                       [81%]
tests/test_transport.py .............                              [85%]
tests/test_tts.py .....................                            [91%]
tests/test_weather.py .................                            [96%]
tests/test_web_search.py .............                             [100%]

======================= 341 passed in 23.10s =======================
```

## 新增测试指引

新增模块时，遵循现有平铺约定：

1. 在 `tests/` 下新建 `test_<模块名>.py`；
2. 纯逻辑直接测试，外部依赖用 `unittest.mock` 打桩；
3. 涉及文件 I/O 的用 `tmp_path` fixture 隔离；
4. 涉及全局状态的用 `monkeypatch` 在测试后还原；
5. 运行 `uv run pytest tests/ -v` 确认通过。
