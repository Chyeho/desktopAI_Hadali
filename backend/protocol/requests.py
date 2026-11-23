'''请求体模型（HTTP JSON）'''
from pydantic import BaseModel, Field

# session_id 允许字符（防路径穿越）：1-64 位字母/数字/下划线/短横线
SESSION_ID_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"


class ChatRequest(BaseModel):
    '''POST /v1/chat 请求体'''
    session_id: str = Field(default="default", pattern=SESSION_ID_PATTERN)
    text: str = Field(min_length=1, description="用户输入")


class InterruptRequest(BaseModel):
    '''POST /v1/interrupt 请求体'''
    session_id: str = Field(default="default", pattern=SESSION_ID_PATTERN)
