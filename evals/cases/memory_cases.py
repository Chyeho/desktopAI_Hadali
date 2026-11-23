'''M6 记忆用例：跨实例恢复历史、恢复时剥离 tool 中间消息

断言对象是"模型实际收到的消息"，避免依赖措辞；每条用例使用独立临时 history 文件。
'''
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from evals.cases.tool_defs import get_weather

MEMORY_CASES = [
    {
        "id": "memory_restore_01",
        "category": "memory",
        "description": "两轮对话（含工具）后新实例恢复：历史注入且工具中间消息被剥离",
        "tools": [get_weather],
        "first_turns": ["我叫小林", "帮我查下北京天气"],
        "first_steps": [
            AIMessage(content="[emotion:happy] 记住啦，小林。"),
            AIMessage(content="", tool_calls=[{
                "name": "get_weather", "args": {"city": "北京"}, "id": "call_mem_1",
            }]),
            AIMessage(content="[emotion:calm] 北京今天晴，25 度。"),
        ],
        "input": "我叫什么名字？",
        "second_steps": ["[emotion:happy] 你叫小林呀，我记得的。"],
        "expect": {
            "restored_contains_all": ("我叫小林", "记住啦", "北京今天晴"),
            "restored_no_tool_messages": True,
            "restored_no_tool_calls": True,
            "final_contains_any": ("小林",),
        },
    },
    {
        "id": "memory_orphan_tool_filtered_02",
        "category": "memory",
        "description": "历史残留 tool 中间消息：恢复时过滤，避免 role=tool 非法请求",
        "seed_history": [
            HumanMessage(content="[2026-11-21 10:00] 今天天气怎么样"),
            AIMessage(content="", tool_calls=[{
                "name": "get_weather", "args": {"city": "北京"}, "id": "call_seed_1",
            }]),
            ToolMessage(content="晴，25 度", tool_call_id="call_seed_1"),
            AIMessage(content="今天北京晴，25 度 [2026-11-21 10:00]"),
        ],
        "input": "那明天呢？",
        "second_steps": ["[emotion:thinking] 明天应该也是晴天，记得带件外套。"],
        "expect": {
            "restored_contains_all": ("今天天气怎么样", "今天北京晴"),
            "restored_no_tool_messages": True,
            "restored_no_tool_calls": True,
            "final_contains_any": ("明天", "外套"),
        },
    },
]
