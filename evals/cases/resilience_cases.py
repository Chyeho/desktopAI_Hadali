'''M4 容错用例：工具异常转 ToolMessage、错误文本人格化、失败后重试

断言重点：
- 图不抛异常（能跑完用例即证明）；
- ToolMessage 携带错误信息且 status=error；
- 最终回复命中失败解释词，且不含技术字样。
'''
from langchain_core.messages import AIMessage

from evals.cases.tool_defs import broken_weather, flaky_weather, get_weather
from evals.keywords import FAILURE_EXPLANATION_KEYWORDS

RESILIENCE_CASES = [
    {
        "id": "resilience_tool_raises_01",
        "category": "resilience",
        "description": "工具抛异常：图不中断，ToolMessage 标记 error，最终回复人格化且无技术字样",
        "input": "帮我看看北京天气",
        "tools": [broken_weather],
        "scripted_steps": [
            AIMessage(content="", tool_calls=[{
                "name": "broken_weather", "args": {"city": "北京"}, "id": "call_boom_1",
            }]),
            AIMessage(content="[emotion:worried] 抱歉，刚才查天气出了点小问题，等会儿再帮你试试好不好？"),
        ],
        "expect": {
            "tool_name": "broken_weather",
            "tool_message_count": 1,
            "tool_status_error": True,
            "tool_content_contains": "weather service unavailable",
            "final_contains_any": FAILURE_EXPLANATION_KEYWORDS,
            "forbid_in_final": ("RuntimeError", "weather service unavailable"),
            "no_tech_terms": True,
        },
    },
    {
        "id": "resilience_tool_error_text_02",
        "category": "resilience",
        "description": "工具返回错误文本：最终回复用陪伴式解释而不是复述报错",
        "input": "查一下北京天气",
        "tools": [flaky_weather],
        "scripted_steps": [
            AIMessage(content="", tool_calls=[{
                "name": "flaky_weather", "args": {"city": "北京"}, "id": "call_flaky_1",
            }]),
            AIMessage(content="[emotion:worried] 暂时没能查到天气，稍后再帮你看看，好不好？"),
        ],
        "expect": {
            "tool_name": "flaky_weather",
            "tool_content_contains": "服务暂时不可用",
            "final_contains_any": FAILURE_EXPLANATION_KEYWORDS,
            "forbid_in_final": ("查询失败", "暂时不可用"),
            "no_tech_terms": True,
        },
    },
    {
        "id": "resilience_retry_after_failure_03",
        "category": "resilience",
        "description": "首次工具失败后重试成功：两条 ToolMessage，最终回复给出结果",
        "input": "北京天气怎么样？",
        "tools": [broken_weather, get_weather],
        "scripted_steps": [
            AIMessage(content="", tool_calls=[{
                "name": "broken_weather", "args": {"city": "北京"}, "id": "call_retry_1",
            }]),
            AIMessage(content="", tool_calls=[{
                "name": "get_weather", "args": {"city": "北京"}, "id": "call_retry_2",
            }]),
            AIMessage(content="[emotion:calm] 这次查到啦，北京今天晴，25 度。"),
        ],
        "expect": {
            "tool_message_count": 2,
            "tool_content_contains": "晴",
            "final_contains_any": ("查到", "晴", "25"),
            "no_tech_terms": True,
        },
    },
]
