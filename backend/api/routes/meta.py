'''元信息路由：GET /v1/health'''
from fastapi import APIRouter, Depends

from backend.api.security import verify_token
from backend.api.services import SERVER_VERSION, Services, get_services

router = APIRouter(prefix="/v1", dependencies=[Depends(verify_token)])


@router.get("/health")
async def health(services: Services = Depends(get_services)):
    '''探活：返回状态、版本与当前模型名'''
    return {"status": "ok", "version": SERVER_VERSION, "model": services.model_name}
