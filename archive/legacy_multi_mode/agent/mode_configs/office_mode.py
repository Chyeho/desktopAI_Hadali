'''桌面办公 agent 模式配置（预留 stub，暂不实现具体逻辑）

后续扩展方式：
1. 在 tools/office/ 下实现办公独有工具；
2. 在下方 allowed_tools 加入工具名（公共工具也可按需加入）；
3. 完善 prompts/office_agent_prompt.txt；
4. UI 右键菜单调用 chatbot.switch_mode("office") 即可切换。
'''

MODE_CONFIG = {
    "name": "office",
    "display_name": "桌面办公",
    "system_prompt_path": "prompts/office_agent_prompt.txt",
    "allowed_tools": [],  # 办公模式独有工具待开发
    # 专业模式温度偏低，回复更稳定严谨
    "model_params": {
        "temperature": 0.3,
        "max_tokens": 2048,
        "top_p": 0.9,
        "presence_penalty": 0.0,
        "frequency_penalty": 0.3,
    },
}
