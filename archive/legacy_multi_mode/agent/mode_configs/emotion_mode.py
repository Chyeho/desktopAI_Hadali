'''日常情感陪伴主模式（桌宠默认模式）配置'''

MODE_CONFIG = {
    # 模式标识
    "name": "emotion",
    "display_name": "情感陪伴",
    # 该模式的系统提示词路径（相对项目根目录）
    "system_prompt_path": "prompts/system_prompt.txt",
    # 工具白名单：仅允许调用以下工具（工具名 = tools/ 下 @tool 函数名）
    "allowed_tools": ["get_weather", "web_search"],
    # 大模型生成参数（温度偏高，回复更自然有变化）
    "model_params": {
        "temperature": 0.7,
        "max_tokens": 1024,
        "top_p": 0.9,
        "presence_penalty": 0.5,
        "frequency_penalty": 0.3,
    },
}
