'''一轮对话的结构化结果类型

从 `chat_agent.py` 抽出：主图 runner、server、tracing 与 legacy 引擎共用，
避免公共类型随旧引擎一起被归档。
'''
from typing import TypedDict


class ToolCallRecord(TypedDict):
    '''一次工具调用的结构化记录'''
    name: str            # 工具名
    args: dict           # 模型给出的入参
    ok: bool             # 是否执行成功
    duration_ms: float   # 执行耗时（毫秒）


class TurnResult(TypedDict):
    '''一轮对话的结构化结果（运行时即普通 dict，便于序列化与向后兼容）'''
    emotion: str                    # 情感标签（已校验，非法值回退 neutral）
    reply: str                      # 剥离情感标签后的回复文本
    mode: str                       # 本轮使用的 agent 模式名
    steps: int                      # 实际模型调用轮数
    tool_calls: list[ToolCallRecord]  # 本轮工具调用记录
    latency_ms: float               # 整轮耗时（毫秒）
