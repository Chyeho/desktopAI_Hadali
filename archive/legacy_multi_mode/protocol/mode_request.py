'''ModeRequest 归档副本（原位于 backend/protocol/requests.py）

仅供恢复旧多模式接口时参考，不属于活跃导入路径。
'''
from pydantic import BaseModel, Field


class ModeRequest(BaseModel):
    '''POST /v1/mode 请求体'''
    mode: str = Field(min_length=1)
