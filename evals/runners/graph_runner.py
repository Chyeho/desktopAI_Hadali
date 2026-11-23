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

from agent.history import HistoryStore
from agent.expression_driver import VALID_EMOTIONS
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


def _build_graph(llm: Any, tools: list):
    return build_main_graph(llm, system_prompt=EVAL_SYSTEM_PROMPT, tools=tools)


def run_case(case: dict) -> dict:
    '''执行一条用例并返回结构化结果'''
    streaming = bool(case.get("streaming"))
    steps = case.get("scripted_steps") or [case.get("scripted_reply", "")]
    llm = ScriptedLLM(steps, streaming=streaming)
    tools = _resolve_tools(case)
    graph = _build_graph(llm, tools)

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


def run_memory_case(case: dict, history_file: str) -> dict:
    '''执行一条记忆用例：第一实例写入历史，第二实例从 JSON 恢复后对话

    - 只断言"模型实际收到的消息"，不依赖具体模型措辞；
    - 第二实例使用全新图与 MemorySaver，模拟进程重启。
    '''
    tools = _resolve_tools(case)
    session_id = case.get("session_id") or f"eval-memory-{uuid.uuid4().hex}"

    if case.get("seed_history"):
        # 直接构造历史文件：用于回归"恢复时剥离 tool 中间消息"
        store = HistoryStore(file_path=history_file)
        store.messages = list(case["seed_history"])
        store.save()
    else:
        first_llm = ScriptedLLM(case.get("first_steps") or [])
        first_agent = CompanionGraphAgent(
            graph=_build_graph(first_llm, tools), history_file=history_file
        )
        for text in case.get("first_turns") or []:
            first_agent.chat(text, session_id=session_id)

    second_llm = ScriptedLLM(case.get("second_steps") or [])
    second_agent = CompanionGraphAgent(
        graph=_build_graph(second_llm, tools), history_file=history_file
    )
    done = second_agent.chat(case["input"], session_id=session_id)

    injected = list(second_llm.calls[0]) if second_llm.calls else []
    return {
        "case_id": case["id"],
        "category": case.get("category", "unknown"),
        "input": case["input"],
        "reply": done.get("reply", ""),
        "emotion": done.get("emotion", ""),
        "route": None,
        "messages": injected,
        "tool_messages": [m for m in injected if isinstance(m, ToolMessage)],
        "tool_names": [getattr(tool, "name", "") for tool in tools],
        "deltas": [],
        "restored_contents": [_content(m) for m in injected],
        "restored_tool_count": sum(isinstance(m, ToolMessage) for m in injected),
        "restored_tool_call_count": sum(
            1 for m in injected
            if isinstance(m, AIMessage) and getattr(m, "tool_calls", None)
        ),
        "elapsed_ms": 0.0,
    }


def _fail(field: str, expected: Any, actual: Any, result: dict) -> None:
    '''统一失败信息：保留断言字段、期望值与实际值，便于从报告定位'''
    context = (
        f"case={result.get('case_id')} reply={result.get('reply')!r} "
        f"route={result.get('route')!r}"
    )
    raise AssertionError(f"[{field}] 期望={expected!r} 实际={actual!r} | {context}")


