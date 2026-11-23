'''M1 工具正确性用例：成功、空结果、白名单与不触发

所有工具均为本地假数据，断言聚焦 ToolMessage 名称/内容与最终回复是否引用结果。
'''
from langchain_core.messages import AIMessage

from evals.cases.tool_defs import get_weather, web_search
from evals.keywords import FAILURE_EXPLANATION_KEYWORDS

TOOL_CASES = [
    {
        "id": "tool_weather_success_01",
        "category": "tool",
        "description": "天气工具成功：ToolMessage 名称/片段正确，最终回复引用结果",
        "input": "北京今天天气怎么样？",
        "tools": [get_weather, web_search],
        "scripted_steps": [
            AIMessage(content="", tool_calls=[{
                "name": "get_weather", "args": {"city": "北京"}, "id": "call_weather_1",
            }]),
            AIMessage(content="[emotion:calm] 北京今天晴，25 度，出门散步刚刚好。"),
        ],
        "expect": {
            "tool_name": "get_weather",
            "tool_message_count": 1,
            "tool_content_contains": "晴",
            "bound_tools_contain": ["get_weather", "web_search"],
            "final_contains_any": ("晴", "25"),
            "no_tech_terms": True,
        },
    },
    {
        "id": "tool_weather_empty_02",
        "category": "tool",
        "description": "天气工具空结果：工具返回未查到，最终回复给出人格化提示",
        "input": "火星今天天气怎么样？",
        "tools": [get_weather],
        "scripted_steps": [
            AIMessage(content="", tool_calls=[{
                "name": "get_weather", "args": {"city": "火星"}, "id": "call_weather_2",
            }]),
            AIMessage(content="[emotion:worried] 抱歉，我好像没有查到火星的天气，换个城市试试？"),
        ],
        "expect": {
            "tool_name": "get_weather",
            "tool_message_count": 1,
            "tool_content_contains": "没有查到",
            "final_contains_any": FAILURE_EXPLANATION_KEYWORDS,
            "no_tech_terms": True,
        },
    },
    {
        "id": "tool_search_success_03",
        "category": "tool",
        "description": "搜索工具成功：ToolMessage 名称/片段正确，最终回复引用结果",
        "input": "LangGraph 是什么？",
        "tools": [get_weather, web_search],
        "scripted_steps": [
            AIMessage(content="", tool_calls=[{
                "name": "web_search", "args": {"query": "LangGraph 是什么"}, "id": "call_search_1",
            }]),
            AIMessage(content="[emotion:neutral] LangGraph 是用来构建有状态智能体的框架。"),
        ],
        "expect": {
            "tool_name": "web_search",
            "tool_message_count": 1,
            "tool_content_contains": "LangGraph",
            "final_contains_any": ("LangGraph", "框架"),
            "no_tech_terms": True,
        },
    },
    {
        "id": "tool_search_empty_04",
        "category": "tool",
        "description": "搜索工具空结果：工具返回无结果，最终回复给出替代建议",
        "input": "帮我搜一下不存在的问题",
        "tools": [web_search],
        "scripted_steps": [
            AIMessage(content="", tool_calls=[{
                "name": "web_search", "args": {"query": "不存在的问题"}, "id": "call_search_2",
            }]),
            AIMessage(content="[emotion:thinking] 我好像没找到相关内容，要不再换个关键词试试？"),
        ],
        "expect": {
            "tool_name": "web_search",
            "tool_message_count": 1,
            "tool_content_contains": "没有找到",
            "final_contains_any": FAILURE_EXPLANATION_KEYWORDS,
            "no_tech_terms": True,
        },
    },
    {
        "id": "tool_not_called_05",
        "category": "tool",
        "description": "普通聊天：工具已挂载但不应触发任何工具调用",
        "input": "今天有点累，陪我聊聊吧",
        "tools": [get_weather, web_search],
        "scripted_reply": "[emotion:relaxed] 我在呢，先歇一会儿，慢慢跟我说。",
        "expect": {
            "bound_tools_exact": ["get_weather", "web_search"],
            "tool_not_called": ["get_weather", "web_search"],
            "no_tool_messages": True,
            "final_contains_any": ("我在", "慢慢"),
        },
    },
]
