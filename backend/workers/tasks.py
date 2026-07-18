"""
Celery tasks.

Every task here calls the real pipeline. If a task returns "completed", a file
exists on disk -- that is the invariant.

The pre-rewrite version of this module reported success from comment blocks
("In production, this would: 1. Call Kokoro TTS..."), which is why the system
appeared to work while producing nothing. Do not reintroduce a task that returns
a status it did not earn.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import structlog

from .celery_app import celery_app

logger = structlog.get_logger()

WORK_ROOT = Path("/tmp/render")


def run_async(coro):
    """Run async code inside a sync Celery task."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(bind=True, name="workers.tasks.compile_video", max_retries=2)
def compile_video(self, project_id: str, idea: str, language: str, duration: int):
    """Compile an idea into a finished video.

    Phase 0 runs the whole slice in one task. Splitting scene generation across
    GPU workers needs the SQS/ASG wiring that does not exist yet (Phase 4), so
    doing it now would be premature.
    """
    from pipeline.phase0 import Phase0Config, run_phase0
    from providers.base import ProviderError, UnsupportedCapability
    from providers.bootstrap import build_registry
    from qc.gates import QCFailure

    log = logger.bind(project_id=project_id, task_id=self.request.id)
    log.info("task.compile_video.start", language=language, duration=duration)

    registry = build_registry()
    work_dir = WORK_ROOT / project_id

    try:
        result = run_async(run_phase0(
            idea=idea,
            registry=registry,
            work_dir=work_dir,
            config=Phase0Config(duration_s=duration, language=language),
        ))
    except UnsupportedCapability as e:
        # Retrying will not add Telugu support. Fail terminally, and say so.
        log.error("task.compile_video.unsupported", error=str(e))
        return {
            "status": "failed",
            "project_id": project_id,
            "reason": "unsupported_capability",
            "detail": str(e),
            "supported_languages": sorted(registry.supported_languages()),
        }
    except QCFailure as e:
        # It rendered, but failed quality gates. Report the failing checks rather
        # than shipping it. See ARCHITECTURE.md §1.1.
        log.error(
            "task.compile_video.qc_failed",
            failures=[c.name for c in e.report.failures],
        )
        return {
            "status": "failed",
            "project_id": project_id,
            "reason": "qc_failed",
            "checks": [
                {"name": c.name, "value": c.value, "threshold": c.threshold}
                for c in e.report.failures
            ],
        }
    except ProviderError as e:
        log.error("task.compile_video.provider_error", error=str(e))
        raise self.retry(exc=e, countdown=15)

    log.info(
        "task.compile_video.complete",
        video=str(result.video),
        elapsed=f"{result.elapsed_s:.1f}s",
    )

    return {
        "status": "completed",
        "project_id": project_id,
        "video_path": str(result.video),
        "title": result.title,
        "duration_s": result.duration_s,
        "elapsed_s": result.elapsed_s,
        "qc_passed": result.qc.passed,
        "stage_timings": result.stage_timings,
        "drift_s": result.reconcile.drift_s,
    }
