'''陪伴主图的 agent 节点

- 每轮按用户文本选择工具（select_tools_for），bind_tools 后调用模型；
- 模型请求工具时原样返回 AIMessage（由 ToolNode 执行）；
- 无 tool_calls 时解析并剥离情绪标签，追加时间后缀，情绪写入 additional_kwargs；
- 模型支持 stream 时用 stream 聚合，使 LangGraph 的 messages 流式模式能逐 token 输出。
'''
from typing import Any

from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    SystemMessage,
)

from agent.graph.emotion import parse_emotion_tag
from agent.graph.state import AgentState
from agent.graph.tooling import get_agent_tools, select_tools_for
from utils.logger_handler import logger
from utils.prompt_loader import load_graph_prompt
from utils.time_utils import (
    DEFAULT_TIME_FORMAT,
    strip_time_markers,
    strip_user_time,
    with_reply_time,
)


def _last_user_text(messages: list[BaseMessage]) -> str:
    '''取最近一条用户消息文本（剥离时间前缀），用于工具分组'''
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            content = message.content if isinstance(message.content, str) else str(message.content)
            return strip_user_time(content)
    return ""


def _merge_chunks(chunks: list[AIMessageChunk]) -> AIMessageChunk:
    '''把流式分片合并成一条消息'''
    merged = chunks[0]
    for chunk in chunks[1:]:
        merged = merged + chunk
    return merged


def invoke_llm(llm: Any, messages: list[BaseMessage]) -> Any:
    '''优先使用 stream 聚合（兼容 LangGraph messages 流式模式），失败回落 invoke'''
    stream = getattr(llm, "stream", None)
    if callable(stream):
        try:
            chunks = list(stream(messages))
        except Exception as e:
            logger.warning(f"[graph.llm]流式调用失败，回落 invoke：{str(e)}")
        else:
            if chunks:
                return _merge_chunks(chunks)
    return llm.invoke(messages)


def to_ai_message(message: Any) -> AIMessage:
    '''把聚合后的 AIMessageChunk 归一化为 AIMessage'''
    if not isinstance(message, AIMessageChunk):
        return message
    return AIMessage(
        content=message.content,
        tool_calls=message.tool_calls or [],
        additional_kwargs=dict(message.additional_kwargs),
        id=message.id,
    )


def finalize_reply(message: AIMessage, time_format: str = DEFAULT_TIME_FORMAT) -> AIMessage:
    '''解析情绪标签、清理时间标记并追加时间后缀，返回最终回复消息'''
    content = message.content if isinstance(message.content, str) else str(message.content)
    emotion, clean_reply = parse_emotion_tag(content)
    return AIMessage(
        content=with_reply_time(strip_time_markers(clean_reply), fmt=time_format),
        additional_kwargs={**dict(message.additional_kwargs), "emotion": emotion},
        id=message.id,
    )


class AgentNode:
    '''陪伴 agent 节点：注入系统提示词、绑定工具并调用模型'''

    def __init__(self, llm: Any, system_prompt: str | None = None,
                 tools: list | None = None,
                 time_format: str = DEFAULT_TIME_FORMAT):
        self.llm = llm
        if system_prompt is None:
            try:
                system_prompt = load_graph_prompt()
            except Exception as e:
                # 提示词缺失不阻断对话，保持与旧行为一致
                logger.warning(f"[graph.agent]系统提示词加载失败：{str(e)}")
                system_prompt = ""
        self.system_prompt = system_prompt
        self.tools = get_agent_tools() if tools is None else list(tools)
        self.time_format = time_format

    def __call__(self, state: AgentState) -> dict:
        messages: list[BaseMessage] = list(state.get("messages") or [])
        if self.system_prompt:
            # 系统提示词每轮临时拼入，不写入 state，避免污染持久化的对话历史
            messages = [SystemMessage(content=self.system_prompt), *messages]

        tools = select_tools_for(_last_user_text(messages), self.tools)
        llm_with_tools = self.llm.bind_tools(tools) if tools else self.llm
        ai_message = to_ai_message(invoke_llm(llm_with_tools, messages))

        tool_calls = getattr(ai_message, "tool_calls", None)
        if tool_calls:
            # 工具轮次不追加时间、不解析情绪，交给 ToolNode 执行
            logger.info(f"[graph.agent]请求工具：{[c.get('name') for c in tool_calls]}")
            return {"messages": [ai_message]}

        logger.info(f"[graph.agent]最终回复，工具：{[t.name for t in tools]}")
        return {"messages": [finalize_reply(ai_message, self.time_format)]}
