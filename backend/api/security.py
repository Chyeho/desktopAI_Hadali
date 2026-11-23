'''本地 token 鉴权

client 拉起 server 时用 `secrets.token_urlsafe(32)` 生成 token，经环境变量
`HADALI_TOKEN` 传入；未配置 token 时放行（独立调试场景），并只打一条 warning。
'''
import os
import secrets

from fastapi import Header, HTTPException

from utils.logger_handler import logger

_warned = False


def verify_token(x_hadali_token: str = Header(default=None)) -> None:
    '''FastAPI 依赖：校验 X-Hadali-Token 请求头'''
    global _warned
    expected = os.environ.get("HADALI_TOKEN", "")
    if not expected:
        if not _warned:
            logger.warning("[server.security]未配置 HADALI_TOKEN，接口仅建议在本机调试时使用")
            _warned = True
        return
    if not x_hadali_token or not secrets.compare_digest(x_hadali_token, expected):
        raise HTTPException(
            status_code=401,
            detail={"code": "UNAUTHORIZED", "message": "token 校验失败"},
        )
