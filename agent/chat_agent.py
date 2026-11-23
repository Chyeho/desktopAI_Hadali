'''AI 对话核心

职责：
- 大模型对话（langchain ChatOpenAI，工厂模式生产）
- 轻量工具调用循环（bind_tools：模型请求工具 → 执行 → 结果回填 → 再思考，直到给出最终回复）
- 对话历史持久化（JSON 文件，关闭程序后仍能记住）
- 最终回复 JSON 解析（情感标签 + 回复内容），返回结构化回合结果
- 支持多 agent 模式切换（set_mode：提示词 / 工具白名单 / 生成参数随模式切换）

说明：不使用 ReAct / create_agent 等重型框架，采用手写工具调用循环，
逻辑可控，便于情感陪伴场景下的严格 JSON 输出。
本模块不依赖 UI：情感标签只做合法性校验，live2d 表情动画由 client 层负责。
'''
import json
import re
import time

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from modelFactory.factory import ChatModelFactory
from agent.history import HistoryStore
from agent.tool_manager import ToolManager
from agent.turn import ToolCallRecord, TurnResult
from agent.mode_configs import DEFAULT_MODE, MODE_REGISTRY
from agent.expression_driver import validate_emotion
from utils.prompt_loader import load_prompt
from utils.logger_handler import logger

# 单次对话中工具调用的最大轮数（防止模型反复调用工具形成死循环）
MAX_TOOL_STEPS = 6


def parse_reply_json(content: str) -> tuple[str, str]:
    '''解析大模型最终回复（约定为严格 JSON：{"emotion": "...", "reply": "..."}）

    返回 (emotion, reply)；
    容错：剥离 markdown 代码块、截取首个 {...}；解析失败回退 ("neutral", 原文)。
    '''
    if not content:
        return "neutral", ""
    text = content.strip()

    # 情形 1：被 ```json ... ``` 代码块包裹
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if fence:
        text = fence.group(1)
    else:
        # 情形 2：模型在 JSON 外夹带了额外文字，截取第一个 { 到最后一个 }
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            text = text[start:end + 1]

    try:
        data = json.loads(text)
        emotion = str(data.get("emotion", "neutral")).strip() or "neutral"
        reply = str(data.get("reply", "")).strip()
        if not reply:
            logger.warning("[chat_agent]回复 JSON 中 reply 为空，回退使用原文")
            return emotion, content.strip()
        return emotion, reply
    except Exception as e:
        logger.warning(
            f"[chat_agent]回复 JSON 解析失败，按纯文本处理：{str(e)}；"
            f"原文前 80 字：{content[:80]}"
        )
        return "neutral", content.strip()


