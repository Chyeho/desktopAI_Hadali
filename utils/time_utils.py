'''时间相关纯函数：格式化、消息前后缀、前缀/后缀剥离

设计约束：
- 不依赖 LangChain，也不读取环境变量，全部通过参数注入，便于测试；
- 时间格式由调用方传入（默认 `%Y-%m-%d %H:%M`），图引擎从配置读取后传入。
'''
import re
from datetime import datetime

# 默认时间格式：与执行文档约定一致
DEFAULT_TIME_FORMAT = "%Y-%m-%d %H:%M"

# 用户消息前缀：[2026-11-21 14:30] 用户原话
_USER_PREFIX_RE = re.compile(r"^\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}\]\s*")
# AI 消息后缀：回复正文 [2026-11-21 14:31]
_REPLY_SUFFIX_RE = re.compile(r"\s*\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}\]\s*$")


def now_str(dt: datetime | None = None, fmt: str = DEFAULT_TIME_FORMAT) -> str:
    '''返回格式化后的当前时间；dt 可注入，便于测试'''
    return (dt or datetime.now()).strftime(fmt)


def strip_user_time(text: str) -> str:
    '''去掉用户消息开头的时间前缀；无前缀时原样返回'''
    return _USER_PREFIX_RE.sub("", text or "")


def strip_reply_time(text: str) -> str:
    '''去掉 AI 消息末尾的时间后缀；无后缀时原样返回'''
    return _REPLY_SUFFIX_RE.sub("", text or "").rstrip()


def with_user_time(text: str, dt: datetime | None = None,
                   fmt: str = DEFAULT_TIME_FORMAT) -> str:
    '''给用户消息加时间前缀；重复调用不会叠加'''
    return f"[{now_str(dt, fmt)}] {strip_user_time(text)}"


def with_reply_time(reply: str, dt: datetime | None = None,
                    fmt: str = DEFAULT_TIME_FORMAT) -> str:
    '''给 AI 回复加时间后缀；重复调用不会叠加'''
    return f"{strip_reply_time(reply)} [{now_str(dt, fmt)}]"
