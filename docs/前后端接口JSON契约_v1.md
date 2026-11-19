# 前后端接口 JSON 契约（协议 v1）

本文是 `client/`（前端 / UI 进程）与 `server/`（后端 / FastAPI 进程）之间的**唯一对接依据**。
契约的代码真源是 [protocol/events.py](file:///d:/soft/trae/Trae%20CN/projects/desktopAI_Hadali/protocol/events.py)（SSE 事件）与 [protocol/requests.py](file:///d:/soft/trae/Trae%20CN/projects/desktopAI_Hadali/protocol/requests.py)（请求体）。
本文与代码不一致时，以代码为准，并应同步修订本文。

| 项目 | 约定 |
| --- | --- |
| 协议版本 | `v1`（路径前缀 `/v1`，事件协议版本同为 v1） |
| 传输 | 本机 HTTP/1.1 + SSE（`text/event-stream`） |
| 默认地址 | `http://127.0.0.1:8765` |
| 字符编码 | 请求、响应、SSE 均为 UTF-8 JSON |
| 鉴权 | 请求头 `X-Hadali-Token`；服务端未设置 `HADALI_TOKEN` 时放行 |
| 时间单位 | `ts` 为 Unix 毫秒；所有 `*_ms` 为毫秒（浮点） |
| 序列化 | pydantic v2：`model_dump_json()` 输出，`model_validate_json()` 校验 |

---

## 1. 端点总览

| 方法 | 路径 | 用途 | 响应类型 |
| --- | --- | --- | --- |
| GET | `/v1/health` | 探活、取版本与模型名 | `application/json` |
| GET | `/v1/modes` | 模式列表 + 当前进程级模式 | `application/json` |
| POST | `/v1/mode` | 切换进程级模式 | `application/json` |
| POST | `/v1/chat` | **一轮对话**（核心接口） | `text/event-stream`（SSE） |
| POST | `/v1/interrupt` | 打断当前轮（尽力而为） | `application/json` |

**所有端点（含 `/v1/health`）**都经过同一个 token 依赖校验；服务端设置了 `HADALI_TOKEN` 时，缺少或不匹配都返回 HTTP 401。

### 1.1 通用错误响应

**鉴权失败（HTTP 401）**——FastAPI `HTTPException` 原样包装在 `detail` 里：

```json
{
  "detail": {
    "code": "UNAUTHORIZED",
    "message": "token 校验失败"
  }
}
```

**请求体校验失败（HTTP 400）**——由全局异常处理器扁平化，**没有** `detail` 包裹：

```json
{
  "code": "BAD_REQUEST",
  "message": "请求参数非法"
}
```

> 注意这两种错误体结构不同（一个嵌套 `detail`、一个扁平）。前端解析 HTTP 4xx 时应兼容两种取法：
> `body.detail.message ?? body.message ?? "未知错误"`。

**业务校验失败（HTTP 400，如未知模式）**——同样是嵌套结构：

```json
{
  "detail": {
    "code": "BAD_REQUEST",
    "message": "未知的 agent 模式：xxx"
  }
}
```

---

## 2. `GET /v1/health`

探活。客户端启动时会用它判断“后端是否已在运行”，`bench` 与 `ServerLauncher` 也用它轮询就绪。

**响应 200**

```json
{
  "status": "ok",
  "version": "0.1.0",
  "model": "deepseek-chat"
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `status` | string | 恒为 `"ok"` |
| `version` | string | 服务端版本，当前 `0.1.0` |
| `model` | string | `.env` 中的 `MODEL`；读取失败时为空串 |

---

## 3. `GET /v1/modes`

返回模式注册表与当前进程级模式。

**响应 200**

```json
{
  "current": "emotion",
  "modes": [
    { "name": "emotion", "display_name": "情感陪伴" },
    { "name": "office", "display_name": "桌面办公" }
  ]
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `current` | string | 进程级当前模式 |
| `modes[].name` | string | 模式标识，供 `/v1/chat` 的 `mode` 使用 |
| `modes[].display_name` | string | 展示名 |

---

## 4. `POST /v1/mode`

切换**进程级**当前模式。已存在的会话在下一次对话时惰性跟随（不重建 agent）。

**请求体**

```json
{ "mode": "office" }
```

| 字段 | 类型 | 必填 | 约束 |
| --- | --- | --- | --- |
| `mode` | string | 是 | 最短 1；必须在模式注册表中，否则 400 |

**响应 200**

```json
{ "ok": true, "current": "office" }
```

**错误**

- 未知模式 → 400，`{"detail":{"code":"BAD_REQUEST","message":"未知的 agent 模式：xxx"}}`
- 缺字段 / 空串 → 400，扁平 `{"code":"BAD_REQUEST","message":"请求参数非法"}`

---

## 5. `POST /v1/interrupt`

打断当前轮。语义是**尽力而为**：服务端 agent 是同步阻塞调用，无法安全强杀工作线程，因此服务端只做确认；真正的停止发生在客户端（关闭 SSE 连接、停 TTS / 表情、丢弃后续事件）。

**请求体**

```json
{ "session_id": "default" }
```

**响应 200**

```json
{ "ok": true }
```

> 客户端实现：先起一个后台线程 POST 本接口，再本地 `response.close()`。两者互不阻塞，服务端不可达也不影响打断。

---

## 6. `POST /v1/chat`（核心）

### 6.1 请求

| 项 | 值 |
| --- | --- |
| 方法 / 路径 | `POST /v1/chat` |
| `Content-Type` | `application/json` |
| `Accept` | `text/event-stream` |
| 建议超时 | connect 3s / write 10s / read 60s（两帧间隔超时视为断连） |

**请求体**

```json
{
  "session_id": "default",
  "text": "今天北京天气怎么样？",
  "mode": null
}
```

| 字段 | 类型 | 必填 | 默认 | 约束与语义 |
| --- | --- | --- | --- | --- |
| `session_id` | string | 否 | `"default"` | 正则 `^[A-Za-z0-9_-]{1,64}$`（防路径穿越）；决定对话历史文件与串行锁 |
| `text` | string | 是 | — | 最短 1；用户输入原文 |
| `mode` | string \| null | 否 | `null` | `null` 表示使用服务端进程当前模式；非 null 时本轮临时切到该模式 |

**响应头**

```http
HTTP/1.1 200 OK
content-type: text/event-stream
cache-control: no-cache
x-accel-buffering: no
```

> `x-accel-buffering: no` 用于关闭反向代理缓冲，保证事件即时下发。

### 6.2 SSE 帧格式

每帧由三行组成，**没有** `id:` 与 `retry:` 行：

```text
event: <事件名>
data: <单行 JSON>

```

即 `event: {name}\ndata: {json}\n\n`。客户端收到后按 `event` 名查 `EVENT_MODEL_MAP` 反序列化；**未知事件名与非法 JSON 必须丢弃并继续消费**（只记日志，不中断整轮）。

### 6.3 公共字段（所有事件都带）

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `seq` | int | ≥ 1 | **本轮内**从 1 递增，用于排序与丢帧检测 |
| `turn_id` | string | 32 位 hex | 本轮唯一 ID（`uuid4().hex`），跨事件不变 |
| `ts` | int | — | 事件构造时的 Unix **毫秒**时间戳 |

### 6.4 事件清单

| 事件名 | 载荷字段 | 触发时机（服务端） | 前端应有行为 |
| --- | --- | --- | --- |
| `turn.start` | `mode: string` | 流开始第一帧 | 进入思考态；重置本轮错误标记 |
| `state` | `value: "thinking" \| "speaking" \| "idle"` | 状态变化 | 见 §6.6 状态机 |
| `text.delta` | `text: string` | 模型回复完成，**整段一次性**下发 | 打字机显示（本期不是真流式分片） |
| `text.done` | `text: string` | 紧跟 `text.delta` | 收尾（当前无额外动作，为未来真流式预留） |
| `emotion` | `name: string`、`intensity?: number\|null` | 回复解析出情感标签后 | 触发 Live2D 动作；`intensity` 本期不发送 |
| `tool.call` | `name: string`、`args: object` | agent 结束后**补发**（非实时） | 可展示/记录；不要据此推断进度 |
| `tool.result` | `name: string`、`ok: boolean`、`duration_ms: number` | 与 `tool.call` 成对出现 | 同上 |
| `turn.end` | `reply: string`、`emotion: string`、`latency_ms: number`、`first_event_ms: number` | 成功路径最后一帧业务事件 | 播报语音、记录指标 |
| `error` | `code: string`、`message: string`、`retryable: boolean` | 任意异常 | 显示错误；**本轮不播报** |
| `audio.start` / `audio.delta` / `audio.end` | 见 §8 | **本期不发送**（模型已定义） | 收到可忽略 |

详细模型：

```python
class TurnStartEvent(BaseEvent):   mode: str
class StateEvent(BaseEvent):       value: StateValue          # thinking / speaking / idle
class TextDeltaEvent(BaseEvent):   text: str
class TextDoneEvent(BaseEvent):    text: str
class EmotionEvent(BaseEvent):     name: str; intensity: float | None = None
class ToolCallEvent(BaseEvent):    name: str; args: dict
class ToolResultEvent(BaseEvent):  name: str; ok: bool; duration_ms: float
class TurnEndEvent(BaseEvent):     reply: str; emotion: str; latency_ms: float; first_event_ms: float = 0.0
class ErrorEvent(BaseEvent):       code: str; message: str; retryable: bool
```

### 6.5 成功路径时序

```text
seq 1  turn.start   {mode: "emotion"}
seq 2  state        {value: "thinking"}
       ── 服务端在工作线程执行 agent（同步阻塞）：思考 → 按需工具调用 → 解析 JSON ──
seq 3  state        {value: "speaking"}
seq 4  text.delta   {text: "<整段回复>"}
seq 5  text.done    {text: "<整段回复>"}
seq 6  emotion      {name: "happy"}
seq 7  tool.call    {name: "get_weather", args: {"city": "北京"}}     ← 有工具时才出现，可多组
seq 8  tool.result  {name: "get_weather", ok: true, duration_ms: 812.4}
seq 9  turn.end     {reply: "...", emotion: "happy", latency_ms: 1743.1, first_event_ms: 3.3}
seq 10 state        {value: "idle"}
```

**完整报文样例**（节选，`data` 为单行 JSON，此处为便于阅读做了换行）：

```text
event: turn.start
data: {"seq":1,"turn_id":"8f1c...","ts":1762900000000,"mode":"emotion"}

event: state
data: {"seq":2,"turn_id":"8f1c...","ts":1762900000001,"value":"thinking"}

event: state
data: {"seq":3,"turn_id":"8f1c...","ts":1762900001800,"value":"speaking"}

event: text.delta
data: {"seq":4,"turn_id":"8f1c...","ts":1762900001801,"text":"北京今天晴，气温 8~17℃。"}

event: text.done
data: {"seq":5,"turn_id":"8f1c...","ts":1762900001802,"text":"北京今天晴，气温 8~17℃。"}

event: emotion
data: {"seq":6,"turn_id":"8f1c...","ts":1762900001803,"name":"happy"}

event: turn.end
data: {"seq":7,"turn_id":"8f1c...","ts":1762900001804,"reply":"北京今天晴，气温 8~17℃。","emotion":"happy","latency_ms":1743.1,"first_event_ms":3.3}

event: state
data: {"seq":8,"turn_id":"8f1c...","ts":1762900001805,"value":"idle"}
```

### 6.6 失败路径时序

```text
seq 1  turn.start   {mode: "emotion"}
seq 2  state        {value: "thinking"}
seq 3  error        {code: "LLM_TIMEOUT", message: "...", retryable: true}
seq 4  state        {value: "idle"}
```

```text
event: error
data: {"seq":3,"turn_id":"8f1c...","ts":1762900000002,"code":"LLM_TIMEOUT","message":"Request timed out.","retryable":true}

event: state
data: {"seq":4,"turn_id":"8f1c...","ts":1762900000003,"value":"idle"}
```

> **无论成功或失败，事件流一定以 `state(idle)` 收尾**（`error` 之后也有），前端据此恢复输入，避免卡在思考态。

### 6.7 状态机

```text
            turn.start / state(thinking)
   idle ─────────────────────────────▶ thinking
     ▲                                    │
     │                                    │ agent 完成
     │        state(idle)                 ▼
     └─────────────────────────────── speaking ──▶ (text.delta → text.done → turn.end)
     ▲                                    │
     └──────── error ─────────────────────┘
```

- `thinking`：已发出请求，模型/工具执行中
- `speaking`：回复已产出（本期与 `text.delta` 同一时刻，语音由前端播报）
- `idle`：本轮结束（成功或失败），前端恢复输入态

---

## 7. 错误码（`error.code`）

| 错误码 | 含义 | `retryable` | 典型来源 |
| --- | --- | --- | --- |
| `BAD_REQUEST` | 请求参数/模式非法 | `false` | pydantic 校验失败、未知模式（`ValueError`） |
| `UNAUTHORIZED` | token 校验失败 | — | **不出现在 SSE 中**，仅 HTTP 401 |
| `SESSION_BUSY` | 同会话已有请求在执行 | `true` | 预留，当前由前端 `is_busy()` 先行拦截 |
| `LLM_TIMEOUT` | 大模型超时 | `true` | `TimeoutError` 或异常名含 `timeout` |
| `LLM_ERROR` | 大模型/网络连接错误 | `true` | 异常名含 `connection` / `connect` |
| `TOOL_ERROR` | 工具执行错误 | `true` | 预留 |
| `INTERRUPTED` | 被打断 | `true` | 预留（本期打断由前端本地关闭连接实现） |
| `INTERNAL` | 其他未分类异常 | `true` | 兜底 |

规则：`retryable = (code != "BAD_REQUEST")`。**是否真的自动重试由前端决定**，后端只给建议。

### 7.1 HTTP 状态码与前端提示对照

| 状态码 | 场景 | 参考提示文案 |
| --- | --- | --- |
| 400 | 参数非法 / 未知模式 | 请求参数错误，请检查输入后重试 |
| 401 | token 不匹配 | 后端鉴权失败（token 不匹配），请重新启动客户端 |
| 404 | 路径不存在（服务版本不符） | 后端接口不存在，请确认服务版本 |
| 5xx | 服务端未捕获异常 | 后端返回错误（HTTP xxx） |

### 7.2 连接层失败

以下情况**不属于**事件协议，由传输层直接上报给 UI：

| 情况 | 处理 |
| --- | --- |
| `httpx.ConnectError` / `ConnectTimeout`，且**一个事件都没收到** | 等待 1s 重试一次（`retry_delay`）；仍失败则提示“与后端的连接中断” |
| 已收到任意事件（含 `turn.start`）后失败 | **不重试**（避免重复调用大模型），直接提示 |
| HTTP 5xx / 4xx | 不重试，按 §7.1 提示 |
| 用户主动打断 | 关闭响应流，静默结束，不提示 |

---

## 8. 保留事件：`audio.*`（本期不发送）

服务端尚未内置 TTS，以下模型已定义但**不会出现在流中**。前端收到时应忽略；未来服务端下发时按此解析。

| 事件 | 字段 | 说明 |
| --- | --- | --- |
| `audio.start` | `format: string = "pcm_s16le"`、`sample_rate: int = 24000` | 音频参数 |
| `audio.delta` | `data: string` | base64 音频分片 |
| `audio.end` | `reason: string = "done"` | 结束原因 |

---

## 9. 并发与串行化

- 同一 `session_id` 的请求由服务端异步锁**串行**执行；不同 `session_id` 可并行。
- 前端 `SseTransport` 另有单轮保护：上一轮未结束时 `send()` 直接失败并提示“上一轮回复尚未结束，请稍候”。
- `POST /v1/interrupt` 不等待 agent 结束，立即返回 `{"ok": true}`；被打断轮次的后续事件由前端丢弃。

---

## 10. 兼容性与演进规则

1. **未知事件必须忽略**：前端 `decode_event()` 对不在 `EVENT_MODEL_MAP` 中的事件名只记 debug 日志并丢弃，不允许抛错或中断读流。
2. **新增字段向后兼容**：pydantic 默认忽略多余字段，前端不得因未知字段失败。
3. **字段只增不改**：已有字段的含义、类型、单位不得变更；确需变更时提升协议版本（`/v2`）。
4. **顺序保证**：`seq` 严格递增；`turn.end` 之前必有 `text.done`（成功路径）；`state(idle)` 永远是该轮最后一帧。
5. **事件真源**：任何新增事件需同时更新 `protocol/events.py` 的 `EventName` 与 `EVENT_MODEL_MAP`，并补 `tests/test_transport.py` 的解析用例。

---

## 11. 前端最小接入示例（Python / httpx）

```python
import httpx
from httpx_sse import connect_sse

from protocol.events import EVENT_MODEL_MAP

with httpx.Client(timeout=httpx.Timeout(connect=3.0, read=60.0, write=10.0)) as client:
    with connect_sse(
        client, "POST", "http://127.0.0.1:8765/v1/chat",
        json={"session_id": "default", "text": "你好", "mode": None},
        headers={"Accept": "text/event-stream", "X-Hadali-Token": token},
    ) as source:
        source.response.raise_for_status()
        for message in source.iter_sse():
            model = EVENT_MODEL_MAP.get(message.event)
            if model is None:
                continue                      # 规则 1：未知事件丢弃
            event = model.model_validate_json(message.data)
            handle(message.event, event.model_dump())
```

## 12. 进程级契约：后端就绪通告

自动拉起后端时（`--port 0`，端口由系统分配），后端在**真正完成监听后**向 stdout 打印一行，供客户端解析：

```text
HADALI_SERVER_READY {"port": 1864}
```

- 前缀固定为 `HADALI_SERVER_READY `（含末尾一个空格），其后为单行 JSON。
- 客户端最多等待 20s（含 langchain 等重依赖的导入时间），超时则提示启动失败。
- 该行只在 `--port 0` 时输出；固定端口启动不打这一行。

---

## 13. 契约校验位置

| 内容 | 文件 |
| --- | --- |
| 事件与请求模型（真源） | [protocol/events.py](file:///d:/soft/trae/Trae%20CN/projects/desktopAI_Hadali/protocol/events.py)、[protocol/requests.py](file:///d:/soft/trae/Trae%20CN/projects/desktopAI_Hadali/protocol/requests.py) |
| 服务端实现 | [server/routes/chat.py](file:///d:/soft/trae/Trae%20CN/projects/desktopAI_Hadali/server/routes/chat.py)、[server/routes/meta.py](file:///d:/soft/trae/Trae%20CN/projects/desktopAI_Hadali/server/routes/meta.py)、[server/security.py](file:///d:/soft/trae/Trae%20CN/projects/desktopAI_Hadali/server/security.py) |
| 客户端解析与传输 | [client/transport/client.py](file:///d:/soft/trae/Trae%20CN/projects/desktopAI_Hadali/client/transport/client.py) |
| 契约测试 | `tests/test_server_api.py`（端到端 SSE、错误码、`first_event_ms`）、`tests/test_transport.py`（解码、重试、鉴权） |

## 14. 变更记录

| 日期 | 版本 | 变更 |
| --- | --- | --- |
| 2026-11-19 | v1 | 首版：整理 HTTP + SSE 接口、事件模型、错误码、并发与演进规则 |
