'''M3 时间注入用例：state 前后缀、UI 流干净、时间工具隔离'''

TIME_CASES = [
    {
        "id": "time_state_prefix_suffix_01",
        "category": "time",
        "description": "state 层：用户消息带时间前缀，AI 回复带时间后缀",
        "input": "你好呀",
        "scripted_reply": "[emotion:happy] 我在呢，今天过得怎么样？",
        "streaming": False,
        "expect": {
            "human_prefix": True,
            "ai_suffix": True,
            "emotion": "happy",
        },
    },
    {
        "id": "time_stream_clean_02",
        "category": "time",
        "description": "UI 流层：流式增量与最终 reply 都不含时间标记",
        "input": "给我讲个睡前小故事吧",
        "scripted_reply": "[emotion:relaxed] 好呀，从前有一只小猫，喜欢在月光下散步。",
        "streaming": True,
        "expect": {
            "deltas_clean": True,
            "final_clean": True,
            "emotion": "relaxed",
        },
    },
    {
        "id": "time_tool_isolation_03",
        "category": "time",
        "description": "工具隔离：时间工具不暴露，询问时间也不会触发工具",
        "input": "现在几点了？",
        "scripted_reply": "[emotion:neutral] 我看不到钟表，不过我愿意陪你慢慢过。",
        "use_agent_tools": True,
        "expect": {
            "no_tool": ["get_current_time"],
            "no_tool_messages": True,
            "final_contains_any": ("陪你", "看不到", "慢慢"),
        },
    },
]
