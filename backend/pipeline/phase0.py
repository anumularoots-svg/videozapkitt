"""
Phase 0 vertical slice.

  idea -> script -> voice -> RECONCILE -> align -> keyframes -> clips
       -> music -> compose -> QC -> playable mp4

Scope, deliberately: 15s, English, 3 scenes, 9:16, Wan 1.3B.

WHAT SUCCESS LOOKS LIKE: audio, subtitles and video stay locked together, and QC
passes. NOT beauty -- 1.3B does not make cinematic video and is not being asked
to. Reading a rough-looking Phase 0 clip as project failure would be the wrong
conclusion; the thing being proven here is that the pipeline is honest.

Ordering that matters:
  - voice BEFORE video, because voice is the clock (reconcile.py)
  - align on the GENERATED audio, so subtitles cannot drift
  - music per act, not per scene, so it doesn't restart every 5 seconds
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

import structlog

from compose.ffmpeg_compose import ComposeConfig, compose
from pipeline.reconcile import ReconcileReport, TimedScene, reconcile_timing
from pipeline.script_stage import ScriptStage
from pipeline.subtitles import build_cues, max_drift_s, render_srt
from providers.base import MusicRequest, VideoRequest
from providers.registry import ProviderRegistry
from qc.gates import QCReport, run_gates

logger = structlog.get_logger()

MUSIC_PROMPTS = {
    "soft": "soft ambient cinematic underscore, gentle piano, warm pads, no vocals",
    "epic": "epic cinematic orchestral, powerful drums, strings, brass, no vocals",
    "emotional": "emotional piano and strings, heartfelt cinematic, no vocals",
    "hopeful": "hopeful uplifting, piano building to strings, cinematic, no vocals",
    "upbeat": "upbeat positive underscore, light percussion, synth, no vocals",
    "tense": "tense dramatic, staccato strings, building pressure, no vocals",
    "motivational": "motivational driving beat, inspiring melody, cinematic, no vocals",
}

STYLE_SUFFIX = (
    "cinematic, professional color grading, shallow depth of field, "
    "high detail, film still"
)


@dataclass
class Phase0Config:
    duration_s: int = 15
    scene_count: int = 3
    language: str = "en"
    width: int = 480          # 9:16 at 1.3B-friendly resolution
    height: int = 854
    fps: int = 16
    seed: int | None = 42     # fixed so runs are comparable
    strict_qc: bool = True


@dataclass
class Phase0Result:
    video: Path
    title: str
    duration_s: float
    elapsed_s: float
    reconcile: ReconcileReport
    qc: QCReport
    stage_timings: dict[str, float] = field(default_factory=dict)


async def run_phase0(
    idea: str,
    registry: ProviderRegistry,
    work_dir: Path,
    config: Phase0Config = Phase0Config(),
) -> Phase0Result:
    started = time.time()
    timings: dict[str, float] = {}
    work_dir.mkdir(parents=True, exist_ok=True)

    log = logger.bind(idea=idea[:50])
    log.info("phase0.start", duration=config.duration_s, scenes=config.scene_count)

    # Route up front so an unsupported language fails in seconds, not after
    # minutes of GPU time.
    tts = registry.tts_for(config.language)
    llm = registry.llm()
    aligner = registry.alignment()
    video = registry.video()
    music = registry.music()
    # No image provider on the Phase 0 path -- Wan T2V generates from text. FLUX
    # stays registered for the I2V/consistency phase but is not fetched here.

    # ── 1. Script ──────────────────────────────────────
    t = time.time()
    script_stage = ScriptStage(llm)
    plan = await script_stage.generate(
        idea, config.duration_s, config.language, config.scene_count
    )
    timings["script"] = time.time() - t

    # ── 2. Voice + reconcile ───────────────────────────
    # Voice first. Everything downstream is timed to what the TTS actually said.
    t = time.time()
    timed, reconcile_report = await reconcile_timing(
        scenes=plan["scenes"],
        tts=tts,
        language=config.language,
        work_dir=work_dir,
        shorten_fn=script_stage.shorten,
    )
    timings["voice_reconcile"] = time.time() - t

    # ── 3. Align -> subtitles ──────────────────────────
    t = time.time()
    all_cues = []
    worst_drift = 0.0
    for scene in timed:
        alignment = await aligner.align(
            scene.voice.path, scene.dialogue, config.language
        )
        cues = build_cues(alignment, offset_s=scene.start_s)
        worst_drift = max(worst_drift, max_drift_s(cues, alignment, scene.start_s))
        all_cues.extend(cues)

    srt_path = work_dir / "subtitles.srt"
    srt_path.write_text(render_srt(all_cues), encoding="utf-8")
    timings["align"] = time.time() - t
    log.info("phase0.subtitles", cues=len(all_cues), drift=f"{worst_drift * 1000:.0f}ms")

    # ── 4. Clips (text-to-video) ───────────────────────
    # Wan T2V-1.3B generates directly from the prompt. It does NOT consume a
    # keyframe image, so Phase 0 does not generate one -- doing so would be a
    # silent no-op, which is exactly what this pipeline refuses to do elsewhere.
    #
    # A FLUX keyframe becomes load-bearing at the I2V/consistency phase, where an
    # image-to-video model animates a fixed first frame and identity can be
    # pinned across clips (ARCHITECTURE.md §4.5). Phase 0's job is sync, not
    # consistency, so it stays on the simpler T2V path.
    t = time.time()
    scene_by_id = {s["id"]: s for s in plan["scenes"]}
    clips: list[Path] = []

    for scene in timed:
        source = scene_by_id[scene.scene_id]
        prompt = f"{source['visual_prompt']}, {STYLE_SUFFIX}"

        clip = await video.generate(VideoRequest(
            prompt=prompt,
            duration_s=min(scene.video_duration_s, 5.0),
            width=config.width,
            height=config.height,
            fps=config.fps,
            seed=config.seed,
            out_path=work_dir / f"scene_{scene.scene_id}_clip.mp4",
        ))
        clips.append(clip.path)
        log.info("phase0.scene_done", scene=scene.scene_id, duration=f"{clip.duration_s:.2f}s")

    timings["video"] = time.time() - t

    # ── 5. Music ───────────────────────────────────────
    # One track across the whole slice. At 15s this is one "act"; at 60s
    # (Phase 1) this splits into 2-3 acts with crossfades.
    t = time.time()
    mood = scene_by_id[timed[0].scene_id].get("music_mood", "soft")
    bgm = await music.generate(MusicRequest(
        prompt=MUSIC_PROMPTS.get(mood, MUSIC_PROMPTS["soft"]),
        duration_s=min(reconcile_report.total_duration_s, 47.0),
        seed=config.seed,
        out_path=work_dir / "bgm.wav",
    ))
    timings["music"] = time.time() - t

    # ── 6. Compose ─────────────────────────────────────
    t = time.time()
    out_path = work_dir / "final.mp4"
    final = await compose(
        clips=clips,
        voice_tracks=[(s.voice.path, s.start_s) for s in timed],
        music=bgm.path,
        srt=srt_path,
        out=out_path,
        work_dir=work_dir / "compose",
        config=ComposeConfig(width=config.width, height=config.height, fps=config.fps),
    )
    timings["compose"] = time.time() - t

    # ── 7. QC ──────────────────────────────────────────
    t = time.time()
    qc = await run_gates(
        video=final,
        subtitle_drift_s=worst_drift,
        expected_duration_s=reconcile_report.total_duration_s,
        strict=config.strict_qc,
    )
    timings["qc"] = time.time() - t

    elapsed = time.time() - started
    log.info(
        "phase0.complete",
        video=str(final),
        elapsed=f"{elapsed:.1f}s",
        qc_passed=qc.passed,
    )

    return Phase0Result(
        video=final,
        title=plan["title"],
        duration_s=reconcile_report.total_duration_s,
        elapsed_s=elapsed,
        reconcile=reconcile_report,
        qc=qc,
        stage_timings=timings,
    )
