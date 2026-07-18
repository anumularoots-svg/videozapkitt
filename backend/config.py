"""Central configuration loaded from environment variables."""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # App
    app_name: str = "ai-video-compiler"
    app_env: str = "development"
    debug: bool = True
    secret_key: str = "change-me"
    api_version: str = "v1"

    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@db:5432/video_compiler"
    database_sync_url: str = "postgresql://postgres:postgres@db:5432/video_compiler"

    # Redis
    redis_url: str = "redis://redis:6379/0"
    celery_result_backend: str = "redis://redis:6379/2"

    # Celery broker: "sqs" in prod (the GPU ASG scales on SQS depth), "redis"
    # for local docker-compose (no SQS locally). docker-compose sets
    # CELERY_BROKER=redis; the default is sqs so a real deploy needs no override.
    celery_broker: str = "sqs"
    celery_broker_url: str = "redis://redis:6379/1"  # used only when celery_broker=redis

    # CORS: who may call the API from a browser. Env-driven -- never hardcode a
    # domain in main.py. Prod sets this to the real origin.
    cors_origins: list[str] = ["http://localhost:3000", "https://dev-video.zapkitt.com"]

    # AWS / Storage
    # aws_region drives both S3 and the SQS Celery broker. On EC2 the worker
    # authenticates to SQS via its IAM role, so no keys live here.
    aws_region: str = "ap-south-1"
    video_queue_url: str = ""
    s3_endpoint: str = "http://minio:9000"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_bucket: str = "video-compiler"
    s3_region: str = "us-east-1"

    # ── AI Models ──────────────────────────────────────
    # Licenses are enforced in code (providers/base.py::License). These defaults
    # are all commercial-safe. See ARCHITECTURE.md §2 before changing any of them.

    # LLM: Groq free tier at Phase 0; point at self-hosted vLLM later.
    llm_model: str = "llama-3.3-70b-versatile"
    llm_api_url: str = "https://api.groq.com/openai/v1"
    llm_api_key: str = ""

    # Image: SCHNELL (Apache-2.0), never DEV (non-commercial).
    image_model: str = "black-forest-labs/FLUX.1-schnell"

    # Video: 1.3B (~8.2GB VRAM) at Phase 0. The 14B needs 40-48GB at 480p and
    # 5-10x the spend -- that is a Phase 6 decision, made with real data.
    # "-Diffusers" repo: WanPipeline loads the diffusers-format layout, not the
    # original Wan checkpoint.
    video_model: str = "Wan-AI/Wan2.1-T2V-1.3B-Diffusers"

    # Voice: Kokoro is English-only here by design. Telugu/Hindi land at Phase 2
    # via IndicF5 (MIT). Kokoro has no Telugu at all and only thin Hindi.
    voice_model: str = "kokoro"
    tts_device: str = "cpu"

    whisper_model_size: str = "base"
    whisper_device: str = "cpu"

    # Translation (Phase 2). IndicTrans2 (MIT, AI4Bharat) -- NOT NLLB. The NLLB
    # distilled model is CC-BY-NC (non-commercial), which the license gate would
    # (correctly) reject in a commercial path. IndicTrans2 also beats NLLB on
    # Indian-language benchmarks. Provider lands with Phase 2.
    translation_model: str = "ai4bharat/indictrans2-en-indic-1B"

    # GPU
    gpu_device: str = "cuda"
    gpu_worker_count: int = 1
    max_concurrent_renders: int = 2

    # Video
    max_video_duration: int = 60
    default_aspect_ratio: str = "9:16"
    default_resolution: str = "1080x1920"
    default_fps: int = 24

    # Rate Limits
    free_videos_per_day: int = 3
    free_max_duration: int = 30

    # Auth
    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    jwt_expiry_hours: int = 24

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
