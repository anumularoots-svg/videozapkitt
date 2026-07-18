"""
Video Compiler — The Core Engine

10-stage compilation pipeline:

  Stage 1: Input Parser
  Stage 2: Video Template Selector
  Stage 3: Video DSL Generator
  Stage 4: Blueprint Generator
  Stage 5: Blueprint Validator
  Stage 6: Blueprint Optimizer
  Stage 7: Execution Planner (DAG)
  Stage 8: Agent Orchestrator   (handled by orchestrator/)
  Stage 9: Quality Validation   (handled by agents/quality/)
  Stage 10: Export              (handled by renderer/)

Nothing bypasses the compiler.
"""

from __future__ import annotations
import uuid
import structlog
from dataclasses import dataclass

from .parser import parse_input, ParsedInput
from .dsl import create_skeleton_dsl, VideoDSL, get_template
from .validator import validate_blueprint, ValidationResult
from .optimizer import optimize_blueprint
from .planner import build_execution_plan, ExecutionPlan

logger = structlog.get_logger()


@dataclass
class CompilationResult:
    success: bool
    project_id: str
    parsed_input: ParsedInput | None = None
    dsl: VideoDSL | None = None
    blueprint: dict | None = None
    validation: ValidationResult | None = None
    execution_plan: ExecutionPlan | None = None
    error: str | None = None
    stage_failed: str | None = None


class VideoCompiler:
    """
    The Video Compiler.

    Takes a user's idea and compiles it through 7 stages into
    an execution-ready blueprint with a DAG plan.
    Stages 8-10 are handled by the orchestrator and renderer.
    """

    async def compile(
        self,
        idea: str,
        language: str,
        duration: int,
        project_id: str | None = None,
    ) -> CompilationResult:
        """Run the full compilation pipeline."""
        pid = project_id or str(uuid.uuid4())
        log = logger.bind(project_id=pid)

        # ── Stage 1: Parse Input ───────────────────────
        log.info("compiler.stage1.parse")
        try:
            parsed = parse_input(idea, language, duration)
        except Exception as e:
            return CompilationResult(
                success=False, project_id=pid,
                error=str(e), stage_failed="parse",
            )

        # ── Stage 2: Select Template ───────────────────
        log.info("compiler.stage2.template", video_type=parsed.video_type)
        template = get_template(parsed.video_type)

        # ── Stage 3: Generate Video DSL ────────────────
        log.info("compiler.stage3.dsl")
        dsl = create_skeleton_dsl(
            video_type=parsed.video_type,
            duration=parsed.duration,
            language=parsed.language,
            style="cinematic",
        )
        dsl.title = parsed.idea[:100]

        # ── Stage 4: Generate Blueprint JSON ───────────
        log.info("compiler.stage4.blueprint")
        blueprint = dsl.to_blueprint_json(project_id=pid)

        # ── Stage 5: Validate Blueprint ────────────────
        log.info("compiler.stage5.validate")
        validation = validate_blueprint(blueprint)
        if not validation.is_valid:
            log.error("compiler.validation_failed", errors=validation.errors)
            return CompilationResult(
                success=False, project_id=pid,
                parsed_input=parsed, dsl=dsl, blueprint=blueprint,
                validation=validation,
                error="Blueprint validation failed",
                stage_failed="validate",
            )

        # ── Stage 6: Optimize Blueprint ────────────────
        log.info("compiler.stage6.optimize")
        blueprint = optimize_blueprint(blueprint)

        # ── Stage 7: Build Execution Plan (DAG) ────────
        log.info("compiler.stage7.plan")
        plan = build_execution_plan(blueprint)

        log.info(
            "compiler.complete",
            scenes=len(blueprint["scenes"]),
            tasks=len(plan.tasks),
            gpu_tasks=plan.total_gpu_tasks,
            estimated_seconds=plan.total_estimated_seconds,
        )

        return CompilationResult(
            success=True,
            project_id=pid,
            parsed_input=parsed,
            dsl=dsl,
            blueprint=blueprint,
            validation=validation,
            execution_plan=plan,
        )
