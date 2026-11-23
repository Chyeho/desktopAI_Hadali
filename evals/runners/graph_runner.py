'''单用例执行器：脚本化 LLM + 主图/Done 结果收集

设计约束：
- 不修改主图源码，LLM 与工具全部通过构造参数注入；
- 确定性用例默认不访问网络（MCP 在 conftest 中被隔离）；
- 每个用例使用独立 thread_id，互不依赖。
'''
import time
import uuid
from typing import Any

from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    ToolMessage,
)

from agent.graph.emotion import parse_emotion_tag
from agent.graph.main_graph import build_main_graph
from agent.graph.runner import CompanionGraphAgent
from evals.keywords import (
    FORBIDDEN_TECH_TERMS,
    TIME_MARKER_RE,
    TIME_STATE_RE,
    TIME_TAIL_RE,
)
from utils.time_utils import strip_time_markers, with_user_time

EVAL_SYSTEM_PROMPT = "你是哈达莉，请自然、简短地陪伴用户。"


class ScriptedLLM:
    '''按脚本返回固定 AIMessage，用于确定性评测

    参数：
        steps     : AIMessage / str / callable(messages) -> AIMessage
        streaming : True 时把内容切成小块通过 stream 输出，用于验证流式过滤
    '''

    def __init__(self, steps: list[Any], streaming: bool = False):
        self.steps = [self._normalize(step) for step in steps]
        self.streaming = streaming
        self.cursor = 0
        self.calls: list[list[BaseMessage]] = []
        self.bound_tool_names: list[str] = []
        if not streaming:
            # 实例属性覆盖类方法，使 AgentNode 直接回落到 invoke
            self.stream = None

    @staticmethod
    def _normalize(step: Any) -> Any:
        if isinstance(step, str):
            return AIMessage(content=step)
        return step

    def bind_tools(self, tools):
        self.bound_tool_names = [getattr(tool, "name", "") for tool in tools]
        return self

    def invoke(self, messages):
        self.calls.append(list(messages))
        if self.cursor >= len(self.steps):
            raise AssertionError(
                f"脚本化 LLM 步骤不足：已调用 {self.cursor + 1} 次，仅提供 {len(self.steps)} 步"
            )
        step = self.steps[self.cursor]
        self.cursor += 1
        return step(messages) if callable(step) else step

    def stream(self, messages):
        message = self.invoke(messages)
        content = message.content if isinstance(message.content, str) else str(message.content)
        if getattr(message, "tool_calls", None):
            raise AssertionError("含工具调用的用例请设置 streaming=False")
        for index in range(0, len(content), 2):
            yield AIMessageChunk(content=content[index:index + 2])


def _content(message: BaseMessage) -> str:
    return message.content if isinstance(message.content, str) else str(message.content)


def _last_ai(messages: list[BaseMessage]) -> AIMessage | None:
    for message in reversed(messages):
        if isinstance(message, AIMessage):
            return message
    return None


def _first_human(messages: list[BaseMessage]) -> HumanMessage | None:
    for message in messages:
        if isinstance(message, HumanMessage):
            return message
    return None


def _resolve_tools(case: dict) -> list:
    if case.get("use_agent_tools"):
        from agent.graph.tooling import get_agent_tools
        return get_agent_tools()
    return list(case.get("tools") or [])


