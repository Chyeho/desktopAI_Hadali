'''FastAPI 应用工厂

测试通过 `create_app(services=FakeServices())` 注入假服务，无需真实 .env / 模型。
'''
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from backend.api.routes import chat, meta
from backend.api.services import SERVER_VERSION, Services


def create_app(services: Services = None) -> FastAPI:
    app = FastAPI(title="Hadali Server", version=SERVER_VERSION)
    app.state.services = services or Services()

    app.include_router(meta.router)
    app.include_router(chat.router)

    @app.exception_handler(RequestValidationError)
    async def _on_validation_error(request: Request, exc: RequestValidationError):
        '''协议约定参数非法返回 400（FastAPI 默认 422）'''
        return JSONResponse(
            status_code=400,
            content={"code": "BAD_REQUEST", "message": "请求参数非法"},
        )

    return app
