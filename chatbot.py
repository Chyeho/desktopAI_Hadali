"""
AI 对话模块

职责：
- 从 .env 文件读取 DeepSeek 的 API_KEY 并初始化 OpenAI 客户端
- 维护与 AI 的完整对话历史（messages 列表）
- 调用 DeepSeek 大模型，支持流式输出（可通过 on_chunk 回调逐块回传）

角色设定：哈达莉（由用户通过 system prompt 自定义）。
"""
import os

from openai import OpenAI

# 全局 OpenAI 客户端（由 init_api_key / init_api_key_from_env 初始化）
client = None

# 用于在流式调用中途异常时保留已生成的部分回复，
# 方便 UI 层在出错时优先展示已生成的内容而不是空白
last_partial_reply = ""


def init_api_key(inapi_key):
    """使用指定的 API Key 初始化 DeepSeek 客户端"""
    global client
    client = OpenAI(
        base_url='https://api.deepseek.com/v1',  # DeepSeek 兼容 OpenAI SDK 的接口地址
        api_key=inapi_key,  # DeepSeek API Key
    )


def init_api_key_from_env(env_path=None):
    """从 .env 文件读取 API_KEY 并初始化客户端

    参数 env_path：.env 文件路径，默认取本模块同目录下的 .env
    说明：手动解析格式简单的 .env（key=value），避免额外引入 python-dotenv 依赖。
    """
    if env_path is None:
        env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
    api_key = ""
    with open(env_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            # 跳过空行、注释行、以及格式不正确的行
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, _, value = line.partition('=')
            if key.strip() == 'API_KEY':
                # 去除值两侧的空白与可能包裹的引号
                api_key = value.strip().strip('"').strip("'")
                break
    if not api_key:
        raise ValueError(f"未在 {env_path} 中找到有效的 API_KEY")
    init_api_key(api_key)


# 对话历史：messages 会持续累积，作为上下文传给模型
# system 消息定义 AI 的角色身份与回复规范（可自定义系统提示词）
messages = [
    {"role": "system", "content":
      '''
      需求：你是名字为哈达莉的AI助手。直接称用户为“用户”即可。
      回复文本格式要求：日常回复用户的文本长度一般不能超过100字。除非用户的提问比较复杂，需要详细解释。
      '''},
]


# 对话处理函数
def chat_with_model(user_input: str, temperature: float = 0.7, max_tokens: int = 200, on_chunk=None):
    """调用 DeepSeek 大模型进行一次对话，返回完整回复文本

    参数：
        user_input : 用户输入的内容
        temperature: 采样温度 (0.0-2.0)，越大回复越随机
        max_tokens : 单次生成的最大 token 数
        on_chunk   : 可选回调 on_chunk(content)，每生成一块内容就会被调用一次（流式）
    """
    # 1. 将用户的输入添加到对话历史
    messages.append({"role": "user", "content": user_input})

    # 2. 调用 API（stream=True 开启流式输出）
    response = client.chat.completions.create(
        model='deepseek-chat',
        messages=messages,      # 传递完整对话历史，让 AI 记住上下文
        stream=True,
        temperature=temperature,   # 核心参数：控制随机性 (0.0-2.0)
        max_tokens=max_tokens,     # 限制生成长度
        top_p=0.9,                 # 核心参数：核采样概率阈值
        presence_penalty=0.5,      # 降低重复话题概率
        frequency_penalty=0.3,     # 降低重复词汇概率
    )

    # 3. 流式读取并收集模型回复
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
                print(content, end="", flush=True)   # 终端实时打印
                full_reply += content                # 累积完整回复
                last_partial_reply = full_reply      # 记录进度（出错时用）
                if on_chunk:                         # 若 UI 需要流式回显，则回调
                    on_chunk(content)
    except Exception:
        # 流式读取中途出错，保留已收集内容并向上抛出，由调用方决定是否使用
        last_partial_reply = full_reply
        raise

    # 4. 将模型回复添加到历史对话（AI 也记住自己说过的话）
    messages.append({"role": "assistant", "content": full_reply})
    print("\n")  # 换行
    return full_reply
