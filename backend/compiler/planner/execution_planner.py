"""
Stage 5: Execution Planner

Builds a Directed Acyclic Graph (DAG) of tasks.
Determines what runs in parallel vs sequentially.
GPU resources are only allocated AFTER this stage.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum


class TaskType(str, Enum):
    SCRIPT = "script"
    CHARACTER = "character"
    VOICE = "voice"
    MUSIC = "music"
    SUBTITLE = "subtitle"
    SCENE_VIDEO = "scene_video"
    SCENE_AUDIO = "scene_audio"
    CONSISTENCY_CHECK = "consistency_check"
    RENDER = "render"
    STITCH = "stitch"
    QUALITY_CHECK = "quality_check"
    EXPORT = "export"


@dataclass
class Task:
    id: str
    task_type: TaskType
    scene_id: int | None = None
    depends_on: list[str] = field(default_factory=list)
    priority: int = 0  # higher = sooner
    gpu_required: bool = False
    estimated_seconds: int = 10


@dataclass
class ExecutionPlan:
    tasks: list[Task] = field(default_factory=list)
    parallel_groups: list[list[str]] = field(default_factory=list)
    total_estimated_seconds: int = 0
    total_gpu_tasks: int = 0

    def add(self, task: Task):
        self.tasks.append(task)
        if task.gpu_required:
            self.total_gpu_tasks += 1

    def get_task(self, task_id: str) -> Task | None:
        return next((t for t in self.tasks if t.id == task_id), None)

    def get_ready_tasks(self, completed: set[str]) -> list[Task]:
        """Return tasks whose dependencies are all completed."""
        ready = []
        for task in self.tasks:
            if task.id in completed:
                continue
            if all(dep in completed for dep in task.depends_on):
                ready.append(task)
        return sorted(ready, key=lambda t: -t.priority)


def build_execution_plan(blueprint: dict) -> ExecutionPlan:
    """Build a DAG from the optimized blueprint."""
    plan = ExecutionPlan()
    scenes = blueprint["scenes"]

    # ── Phase 1: Script generation (sequential) ────────
    plan.add(Task(
        id="script_all",
        task_type=TaskType.SCRIPT,
        priority=100,
        estimated_seconds=15,
    ))

    # ── Phase 2: Parallel asset generation ─────────────
    # Character + Music run in parallel (no dependency on each other)
    plan.add(Task(
        id="character_gen",
        task_type=TaskType.CHARACTER,
        depends_on=["script_all"],
        priority=90,
        gpu_required=True,
        estimated_seconds=30,
    ))

    plan.add(Task(
        id="music_gen",
        task_type=TaskType.MUSIC,
        depends_on=["script_all"],
        priority=80,
        gpu_required=True,
        estimated_seconds=20,
    ))

    # Voice depends on script (sequential)
    plan.add(Task(
        id="voice_gen",
        task_type=TaskType.VOICE,
        depends_on=["script_all"],
        priority=85,
        gpu_required=True,
        estimated_seconds=20,
    ))

    # Subtitle depends on voice
    plan.add(Task(
        id="subtitle_gen",
        task_type=TaskType.SUBTITLE,
        depends_on=["voice_gen"],
        priority=70,
        estimated_seconds=5,
    ))

    # ── Phase 3: Per-scene video generation ────────────
    for scene in scenes:
        sid = scene["id"]
        plan.add(Task(
            id=f"scene_video_{sid}",
            task_type=TaskType.SCENE_VIDEO,
            scene_id=sid,
            depends_on=["character_gen", "script_all"],
            priority=60,
            gpu_required=True,
            estimated_seconds=45,
        ))

    # ── Phase 4: Consistency check ─────────────────────
    scene_video_ids = [f"scene_video_{s['id']}" for s in scenes]
    plan.add(Task(
        id="consistency_check",
        task_type=TaskType.CONSISTENCY_CHECK,
        depends_on=scene_video_ids,
        priority=50,
        estimated_seconds=10,
    ))

    # ── Phase 5: Render (stitch + audio + subtitles) ───
    plan.add(Task(
        id="render",
        task_type=TaskType.RENDER,
        depends_on=["consistency_check", "voice_gen", "music_gen", "subtitle_gen"],
        priority=40,
        gpu_required=True,
        estimated_seconds=30,
    ))

    # ── Phase 6: Quality check ─────────────────────────
    plan.add(Task(
        id="quality_check",
        task_type=TaskType.QUALITY_CHECK,
        depends_on=["render"],
        priority=30,
        estimated_seconds=10,
    ))

    # ── Phase 7: Export ────────────────────────────────
    plan.add(Task(
        id="export",
        task_type=TaskType.EXPORT,
        depends_on=["quality_check"],
        priority=20,
        estimated_seconds=5,
    ))

    # Compute parallel groups for visualization
    plan.parallel_groups = [
        ["script_all"],
        ["character_gen", "music_gen", "voice_gen"],
        ["subtitle_gen"] + scene_video_ids,
        ["consistency_check"],
        ["render"],
        ["quality_check"],
        ["export"],
    ]

    plan.total_estimated_seconds = sum(t.estimated_seconds for t in plan.tasks)

    return plan
