from fastapi import APIRouter
from .routes.auth import router as auth_router
from .routes.video import router as video_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth_router)
api_router.include_router(video_router)
