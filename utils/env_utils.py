'''环境变量文件工具：轻量解析 .env，避免额外引入 python-dotenv

统一入口：core/facade、client/voice/tts 等模块共用，避免各处重复实现。
'''
import os


def load_env(env_path: str, missing_ok: bool = False) -> dict:
    '''解析 .env（key=value，跳过注释/空行与无等号行）

    参数：
        missing_ok: 文件不存在时返回空字典而不是抛 FileNotFoundError
    '''
    env = {}
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                env[key.strip()] = value.strip().strip('"').strip("'")
    except FileNotFoundError:
        if not missing_ok:
            raise
    return env
