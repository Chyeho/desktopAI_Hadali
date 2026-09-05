# DesktopAI_Hadali

基于 PySide6 + Live2D 的桌面情感陪伴 AI 助手。AI 助手形象为 Live2D 模型（固定神态动作），内置 AI 聊天（langchain 驱动，支持任意 OpenAI 协议大模型）、基础工具调用与多 agent 模式扩展通道。

## 功能特性

- Live2D 桌宠形象，自动适配窗口大小、随窗口等比缩放
- 与 AI 角色对话（哈达莉），回复逐字打字机显示
- AI 具备基础工具调用能力：本机时间 / 天气查询 / 联网搜索
- 对话历史持久化：关闭程序后 AI 仍记得之前的对话
- 情感标签驱动 live2d 表情（表情资源待接入，链路已打通）
- 多 agent 模式扩展通道（当前为情感陪伴主模式，办公模式预留）
- 单轮对话框交互：输入 → 思考中 → 回复 → 点击恢复输入
- 半透明聊天框，支持拖拽窗口、滚轮缩放
- 右键菜单：最小化到托盘 / 退出程序

> Live2D 形象来源于 Live2D 官方提供的免费模型（HiYori），仅用于学习与演示用途。

## 运行方式

1. 安装依赖（使用国内镜像加速）：

   ```
   uv sync
   ```

2. 在项目根目录创建 `.env` 文件，写入大模型连接参数（默认 DeepSeek，可换任意 OpenAI 协议端）：

   ```
   API_KEY=sk-你的llm密钥
   BASE_URL=https://api.deepseek.com/v1
   MODEL=deepseek-chat
   ```

3. 启动程序：

   ```
   uv run python main.py
   ```

## 项目结构

- `main.py`        程序主入口
- `chatbot.py`     AI 对话门面（初始化 + 对外接口，核心逻辑在 `agent/`）
- `agent/`         AI 对话核心：chat_agent（工具调用循环）/ tool_manager（工具管理）/ expression_driver（表情驱动）/ mode_configs（模式配置）
- `modelFactory/`  模型工厂（langchain ChatOpenAI，工厂模式）
- `tools/common/`  公共工具（本机时间 / 天气 / 联网搜索）
- `utils/`         工具集（配置 / 日志 / 路径 / 提示词加载）
- `prompts/`       系统提示词文本（不硬编码在代码中）
- `config/`        配置文件（提示词路径等 yaml）
- `chatbotUI.py`   Live2D 桌宠界面
- `chatbotTTS.py`  语音合成模块（TTS，qwen3-tts / edge-tts）
- `resources.py`   资源目录常量
- `Resources/`     Live2D 模型资源

## AI 对话逻辑与 agent 模式

**对话流程**：用户输入 → AIWorker 后台线程处理（模型思考 → 按需调用工具 → 解析回复）→ 聊天框打字机逐字显示。

- **模型工厂**：连接参数（`API_KEY` / `BASE_URL` / `MODEL`）从 `.env` 读取，生产 langchain `ChatOpenAI`，支持 DeepSeek、通义兼容端、本地 vLLM 等任意 OpenAI 协议模型
- **工具调用**：手写轻量循环（`bind_tools`，单次对话最多 6 轮），模型遇到实时信息（时间 / 天气 / 新闻等）时自动调用工具后作答，不使用 ReAct 等重型框架
- **结构化输出**：模型最终回复为严格 JSON `{"emotion": "...", "reply": "..."}`，`emotion`（9 种情感标签）驱动 live2d 表情（待接入），`reply` 用于聊天框显示与 TTS 播报
- **对话记忆**：历史持久化到 `chat_history/default.json`，重启自动加载，仅保留最近 30 条滑动窗口

**agent 模式切换**：每个模式一份配置（系统提示词 / 工具白名单 / 模型生成参数），注册在 `agent/mode_configs/`。当前仅实现情感陪伴主模式（emotion）；桌面办公模式（office）为预留 stub。代码层调用 `chatbot.switch_mode("office")` 即可切换，UI 右键菜单接入待开发。新增模式只需：写提示词 → 加工具 → 加模式配置 → 注册。

## TTS 语音合成方案

