"""
Video API Routes

The V1 API surface is intentionally small:
  POST /video/create       - Create a video from an idea
  GET  /video/status/{id}  - Check generation progress
  GET  /video/project/{id} - Get project details
  POST /video/regenerate   - Regenerate a failed scene
  GET  /video/download/{id} - Download the final video
  GET  /video/credits      - Check remaining credits
"""

from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from models import (
    Project, Blueprint, Scene,
    CreateVideoRequest, ProjectResponse, ProjectStatusResponse,
    RegenerateSceneRequest, CreditsResponse,
)
from services.database import get_db
from workers.tasks import compile_video

router = APIRouter(prefix="/video", tags=["video"])


@router.post("/create", response_model=ProjectResponse)
async def create_video(req: CreateVideoRequest, db: AsyncSession = Depends(get_db)):
    """
    Create a new video.

    This is the primary endpoint. The user provides:
    - idea: What the video should be about
    - language: Target language
    - duration: 30 or 60 seconds

    Everything else is handled by the AI Video Compiler.
    """
    project = Project(
        id=uuid4(),
        user_id=uuid4(),  # TODO: get from auth
        title=req.idea[:100],
        idea=req.idea,
        language=req.language,
        duration=req.duration,
        status="compiling",
    )
    db.add(project)
    await db.flush()

    # Submit to the compilation pipeline
    compile_video.delay(
        project_id=str(project.id),
        idea=req.idea,
        language=req.language,
        duration=req.duration,
    )

    return ProjectResponse(
        id=project.id,
        title=project.title,
        idea=project.idea,
        language=project.language,
        duration=project.duration,
        status=project.status,
        credits_used=0,
        created_at=project.created_at,
    )


@router.get("/status/{project_id}", response_model=ProjectStatusResponse)
async def get_status(project_id: UUID, db: AsyncSession = Depends(get_db)):
    """Check the generation progress of a video."""
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Count completed scenes
    scene_result = await db.execute(
        select(Scene).where(Scene.project_id == project_id)
    )
    scenes = scene_result.scalars().all()
    completed = sum(1 for s in scenes if s.status == "completed")

    # Determine current stage from status
    stage_map = {
        "created": "compiling",
        "compiling": "compiling",
        "planning": "planning",
        "generating": "generating",
        "rendering": "rendering",
        "completed": "completed",
        "failed": "failed",
    }

    return ProjectStatusResponse(
        id=project.id,
        status=project.status,
        stage=stage_map.get(project.status, "unknown"),
        progress=completed / max(len(scenes), 1),
        scenes_completed=completed,
        scenes_total=len(scenes),
        download_url=None,  # Set when completed
    )


@router.get("/project/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: UUID, db: AsyncSession = Depends(get_db)):
    """Get full project details."""
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    return ProjectResponse.model_validate(project)


@router.post("/regenerate-scene")
async def regenerate_scene(
    req: RegenerateSceneRequest,
    db: AsyncSession = Depends(get_db),
):
    """Regenerate a single failed scene (not the whole video)."""
    result = await db.execute(
        select(Scene).where(
            Scene.project_id == req.project_id,
            Scene.scene_number == req.scene_number,
        )
    )
    scene = result.scalar_one_or_none()
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")

    scene.status = "pending"
    scene.retry_count += 1
    await db.flush()

    # TODO: submit scene regeneration to worker queue
    return {"status": "regenerating", "scene_number": req.scene_number}


@router.get("/download/{project_id}")
async def download_video(project_id: UUID, db: AsyncSession = Depends(get_db)):
    """Get the download URL for a completed video."""
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.status != "completed":
        raise HTTPException(status_code=400, detail="Video not ready yet")

    # TODO: generate presigned S3 URL
    return {"download_url": f"/api/v1/files/{project_id}/final.mp4"}


@router.get("/credits", response_model=CreditsResponse)
async def get_credits(db: AsyncSession = Depends(get_db)):
    """Check remaining credits."""
    # TODO: get user from auth token
    return CreditsResponse(
        credits_remaining=10,
        plan="free",
        videos_today=0,
        max_videos_today=3,
    )