def run_case(case: dict) -> dict:
    '''执行一条用例并返回结构化结果'''
    streaming = bool(case.get("streaming"))
    steps = case.get("scripted_steps") or [case.get("scripted_reply", "")]
    llm = ScriptedLLM(steps, streaming=streaming)
    tools = _resolve_tools(case)
    graph = build_main_graph(llm, system_prompt=EVAL_SYSTEM_PROMPT, tools=tools)

    started = time.perf_counter()
    if streaming:
        agent = CompanionGraphAgent(graph=graph)
        deltas: list[str] = []
        done: dict = {}
        for kind, payload in agent.stream_chat(
            case["input"], session_id=f"eval-{uuid.uuid4().hex}"
        ):
            if kind == "delta":
                deltas.append(payload)
            elif kind == "done":
                done = payload
        messages = list(agent.messages)
        reply = done.get("reply", "")
        emotion = done.get("emotion", "")
        route = None
    else:
        config = {"configurable": {"thread_id": f"eval-{uuid.uuid4().hex}"}}
        state = {"messages": [HumanMessage(content=with_user_time(case["input"]))]}
        output = graph.invoke(state, config)
        messages = list(output.get("messages") or [])
        route = output.get("route")
        last_ai = _last_ai(messages)
        reply = strip_time_markers(_content(last_ai)) if last_ai else ""
        emotion = ""
        if last_ai is not None:
            emotion = str(last_ai.additional_kwargs.get("emotion") or "")
        if not emotion:
            emotion, _ = parse_emotion_tag(_content(last_ai)) if last_ai else ("", "")
        deltas = []

    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
    tool_messages = [message for message in messages if isinstance(message, ToolMessage)]
    return {
        "case_id": case["id"],
        "category": case.get("category", "unknown"),
        "input": case["input"],
        "reply": reply,
        "emotion": emotion,
        "route": route,
        "messages": messages,
        "tool_messages": tool_messages,
        "tool_names": [getattr(tool, "name", "") for tool in tools],
        "deltas": deltas,
        "elapsed_ms": elapsed_ms,
    }


def assert_expect(result: dict, expect: dict) -> None:
    '''按用例声明逐项断言，失败信息包含实际值'''
    context = f"case={result['case_id']} reply={result['reply']!r} route={result['route']!r}"

    if expect.get("route") is not None:
        assert result["route"] == expect["route"], f"路由不符：{context}"

    if expect.get("emotion"):
        assert result["emotion"] == expect["emotion"], f"情绪不符：{context}"

    messages = result["messages"]
    human = _first_human(messages)
    last_ai = _last_ai(messages)

    if expect.get("human_prefix"):
        assert human is not None and TIME_STATE_RE.search(_content(human)), \
            f"用户消息缺少时间前缀：{context}"

    if expect.get("ai_suffix"):
        assert last_ai is not None and TIME_TAIL_RE.search(_content(last_ai)), \
            f"AI 消息缺少时间后缀：{context}"

    tool_names = [message.name for message in result["tool_messages"]]
    if expect.get("tool_name"):
        assert expect["tool_name"] in tool_names, f"未调用预期工具：{context} tools={tool_names}"

    if expect.get("tool_content_contains"):
        assert any(
            expect["tool_content_contains"] in _content(message)
            for message in result["tool_messages"]
        ), f"工具结果未包含预期片段：{context}"

    if expect.get("no_tool"):
        for forbidden in expect["no_tool"]:
            assert forbidden not in tool_names, f"不应调用工具 {forbidden}：{context}"
            assert forbidden not in result["tool_names"], \
                f"工具白名单不应包含 {forbidden}：{result['tool_names']}"

    if expect.get("no_tool_messages"):
        assert not result["tool_messages"], f"不应出现工具消息：{context} tools={tool_names}"

    if expect.get("final_contains_any"):
        assert any(word in result["reply"] for word in expect["final_contains_any"]), \
            f"最终回复未命中关键词：{context}"

    if expect.get("forbid_in_final"):
        for term in expect["forbid_in_final"]:
            assert term not in result["reply"], f"最终回复含禁用词 {term}：{context}"

    if expect.get("deltas_clean"):
        joined = "".join(result["deltas"])
        assert not TIME_MARKER_RE.search(joined), f"流式增量含时间标记：{joined!r}"

    if expect.get("final_clean"):
        assert not TIME_MARKER_RE.search(result["reply"]), f"最终回复含时间标记：{context}"

    if expect.get("no_tech_terms"):
        for term in FORBIDDEN_TECH_TERMS:
            assert term not in result["reply"], f"最终回复含技术字样 {term}：{context}"
