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

共 **14 个测试文件、186 条用例**，覆盖项目所有纯逻辑模块。

| 测试文件 | 被测模块 | 用例数 | 覆盖要点 |
| --- | --- | ---: | --- |
| `test_path_tool.py` | `utils/path_tool.py` | 7 | `get_root_path` / `get_abs_path` 路径拼接与目录定位 |
| `test_config_handler.py` | `utils/config_handler.py` | 5 | yaml 配置加载、嵌套结构、缺失文件异常 |
| `test_prompt_loader.py` | `utils/prompt_loader.py` | 4 | 提示词文件读取、默认系统提示词加载 |
| `test_logger_handler.py` | `utils/logger_handler.py` | 6 | 日志器幂等创建、控制台/文件处理器、日志级别 |
| `test_expression_driver.py` | `agent/expression_driver.py` | 16 | 10 种情感标签集合、情感→动作映射、`drive_expression` 各分支（无 widget / 未知情感 / 信号 emit） |
| `test_tool_manager.py` | `agent/tool_manager.py` | 10 | 全量工具注册表、白名单过滤、未注册工具忽略 |
| `test_mode_configs.py` | `agent/mode_configs/` | 15 | `MODE_REGISTRY` 结构、emotion/office 模式配置字段完整性、默认模式 |
| `test_chat_agent.py` | `agent/chat_agent.py` | 38 | `HistoryStore`（加载/保存/裁剪/system prompt/异常容错）、`parse_reply_json`（JSON / markdown 代码块 / 夹带文字 / 空值 / 非法 JSON 回退）、`ChatAgent.set_mode`（mock 工厂）、`ChatAgent.chat`（工具调用循环 / 未知工具 / 最大轮数） |
| `test_time_utils.py` | `utils/time_utils.py` | 13 | `now_str` / `with_user_time` / `with_reply_time` / `strip_user_time` / `strip_reply_time` 与幂等性 |
| `test_weather.py` | `tools/common/weather.py` | 17 | 天气/风向中文映射、`get_weather` mock 网络请求的成功/回退/异常分支 |
| `test_web_search.py` | `tools/common/web_search.py` | 13 | `_strip_tags`（去标签 / 反转义实体）、`web_search` mock Bing 搜索的成功/无结果/异常分支 |
| `test_chatbot.py` | `chatbot.py` | 15 | `_load_env`（注释/空行/引号/缺失）、`init_api_key` / `init_api_key_from_env`（mock 工厂）、`chat_with_model` / `switch_mode`（mock agent） |
| `test_tts.py` | `chatbotTTS.py` | 21 | `_clean_text`（去 emoji / markdown 符号 / 保留标点）、配置默认值、`speak` 空文本不启动线程、`_StreamPlayer` 会话丢弃逻辑 |
| `test_factory.py` | `modelFactory/factory.py` | 9 | `ChatModelFactory`（mock ChatOpenAI，验证连接参数与生成参数传递）、`EmbeddingModelFactory` 桩抛 `NotImplementedError`、抽象基类不可实例化 |

## 测试策略说明

### 隔离真实数据

- **对话历史隔离**：`test_chat_agent.py` 中的 `patched_history` fixture 通过 `monkeypatch` 将 `HistoryStore` 默认路径重定向到 `tmp_path` 临时文件，避免读写真实的 `chat_history/default.json`，防止污染用户对话记忆。
- **全局 Agent 清理**：`test_chatbot.py` 中每个测试用例结束后将 `chatbot._agent` 置为 `None`，避免全局状态在测试间串扰。

### Mock 外部依赖

| 外部依赖 | Mock 方式 |
| --- | --- |
| 大模型（ChatOpenAI） | `test_chat_agent.py` 用 `_FakeFactory` + `MagicMock` 模拟 `llm.invoke` / `bind_tools`；`test_factory.py` 用 `patch("modelFactory.factory.ChatOpenAI")` |
| 网络请求（urllib） | `test_weather.py` / `test_web_search.py` 用 `patch("urllib.request.urlopen")` 返回构造的假响应 |
| Live2D Widget | `test_expression_driver.py` 用 `MagicMock()` 模拟 `request_play_motion.emit` 信号 |
| 模块级配置加载 | `test_chatbot.py` 用 `patch("chatbot.ChatModelFactory")` 拦截工厂实例化 |

### 不参与测试的模块

以下模块强依赖 GUI / 硬件 / 模型资源，不纳入单元测试：

- `chatbotUI.py` — 依赖 PySide6 + OpenGL + Live2D 运行时，属 UI 层，适合手动 / E2E 测试
- `main.py` — 程序入口，整合 GUI 启动
- `expression_tester.py` — Live2D 表情调试台，需 GUI
- `resources.py` — 仅路径常量，无逻辑分支

## 测试结果

```
186 passed in 6.63s
```

环境：Windows + Python 3.13 + uv 管理依赖。

```
========================= test session starts =========================
platform win32 -- Python 3.13.x, pytest-8.x, pluggy-1.x
rootdir: .../desktopAI_Hadali
configfile: pyproject.toml: [tool.pytest.ini_options]
collected 186 items

tests/test_chat_agent.py ......... [38%]   38 passed
tests/test_chatbot.py ...............      15 passed
tests/test_config_handler.py .....         5 passed
tests/test_expression_driver.py ................  16 passed
tests/test_factory.py .........            9 passed
tests/test_get_time.py ..........         10 passed
tests/test_logger_handler.py ......        6 passed
tests/test_mode_configs.py ...........     15 passed
tests/test_path_tool.py .......           7 passed
tests/test_prompt_loader.py ....           4 passed
tests/test_tool_manager.py ..........     10 passed
tests/test_tts.py .....................   21 passed
tests/test_weather.py .................   17 passed
tests/test_web_search.py .............    13 passed

========================= 186 passed in 6.63s =========================
```

## 新增测试指引

新增模块时，遵循现有平铺约定：

1. 在 `tests/` 下新建 `test_<模块名>.py`；
2. 纯逻辑直接测试，外部依赖用 `unittest.mock` 打桩；
3. 涉及文件 I/O 的用 `tmp_path` fixture 隔离；
4. 涉及全局状态的用 `monkeypatch` 在测试后还原；
5. 运行 `uv run pytest tests/ -v` 确认通过。
