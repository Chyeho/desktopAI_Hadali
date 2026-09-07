# DesktopAI_Hadali

基于 PySide6 + Live2D 的多功能桌面情感陪伴 AI 助手「哈达莉」。AI 助手形象为 Live2D 模型（HiYori），内置 AI 聊天（LangChain 驱动，支持任意 OpenAI 协议大模型）、轻量级工具调用循环、情感标签驱动的表情动画、多 agent 模式扩展通道与可换源的 TTS 语音播报。哈达莉的定位是「伴随在桌面的情感陪伴 AI 助手」——既能自然地陪伴聊天、关心用户日常，也能按需扩展为桌面办公、编程等专用 agent 模式，辅助用户处理实际任务。

## 功能特性

- Live2D 桌宠形象，自动适配窗口大小、随窗口等比缩放
- 与 AI 角色对话（哈达莉），回复逐字打字机显示
- AI 具备基础工具调用能力：本机时间 / 天气查询 / 联网搜索
- 对话历史持久化：关闭程序后 AI 仍记得之前的对话
- 已接入部分表情动画，持续开发中（10 种情感标签 → 6 组 hiyori 自带动作，播完平滑过渡回常态）
- 多 agent 模式扩展通道（当前为情感陪伴主模式，办公 / 编程等模式预留）
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

- `main.py`              程序主入口
- `chatbot.py`           AI 对话门面（初始化 + 对外接口，核心逻辑在 `agent/`）
- `agent/`               AI 对话核心：chat_agent（工具调用循环）/ tool_manager（工具管理）/ expression_driver（表情驱动）/ mode_configs（模式配置）
- `modelFactory/`        模型工厂（langchain ChatOpenAI，工厂模式）
- `tools/common/`        公共工具（本机时间 / 天气 / 联网搜索）
- `utils/`               工具集（配置 / 日志 / 路径 / 提示词加载）
- `prompts/`             系统提示词文本（不硬编码在代码中）
- `config/`              配置文件（提示词路径等 yaml）
- `chatbotUI.py`         Live2D 桌宠界面（含表情动画驱动 + 回常态平滑过渡）
- `chatbotTTS.py`        语音合成模块（TTS，qwen3-tts / edge-tts）
- `expression_tester.py` Live2D 表情动画调试台（独立运行，见下文）
- `resources.py`         资源目录常量
- `Resources/`           Live2D 模型资源（HiYori 模型 + 动作）

## AI 对话逻辑与 agent 模式

**对话流程**：用户输入 → AIWorker 后台线程处理（模型思考 → 按需调用工具 → 解析回复）→ 聊天框打字机逐字显示。

- **模型工厂**：连接参数（`API_KEY` / `BASE_URL` / `MODEL`）从 `.env` 读取，生产 langchain `ChatOpenAI`，支持 DeepSeek、通义兼容端、本地 vLLM 等任意 OpenAI 协议模型
- **工具调用**：手写轻量循环（`bind_tools`，单次对话最多 6 轮），模型遇到实时信息（时间 / 天气 / 新闻等）时自动调用工具后作答，不使用 ReAct 等重型框架
- **结构化输出**：模型最终回复为严格 JSON `{"emotion": "...", "reply": "..."}`，`emotion`（10 种情感标签）驱动 live2d 表情动画，`reply` 用于聊天框显示与 TTS 播报
- **对话记忆**：历史持久化到 `chat_history/default.json`，重启自动加载，仅保留最近 30 条滑动窗口

**agent 模式切换**：每个模式一份配置（系统提示词 / 工具白名单 / 模型生成参数），注册在 `agent/mode_configs/`。当前仅实现情感陪伴主模式（emotion）；桌面办公模式（office）、编程模式等为预留扩展。代码层调用 `chatbot.switch_mode("office")` 即可切换，UI 右键菜单接入待开发。新增模式只需：写提示词 → 加工具 → 加模式配置 → 注册。

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

## Live2D 表情动画系统

情感标签 → 动作组的映射定义在 `agent/expression_driver.py` 的 `EMOTION_MOTION_MAP`，当前接入了 HiYori 模型自带的 6 组动作：

| 情感标签 | 动作组 | 含义 |
| --- | --- | --- |
| `thinking` | `Idle` | 了解并思考 |
| `relaxed` | `Flick` | 悠闲 / 摇头晃脑 |
| `shy` | `FlickDown` | 害羞 |
| `surprised` | `Tap` | 惊讶 |
| `angry` | `Tap@Body` | 生气 |
| `sad` | `Flick@Body` | 难过 |
| `happy` / `neutral` / `worried` / `excited` | — | 暂无对应动作，保持常态（自动呼吸 / 眨眼） |

