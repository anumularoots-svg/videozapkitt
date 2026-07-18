"""SQLAlchemy database models."""

import uuid
from datetime import datetime

from sqlalchemy import (
    Column, String, Integer, Float, Text, Boolean, DateTime,
    ForeignKey, JSON, Enum as SQLEnum,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


# ── Users ──────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    name = Column(String(100))
    credits = Column(Integer, default=10)
    plan = Column(String(20), default="free")  # free, starter, pro, business
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    projects = relationship("Project", back_populates="user")


# ── Projects ───────────────────────────────────────────

class Project(Base):
    __tablename__ = "projects"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    title = Column(String(255))
    idea = Column(Text, nullable=False)
    language = Column(String(50), default="English")
    duration = Column(Integer, default=60)  # seconds
    style = Column(String(50), default="cinematic")
    video_type = Column(String(50), default="story")
    aspect_ratio = Column(String(10), default="9:16")
    status = Column(String(20), default="created")
    # created → compiling → planning → generating → rendering → completed → failed
    credits_used = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="projects")
    blueprints = relationship("Blueprint", back_populates="project")
    scenes = relationship("Scene", back_populates="project")


# ── Blueprints (versioned) ─────────────────────────────

class Blueprint(Base):
    __tablename__ = "blueprints"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    version = Column(Integer, default=1)
    dsl_text = Column(Text)  # The Video DSL representation
    blueprint_json = Column(JSON)  # Full blueprint
    is_active = Column(Boolean, default=True)
    status = Column(String(20), default="draft")
    # draft → validated → optimized → executing → completed → failed
    created_at = Column(DateTime, default=datetime.utcnow)

    project = relationship("Project", back_populates="blueprints")


# ── Scenes ─────────────────────────────────────────────

class Scene(Base):
    __tablename__ = "scenes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    blueprint_id = Column(UUID(as_uuid=True), ForeignKey("blueprints.id"))
    scene_number = Column(Integer, nullable=False)
    duration = Column(Float)  # seconds
    character_id = Column(String(50))
    camera_angle = Column(String(50))
    emotion = Column(String(50))
    environment = Column(String(100))
    voice_type = Column(String(50))
    music_type = Column(String(50))
    prompt = Column(Text)
    script_text = Column(Text)
    subtitle_text = Column(Text)
    status = Column(String(20), default="pending")
    # pending → generating → completed → failed
    retry_count = Column(Integer, default=0)
    quality_check = Column(String(10))  # PASS / FAIL

    # Generated asset paths (S3 keys)
    video_path = Column(String(500))
    audio_path = Column(String(500))
    subtitle_path = Column(String(500))
    image_path = Column(String(500))

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    project = relationship("Project", back_populates="scenes")


# ── Characters ─────────────────────────────────────────

class Character(Base):
    __tablename__ = "characters"

    id = Column(String(50), primary_key=True)  # e.g. "narrator_01"
    name = Column(String(100), nullable=False)
    gender = Column(String(20))
    age_range = Column(String(20))  # young, adult, senior
    style = Column(String(50))  # cinematic, corporate, anime
    voice_id = Column(String(50))
    language_support = Column(JSON)  # ["en", "te", "hi", ...]
    supported_styles = Column(JSON)
    reference_images_path = Column(String(500))  # S3 prefix
    metadata = Column(JSON)
    is_active = Column(Boolean, default=True)


# ── Video Exports ──────────────────────────────────────

class VideoExport(Base):
    __tablename__ = "video_exports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    blueprint_version = Column(Integer)
    resolution = Column(String(20))
    file_path = Column(String(500))
    file_size = Column(Integer)  # bytes
    duration = Column(Float)
    render_time = Column(Float)  # seconds it took to render
    gpu_cost = Column(Float)
    status = Column(String(20), default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)
