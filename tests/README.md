# 单元测试说明

本项目使用 [pytest](https://docs.pytest.org/) 作为单元测试框架，所有测试代码**平铺**存放于 `tests/` 目录（一个模块对应一个 `test_*.py` 文件）。

测试围绕「无需 API Key / 网络 / GUI 即可运行」的原则设计：涉及外部依赖（大模型、网络请求、Live2D 渲染）的部分均通过 `unittest.mock` 打桩隔离，保证测试可重复、可在任意环境一键执行。行为级回归（路由 / 工具 / 时间 / 流式 / 记忆）在 `evals/`，性能基准在 `bench/`。

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
uv run pytest tests/test_history.py -v

# 只跑某个测试类
uv run pytest tests/test_graph_flow.py::TestGraphChat -v

# 只跑某个测试方法
uv run pytest tests/test_protocol.py::TestChatRequest -v

# 显示详细输出 + 失败时打印局部变量
uv run pytest tests/ -v --tb=short

# 生成覆盖率报告（需先 uv add --dev pytest-cov）
uv run pytest tests/ --cov --cov-report=term-missing
```

归档目录 `archive/` 已通过 `pyproject.toml` 的 `norecursedirs` 排除，不参与收集与运行。

## 测试文件清单

共 **24 个测试文件、321 条用例**，覆盖纯逻辑模块、后端 API 与 LangGraph 陪伴主图。

| 测试文件 | 被测模块 | 用例数 | 覆盖要点 |
| --- | --- | ---: | --- |
| `test_path_tool.py` | `utils/path_tool.py` | 7 | `get_root_path` / `get_abs_path` 路径拼接与目录定位 |
| `test_config_handler.py` | `utils/config_handler.py` | 6 | yaml 配置加载、嵌套结构、缺失文件异常 |
| `test_prompt_loader.py` | `utils/prompt_loader.py` | 6 | 提示词文件读取、配置键加载、默认系统提示词与陪伴主图提示词 |
| `test_env_utils.py` | `utils/env_utils.py` | 5 | `.env` 解析、注释/引号、缺失文件抛错与 `missing_ok` 降级 |
| `test_logger_handler.py` | `utils/logger_handler.py` | 6 | 日志器幂等创建、控制台/文件处理器、日志级别 |
| `test_time_utils.py` | `utils/time_utils.py` | 23 | `now_str` / `with_user_time` / `with_reply_time` / 前后缀剥离 / 任意位置时间标记清除 / `TimeMarkerStreamFilter` 跨块去标记与幂等性 |
| `test_expression_driver.py` | `backend/agent/expression_driver.py` | 16 | 10 种情感标签集合、情感→动作映射、`drive_expression` 各分支 |
| `test_history.py` | `backend/agent/history.py` | 15 | `HistoryStore` 加载容错 / 保存 roundtrip / 裁剪窗口 / 整体替换 / system prompt 管理 |
| `test_facade_engine.py` | `backend/core/facade.py` | 5 | graph-only 构造、图生成参数、`.env` 读取、未初始化 agent 保护 |
| `test_graph_state.py` | `backend/agent/graph/state.py` | 3 | `AgentState` 字段与 `add_messages` 归并 |
| `test_graph_perception.py` | `backend/agent/graph/perception.py` | 10 | FakeJev 路由、0.7 阈值边界、关键词兜底、时间前缀剥离 |
| `test_graph_emotion.py` | `backend/agent/graph/emotion.py` | 13 | 情绪标签解析、跨 token 过滤、非法标签回退 |
| `test_graph_tooling.py` | `backend/agent/graph/tooling.py` | 23 | 工具装配、时间工具剔除、MCP 配置读取（含 BOM）/逐服务加载/单服务失败与超时隔离/超时覆盖、异步工具同步包装 |
| `test_graph_flow.py` | `backend/agent/graph/` | 20 | 主图 chat/game 分支、工具循环、流式 token、多轮与 JSON 镜像、时间注入与时间戳清除、工具中间消息剥离 |
| `test_weather.py` | `backend/agent/tools/weather.py` | 17 | 天气/风向中文映射、`get_weather` mock 网络请求的成功/回退/异常分支 |
| `test_web_search.py` | `backend/agent/tools/web_search.py` | 13 | `_strip_tags`、`web_search` mock Bing 搜索的成功/无结果/异常分支 |
| `test_live2d_behavior.py` | `client/live2d_behavior.py` | 28 | 鼠标归一化/限幅、平滑收敛、状态机迁移、随机动作间隔与去重 |
| `test_tts.py` | `chatbotTTS.py` | 21 | `_clean_text`、配置默认值、`speak` 空文本、`_StreamPlayer` 会话丢弃 |
| `test_factory.py` | `backend/model_factory/factory.py` | 9 | `ChatModelFactory` 参数传递、`EmbeddingModelFactory` 桩、抽象基类 |
| `test_server_api.py` | `backend/api/` | 22 | 健康检查、SSE 事件顺序、流式与一次性降级、错误映射、鉴权 |
| `test_session.py` | `backend/core/session.py` | 12 | session_id 校验、agent 惰性创建、按会话锁隔离 |
| `test_protocol.py` | `backend/protocol/` | 22 | 请求模型校验、SSE 事件字段与序列化 |
| `test_transport.py` | `client/transport/` | 13 | SSE 解析、事件分发、错误与中断 |
| `test_tracing.py` | `backend/core/tracing.py` | 6 | 回合指标统计与 JSONL 落盘 |

## 测试策略说明

### 隔离真实数据

- **对话历史隔离**：`test_history.py` / `test_graph_flow.py` / `evals/` 均使用 `tmp_path` 临时历史文件，不读写真实的 `chat_history/`。
- **图引擎缓存**：`test_graph_tooling.py` 每个用例前后清空 `_agent_tools` 缓存，并把 `MCP_CONFIG_PATH` 指向 `tmp_path` 下不存在的文件，保证不读取本地真实 MCP 配置、不发起网络请求。
- **归档代码隔离**：`archive/legacy_multi_mode/` 通过 `norecursedirs = ["archive"]` 排除，避免旧模块导入失败影响测试。

### Mock 外部依赖

| 外部依赖 | Mock 方式 |
| --- | --- |
| 大模型（ChatOpenAI） | `test_facade_engine.py` 用 `_FakeFactory` + `_FakeLLM`；`test_graph_flow.py` 用 `_FakeLLM` / `GenericFakeChatModel`；`test_factory.py` 用 `patch("backend.model_factory.factory.ChatOpenAI")` |
| 网络请求（urllib） | `test_weather.py` / `test_web_search.py` 用 `patch("urllib.request.urlopen")` 返回构造的假响应 |
| MCP 客户端 | `test_graph_tooling.py` 用假客户端替换 `MultiServerMCPClient`，覆盖正常返回、构造异常、适配器缺失 |
| Live2D Widget | `test_expression_driver.py` 用 `MagicMock()` 模拟 `request_play_motion.emit` 信号 |

### 不参与测试的模块

以下模块强依赖 GUI / 硬件 / 模型资源，不纳入单元测试：

- `chatbotUI.py` — 依赖 PySide6 + OpenGL + Live2D 运行时，属 UI 层，适合手动 / E2E 测试
- `client/ui/` — 聊天框增量显示与窗口事件处理，随 UI 手工验收
- `main.py` — 程序入口，整合 GUI 启动
- `scripts/expression_tester.py` — Live2D 表情调试台，需 GUI

## 测试结果

```
321 passed in 53.62s
```

环境：Windows + Python 3.13 + uv 管理依赖。

```
========================= test session starts =========================
platform win32 -- Python 3.13.x, pytest-9.x, pluggy-1.x
rootdir: .../desktopAI_Hadali
configfile: pyproject.toml: [tool.pytest.ini_options]
collected 321 items

tests/test_config_handler.py ......                                [ 2%]
tests/test_env_utils.py .....                                      [ 3%]
tests/test_expression_driver.py ................                   [ 8%]
tests/test_facade_engine.py .....                                  [10%]
tests/test_factory.py .........                                    [13%]
tests/test_graph_emotion.py .............                          [17%]
tests/test_graph_flow.py ....................                      [23%]
tests/test_graph_perception.py ..........                          [26%]
tests/test_graph_state.py ...                                      [27%]
tests/test_graph_tooling.py .......................                [34%]
tests/test_history.py ...............                              [39%]
tests/test_live2d_behavior.py ............................         [48%]
tests/test_logger_handler.py ......                                [50%]
tests/test_path_tool.py .......                                    [52%]
tests/test_prompt_loader.py ......                                 [54%]
tests/test_protocol.py ......................                     [60%]
tests/test_server_api.py ......................                     [67%]
tests/test_session.py ............                                 [71%]
tests/test_time_utils.py .......................                   [78%]
tests/test_tracing.py ......                                       [80%]
tests/test_transport.py .............                              [84%]
tests/test_tts.py .....................                            [90%]
tests/test_weather.py .................                            [96%]
tests/test_web_search.py .............                             [100%]

======================= 321 passed in 53.62s =======================
```

## 新增测试指引

新增模块时，遵循现有平铺约定：

1. 在 `tests/` 下新建 `test_<模块名>.py`；
2. 纯逻辑直接测试，外部依赖用 `unittest.mock` 打桩；
3. 涉及文件 I/O 的用 `tmp_path` fixture 隔离；
4. 涉及全局状态的用 `monkeypatch` 在测试后还原；
5. 运行 `uv run pytest tests/ -v` 确认通过。