桌宠播报语音由 `chatbotTTS.py` 负责，通过 `.env` 的 `TTS_MODE` 切换运行模式：

- **demo（演示模式，默认）**：优先 qwen3-tts（阿里云百炼，多语言混说 + 自定义音色），失败时 edge-tts 兜底
- **dev（开发模式）**：仅使用 edge-tts（免费、零配置，不依赖 API Key）

### 方案对比

| 方案 | 多语言混说 | 部署/配置 | 音色 | 成本 | 说明 |
| --- | --- | --- | --- | --- | --- |
| **edge-tts** | 弱 | 云端、零配置 | 固定 | 免费 | 免费但固定音色，用作兜底方案 |
| **GPT-SoVITS** | 否 | 本地、部署困难 | 自训练 | 免费 | 吃电脑配置，需先自训练模型，无法多语言混说，本地部署困难 |
| **genie-tts** | 否 | 本地 CPU 可跑 | 演示/自训练 | 免费 | 解决了 GPT-SoVITS 的配置和部署问题，CPU 能跑，有演示模型，但依旧无法多语言混说（已弃用） |
| **qwen3-tts** | 是 | 云端、需 API Key | 固定 + 声音设计 | 付费 | 有固定音色且能便捷生成独特音色（灵活性偏低，不能克隆指定角色音色；qwen3-tts-vc 模型支持声音复刻），支持多语言混说 |
| **moss-tts-nano** | 是 | 本地、配置要求低 | 固定 + 自训练 | 免费 | 免费，配置要求低，支持多语言混说，有固定音色和可训练自训练音色，但自训练音色官方缺少资料，可未来考虑 |
| **fish-speech** | 是 | 本地吃配置 / 云端可克隆 | 可克隆 | 免费/付费 | 满足大部分需求，但吃本地配置；云端方案能克隆音色，可尝试云端方案 |
| **meloTTS** | 弱 | 本地、低配置可跑 | 少量固定 | 免费 | 少量固定音色，无法克隆或训练，但可低配置本地推理，可未来成为兜底方案 |

### 当前状况与未来方向

- **当前**：暂时使用 edge-tts 和 qwen3-tts 切换进行桌宠 TTS 服务
- **未来主力**：云端 fish-speech（可克隆音色）和 moss-tts-nano（优先考虑 fish-speech）
- **本地部署**：电脑配置问题解决后，可选本地 fish-speech
- **兜底演进**：edge-tts 可替换为 meloTTS

## .env 配置
```text
# 环境变量配置文件
# 用于存储敏感信息，如API密钥、数据库连接等

# 1.API密钥（支持任意 OpenAI 协议大模型：DeepSeek / 通义兼容端 / 本地 vLLM 等）
API_KEY=sk-你的llm密钥
# 1.1 大模型接口地址（OpenAI 兼容端点）
BASE_URL=https://api.deepseek.com/v1
# 1.2 大模型名称
MODEL=deepseek-chat

# 2.语音合成(TTS)配置项
# TTS 运行模式（demo / dev）：
#     demo = 演示模式：优先 qwen3-tts，失败时 edge-tts 兜底
#     dev  = 开发模式：仅使用 edge-tts
TTS_MODE=demo
# 2.1  edge-tts 音色
EDGE_TTS_VOICE=zh-CN-XiaoxiaoNeural
# 2.2 阿里云百炼 qwen3-tts 云端 TTS
#     获取 API Key：阿里云百炼控制台 https://bailian.console.aliyun.com/
DASHSCOPE_API_KEY=sk-你的阿里云密钥
#     模型：qwen3-tts-vd-2026-01-26（声音设计音色，HTTP 流式） / qwen3-tts-vc-2026-01-22（声音复刻音色）
#     其他：cosyvoice-v2 / cosyvoice-v3-flash / qwen-audio-3.0-tts-plus 等（WebSocket 接入）
DASHSCOPE_MODEL=qwen3-tts-vd-2026-01-26
#     音色（qwen3-tts 常用）：longxiaoxia_v2 龙小夏(温柔年轻女声) / longxiaochun_v2 龙小淳(温柔姐姐)
#     自定义声音设计/复刻音色：直接填音色 ID（需与模型匹配）
DASHSCOPE_VOICE=音色ID
```
