"""
AI 对话模块
"""
import os

from openai import OpenAI

client = None
# 用于在流式调用中途异常时保留已生成的部分回复
last_partial_reply = ""


def init_api_key(inapi_key):
    global client
    client = OpenAI(
        base_url='https://api.deepseek.com/v1',
        api_key=inapi_key,  # DeepSeek API Key
    )


def init_api_key_from_env(env_path=None):
    """从 .env 文件读取 API_KEY 并初始化客户端"""
    if env_path is None:
        env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
    api_key = ""
    with open(env_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, _, value = line.partition('=')
            if key.strip() == 'API_KEY':
                api_key = value.strip().strip('"').strip("'")
                break
    if not api_key:
        raise ValueError(f"未在 {env_path} 中找到有效的 API_KEY")
    init_api_key(api_key)


# 初始化对话历史
messages = [
    {"role": "system", "content":
      '''
      需求：你是名字为哈达莉的AI助手。直接称用户为“用户”即可。
      回复文本格式要求：日常回复用户的文本长度一般不能超过100字。除非用户的提问比较复杂，需要详细解释。
      '''},  # 可自定义系统提示词
]


# 对话处理函数
def chat_with_model(user_input: str, temperature: float = 0.7, max_tokens: int = 200, on_chunk=None):
    # 1.将用户的输入添加到对话历史
    messages.append({"role": "user", "content": user_input})

    # 2.调用API
    response = client.chat.completions.create(
        model='deepseek-chat',
        messages=messages,  # 传递完整对话历史
        stream=True,
        temperature=temperature,  # 核心参数：控制随机性 (0.0-2.0)
        max_tokens=max_tokens,    # 限制生成长度
        top_p=0.9,                # 核心参数：核采样概率阈值
        presence_penalty=0.5,     # 降低重复话题概率
        frequency_penalty=0.3,    # 降低重复词汇概率
    )

    # 3.流式输出并收集模型回复
    global last_partial_reply
    full_reply = ""
    last_partial_reply = ""
    print("\n哈达莉: ", end="", flush=True)
    try:
        for chunk in response:
            # 某些 chunk（如终止 chunk）choices 可能为空，需判空避免 IndexError
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            content = getattr(delta, 'content', None)
            if content:
                print(content, end="", flush=True)
                full_reply += content
                last_partial_reply = full_reply
                if on_chunk:
                    on_chunk(content)
    except Exception:
        # 流式读取中途出错，保留已收集内容并向上抛出，由调用方决定是否使用
        last_partial_reply = full_reply
        raise

    # 4.将模型回复添加到历史对话
    messages.append({"role": "assistant", "content": full_reply})
    print("\n")  # 换行
    return full_reply
