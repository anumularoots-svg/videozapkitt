"""
AI Video Compiler — FastAPI Application

"Turn one idea into a cinematic 60-second Reel in any language."
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import structlog

from api import api_router
from config import get_settings

settings = get_settings()

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    logger = structlog.get_logger()
    logger.info("app.starting", env=settings.app_env)

    # Startup: ensure storage bucket exists
    from storage import S3Storage
    try:
        storage = S3Storage()
        storage.ensure_bucket()
        logger.info("app.storage_ready")
    except Exception as e:
        logger.warning("app.storage_not_ready", error=str(e))

    yield

    logger.info("app.shutdown")


app = FastAPI(
    title="AI Video Compiler",
    description="Turn one idea into a cinematic 60-second Reel in any language.",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — origins come from config (env-driven), not a hardcoded domain.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes
app.include_router(api_router)


@app.get("/health")
async def health():
    return {"status": "healthy", "version": "1.0.0"}