### 平滑回常态机制

`chatbotUI.py` 的 `Live2DWidget` 在每次表情动作播放结束后，会用 **smoothstep 缓动**在 1.5 秒内把全部参数从动作末值平滑插值回 `default`（常态），过渡完成再恢复自动眨眼 / 呼吸。避免动作一结束就跳变回中性参数导致不自然。

### 跨线程安全

`drive_expression` 在 `AIWorker` 子线程被调用，通过 `Live2DWidget.request_play_motion` 信号（`QueuedConnection`）把动作播放请求转发到主线程执行，避免子线程直接操作 OpenGL 导致崩溃。

## Live2D 表情动画调试台

`expression_tester.py` 是一个独立运行的调试工具，用于在接入主程序前先在 HiYori 模型上探索、组合并保存自定义神态 / 动作，再迁入主程序。

```bash
uv run python expression_tester.py
```

主要功能：

- **实时调参**：面部表情（脸朝向 / 眼睛 / 眉毛 / 嘴形 / 脸红）与身体肢体（左右臂 / 身体三轴）滑条，拖动立即生效，范围从模型真实 min/max 读取
- **一键肢体姿态**：双手举起 / 单手举起 / 身体倾斜 / 歪头卖萌 / 站姿归位等预设按钮，可与面部表情叠加
- **神态预设保存**：把当前表情 + 肢体组合保存为命名预设，存入 `expression_presets.json`（追加保存，重启不丢）
- **平滑过渡**：从当前姿态 smoothstep 过渡到指定预设，可调时长
- **动画序列**：把多个预设按顺序串联成动画，支持循环播放，存入 `expression_animations.json`
- **Dump 全部参数**：一键打印所有参数的 id / min / max / default / 当前值，方便了解模型能力边界

> 调试台产出的预设 / 动画是后续扩展自定义神态（不依赖模型自带动作）的原料，可由主程序按需加载。

## 项目期望与规划

哈达莉的长期目标是做一个「伴随在桌面的、能陪伴也能干活的多功能 AI 助手」。当前以情感陪伴为主模式，后续会沿以下方向演进：

### 多 agent 模式扩展

在情感陪伴主模式之外，引入更多专业 agent 模式，让哈达莉具备辅助用户处理实际任务的能力：

- **桌面办公 agent**：日程管理、邮件 / 消息摘要、文档润色、待办提醒，把桌面侧的高频操作纳入工具调用
- **编程 agent**：代码片段解释 / 生成、项目内检索、提交信息撰写、运行命令封装，作为轻量编程副驾
- **通用扩展机制**：每个模式一份提示词 + 工具白名单 + 模型生成参数，已预留注册通道，新增模式即写即用

### 分层记忆架构

多 agent 模式下「记忆错乱 / 忘事」是核心痛点。规划采用分层记忆架构替代当前的单一滑动窗口：

- **长期全局层**：跨模式共享，存所有 agent 模式的关键事实与用户偏好（用户画像、长期约定、跨模式共识）
- **短期工作层**：按 agent 模式分桶，缓存各模式近期对话上下文，切换模式时不互相污染
- **模式切换时**：仅加载对应模式的短期层 + 全局层，避免不同 agent 的工具语义 / 角色设定串扰

目标是在多 agent 切换下仍保持「记得用户说过的事」，同时不让办公上下文污染陪伴对话、反之亦然。

### 更丰富的表情动画

当前已接入 HiYori 自带的 6 组动作。后续通过 `expression_tester.py` 探索参数组合，为更多情感标签设计自定义神态（不依赖模型自带动作），让哈达莉更生动；未来换用绑定更完整的模型后，动作空间会进一步打开（HiYori 无独立手脚绑定，大幅动作能力有限）。

### 屏幕识别与主动搭话

让哈达莉从「被动应答」走向「主动陪伴」，更贴合「桌面情感陪伴」的定位：

- **屏幕感知**：识别当前前台应用 / 窗口标题 / 工作状态，判断用户是否在忙
- **主动搭话**：基于时间（久坐提醒、深夜问候）、状态（长时间无操作、应用切换）和记忆（之前聊过的话题）主动发起对话
- **节奏控制**：避免打扰，尊重专注状态，搭话频率与时机可配
