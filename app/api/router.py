"""
Top-level API router — mounts all sub-routers.
"""
from fastapi import APIRouter

from app.api.routes.agent import router as agent_router
from app.api.routes.health import router as health_router
from app.api.routes.system_metrics import router as system_metrics_router
from app.api.routes.ws import router as ws_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(agent_router)
api_router.include_router(system_metrics_router)
api_router.include_router(ws_router)
