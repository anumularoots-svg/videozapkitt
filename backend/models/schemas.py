"""Pydantic schemas for API requests and responses."""

from __future__ import annotations
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ── Auth ───────────────────────────────────────────────

class SignupRequest(BaseModel):
    email: str
    password: str
    name: Optional[str] = None


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ── Video Creation ─────────────────────────────────────

class CreateVideoRequest(BaseModel):
    """The only input a V1 user ever provides."""
    idea: str = Field(..., min_length=5, max_length=2000,
                      description="What the video should be about")
    language: str = Field(default="English", max_length=50)
    duration: int = Field(default=60, ge=15, le=60,
                          description="Video duration in seconds (30 or 60)")

    model_config = {"json_schema_extra": {
        "examples": [{
            "idea": "Explain Kubernetes to beginners",
            "language": "Telugu",
            "duration": 60
        }]
    }}


class ProjectResponse(BaseModel):
    id: UUID
    title: Optional[str]
    idea: str
    language: str
    duration: int
    status: str
    credits_used: int
    created_at: datetime

    model_config = {"from_attributes": True}


class ProjectStatusResponse(BaseModel):
    id: UUID
    status: str
    stage: str  # compiling, planning, generating, rendering, exporting
    progress: float  # 0.0 – 1.0
    scenes_completed: int
    scenes_total: int
    estimated_time_remaining: Optional[int] = None  # seconds
    download_url: Optional[str] = None


# ── Scene ──────────────────────────────────────────────

class SceneResponse(BaseModel):
    scene_number: int
    duration: float
    character_id: Optional[str]
    environment: Optional[str]
    emotion: Optional[str]
    camera_angle: Optional[str]
    status: str
    quality_check: Optional[str]

    model_config = {"from_attributes": True}


class RegenerateSceneRequest(BaseModel):
    project_id: UUID
    scene_number: int


# ── Blueprint ──────────────────────────────────────────

class SceneBlueprint(BaseModel):
    id: int
    duration: float
    character: str
    camera: str
    emotion: str
    environment: str
    voice: str
    music: str
    subtitle: str = ""
    prompt: str = ""
    transition: str = "fade"
    lighting: str = "natural"
    status: str = "pending"


class VideoBlueprint(BaseModel):
    """The source of truth for the entire video."""
    project_id: str
    version: int = 1
    video_type: str
    duration: int
    language: str
    style: str = "cinematic"
    aspect_ratio: str = "9:16"
    resolution: str = "1080x1920"
    fps: int = 24
    title: str = ""
    script: str = ""
    scenes: list[SceneBlueprint] = []
    characters_used: list[str] = []
    status: str = "draft"
    render_status: str = "pending"


# ── Credits ────────────────────────────────────────────

class CreditsResponse(BaseModel):
    credits_remaining: int
    plan: str
    videos_today: int
    max_videos_today: int