class ChatAgent:
    '''对话 agent：按模式加载模型与工具，执行工具调用循环，管理历史并输出情感与回复'''

    def __init__(self, model_factory: ChatModelFactory, tool_manager: ToolManager = None,
                 history_file: str = None):
        self.model_factory = model_factory
        self.tool_manager = tool_manager or ToolManager()
        # history_file 为空时沿用默认单会话文件；多会话/测试注入时可指定独立文件
        self.history_file = history_file
        self.history = HistoryStore(file_path=history_file) if history_file else HistoryStore()
        self.mode_config: dict | None = None
        self.llm = None               # 当前模式的 ChatOpenAI 实例
        self.llm_with_tools = None    # bind_tools 后的模型（无工具时等同 llm）
        self.tool_map: dict = {}      # 当前模式可用工具 {工具名: BaseTool}
        self.set_mode(DEFAULT_MODE)

    def set_mode(self, mode_name: str) -> None:
        '''切换 agent 模式：重载提示词、按模式生成模型并绑定工具白名单

        历史对话保留（同一用户的连续对话），仅替换 system 消息。
        '''
        if mode_name not in MODE_REGISTRY:
            logger.error(
                f"[ChatAgent]未知模式：{mode_name}，可用模式：{list(MODE_REGISTRY.keys())}"
            )
            raise ValueError(f"未知的 agent 模式：{mode_name}")

        self.mode_config = MODE_REGISTRY[mode_name]

        # 1. 按模式生成参数生成大模型
        self.llm = self.model_factory.generator(**self.mode_config.get("model_params", {}))

        # 2. 按白名单绑定工具
        allowed_tools = self.mode_config.get("allowed_tools", [])
        tools = self.tool_manager.get_tools(allowed_tools)
        self.tool_map = {t.name: t for t in tools}
        self.llm_with_tools = self.llm.bind_tools(tools) if tools else self.llm
        logger.info(
            f"[ChatAgent]切换模式：{mode_name}（{self.mode_config.get('display_name', '')}），"
            f"可用工具：{list(self.tool_map.keys())}"
        )

        # 3. 加载该模式系统提示词并更新历史中的 system 消息
        try:
            system_prompt = load_prompt(self.mode_config["system_prompt_path"])
        except Exception:
            logger.warning(f"[ChatAgent]模式 {mode_name} 的系统提示词加载失败，使用空提示词")
            system_prompt = ""
        self.history.set_system_prompt(system_prompt)
        self.history.save()

    def chat(self, user_input: str) -> TurnResult:
        '''处理一次用户输入

        流程：追加用户消息 → 工具调用循环（思考 → 调工具 → 再思考 → 最终回复）
        → 解析回复 JSON（emotion / reply）→ 保存历史 → 返回结构化回合结果。

        返回 TurnResult：emotion / reply / mode / steps / tool_calls / latency_ms。
        live2d 表情动画不在本层触发，由 client 收到 emotion 后播放。
        '''
        started_at = time.perf_counter()

        # 1. 记录用户输入
        self.history.append(HumanMessage(content=user_input))
        self.history.save()

        final_content = ""
        tool_records: list[ToolCallRecord] = []
        steps = 0
        try:
            # 2. 工具调用循环
            for step in range(MAX_TOOL_STEPS):
                steps = step + 1
                logger.info(
                    f"[ChatAgent]第 {steps} 轮模型调用，当前历史消息数：{len(self.history.messages)}"
                )
                ai_msg: AIMessage = self.llm_with_tools.invoke(self.history.messages)
                self.history.append(ai_msg)

                tool_calls = getattr(ai_msg, "tool_calls", None)
                if not tool_calls:
                    # 模型不再请求工具 → 得到最终回复
                    final_content = ai_msg.content if isinstance(ai_msg.content, str) else str(ai_msg.content)
                    break

                # 3. 模型请求调用工具：逐个执行并回填 ToolMessage
                for tc in tool_calls:
                    name = tc.get("name", "")
                    args = tc.get("args", {}) or {}
                    call_id = tc.get("id", "")
                    tool = self.tool_map.get(name)

                    tool_started = time.perf_counter()
                    ok = True
                    if tool is None:
                        result = f"工具 {name} 不可用"
                        ok = False
                        logger.error(f"[ChatAgent]模型请求调用了未授权/不存在的工具：{name}")
                    else:
                        logger.info(f"[ChatAgent]调用工具：{name}，入参：{args}")
                        try:
                            result = tool.invoke(args)
                            logger.info(f"[ChatAgent]工具 {name} 调用成功")
                        except Exception as e:
                            result = f"工具 {name} 执行出错：{str(e)}"
                            ok = False
                            logger.error(f"[ChatAgent]工具 {name} 调用失败：{str(e)}")

                    tool_records.append({
                        "name": name,
                        "args": args,
                        "ok": ok,
                        "duration_ms": round((time.perf_counter() - tool_started) * 1000, 2),
                    })
                    self.history.append(
                        ToolMessage(content=str(result), tool_call_id=call_id, name=name)
                    )
            else:
                # 达到最大轮数仍未给出最终回复
                logger.warning("[ChatAgent]工具调用达到最大轮数，强制结束循环")
                final_content = final_content or "我刚刚处理得有点久呢，用户可以再问我一次吗？"

            # 4. 解析最终回复：emotion 供 client 播放表情，reply 用于聊天框展示与 TTS 播报
            emotion, reply = parse_reply_json(final_content)
            emotion = validate_emotion(emotion)

            self.history.save()
            return TurnResult(
                emotion=emotion,
                reply=reply,
                mode=self.mode_config.get("name", "") if self.mode_config else "",
                steps=steps,
                tool_calls=tool_records,
                latency_ms=round((time.perf_counter() - started_at) * 1000, 2),
            )
        except Exception:
            # 异常时也保存已有历史（含用户消息与工具过程），便于排查
            self.history.save()
            raise
