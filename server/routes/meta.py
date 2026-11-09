'''元信息路由：GET /v1/health、GET /v1/modes、POST /v1/mode'''
from fastapi import APIRouter, Depends, HTTPException

from protocol.requests import ModeRequest
from server.security import verify_token
from server.services import SERVER_VERSION, Services, get_services

router = APIRouter(prefix="/v1", dependencies=[Depends(verify_token)])


@router.get("/health")
async def health(services: Services = Depends(get_services)):
    '''探活：返回状态、版本与当前模型名'''
    return {"status": "ok", "version": SERVER_VERSION, "model": services.model_name}


@router.get("/modes")
async def modes(services: Services = Depends(get_services)):
    '''模式列表与当前进程级模式'''
    return {"current": services.current_mode, "modes": services.list_modes()}


@router.post("/mode")
async def set_mode(req: ModeRequest, services: Services = Depends(get_services)):
    '''切换进程级当前模式'''
    try:
        services.set_mode(req.mode)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": "BAD_REQUEST", "message": str(exc)},
        )
    return {"ok": True, "current": services.current_mode}