def assert_expect(result: dict, expect: dict) -> None:
    '''按用例声明逐项断言，失败信息包含断言字段、期望值与实际值'''
    if expect.get("route") is not None and result["route"] != expect["route"]:
        _fail("route", expect["route"], result["route"], result)

    if expect.get("emotion") and result["emotion"] != expect["emotion"]:
        _fail("emotion", expect["emotion"], result["emotion"], result)

    if expect.get("emotion_valid") and result["emotion"] not in VALID_EMOTIONS:
        _fail("emotion_valid", sorted(VALID_EMOTIONS), result["emotion"], result)

    messages = result["messages"]
    human = _first_human(messages)
    last_ai = _last_ai(messages)

    if expect.get("human_prefix"):
        actual = _content(human) if human is not None else None
        if not (human is not None and TIME_STATE_RE.search(actual)):
            _fail("human_prefix", "用户消息以 [YYYY-MM-DD HH:MM] 开头", actual, result)

    if expect.get("ai_suffix"):
        actual = _content(last_ai) if last_ai is not None else None
        if not (last_ai is not None and TIME_TAIL_RE.search(actual)):
            _fail("ai_suffix", "AI 消息以 [YYYY-MM-DD HH:MM] 结尾", actual, result)

    executed_tools = [message.name for message in result["tool_messages"]]
    if expect.get("tool_name") and expect["tool_name"] not in executed_tools:
        _fail("tool_name", expect["tool_name"], executed_tools, result)

    if expect.get("tool_message_count") is not None:
        expected_count = expect["tool_message_count"]
        if len(executed_tools) != expected_count:
            _fail("tool_message_count", expected_count, executed_tools, result)

    if expect.get("tool_content_contains"):
        contents = [_content(message) for message in result["tool_messages"]]
        if not any(expect["tool_content_contains"] in text for text in contents):
            _fail("tool_content_contains", expect["tool_content_contains"], contents, result)

    if expect.get("tool_status_error"):
        statuses = [getattr(message, "status", None) for message in result["tool_messages"]]
        if "error" not in statuses:
            _fail("tool_status_error", "至少一条 ToolMessage.status=error", statuses, result)

    if expect.get("no_tool"):
        for forbidden in expect["no_tool"]:
            if forbidden in executed_tools:
                _fail("no_tool(executed)", forbidden, executed_tools, result)
            if forbidden in result["tool_names"]:
                _fail("no_tool(whitelist)", forbidden, result["tool_names"], result)

    if expect.get("tool_not_called"):
        for name in expect["tool_not_called"]:
            if name in executed_tools:
                _fail("tool_not_called", name, executed_tools, result)

    if expect.get("bound_tools_contain"):
        for name in expect["bound_tools_contain"]:
            if name not in result["tool_names"]:
                _fail("bound_tools_contain", name, result["tool_names"], result)

    if expect.get("bound_tools_exact") is not None:
        expected = sorted(expect["bound_tools_exact"])
        if sorted(result["tool_names"]) != expected:
            _fail("bound_tools_exact", expected, sorted(result["tool_names"]), result)

    if expect.get("no_tool_messages"):
        if result["tool_messages"]:
            _fail("no_tool_messages", "无工具消息", executed_tools, result)

    if expect.get("final_contains_any"):
        if not any(word in result["reply"] for word in expect["final_contains_any"]):
            _fail("final_contains_any", expect["final_contains_any"], result["reply"], result)

    if expect.get("forbid_in_final"):
        for term in expect["forbid_in_final"]:
            if term in result["reply"]:
                _fail("forbid_in_final", f"不含 {term}", result["reply"], result)

    if expect.get("deltas_clean"):
        joined = "".join(result["deltas"])
        if TIME_MARKER_RE.search(joined):
            _fail("deltas_clean", "流式增量不含时间标记", joined, result)

    if expect.get("deltas_join_equals_reply"):
        joined = "".join(result["deltas"])
        if joined != result["reply"]:
            _fail("deltas_join_equals_reply", result["reply"], joined, result)

    if expect.get("deltas_no_emotion_tag"):
        joined = "".join(result["deltas"])
        if "[emotion" in joined:
            _fail("deltas_no_emotion_tag", "流式增量不含情绪标签", joined, result)

    if expect.get("final_clean"):
        if TIME_MARKER_RE.search(result["reply"]):
            _fail("final_clean", "最终回复不含时间标记", result["reply"], result)

    if expect.get("no_tech_terms"):
        for term in FORBIDDEN_TECH_TERMS:
            if term in result["reply"]:
                _fail("no_tech_terms", f"不含 {term}", result["reply"], result)

    if expect.get("restored_contains_all"):
        joined = "\n".join(result.get("restored_contents") or [])
        for word in expect["restored_contains_all"]:
            if word not in joined:
                _fail("restored_contains_all", word, joined, result)

    if expect.get("restored_no_tool_messages"):
        if result.get("restored_tool_count"):
            _fail("restored_no_tool_messages", 0, result.get("restored_tool_count"), result)

    if expect.get("restored_no_tool_calls"):
        if result.get("restored_tool_call_count"):
            _fail("restored_no_tool_calls", 0, result.get("restored_tool_call_count"), result)
