"""
Timing reconciliation -- "voice is the clock".

The planner guesses a scene is 5.0s. The TTS then produces 6.3s of speech. If
nothing compares those two numbers, audio, subtitles and video drift apart, and
the drift ACCUMULATES: a 1.3s error per scene is 15s of desync by scene 12. The
video is broken and no single stage looks guilty.

The fix is an ordering rule: generate voice FIRST, measure its real duration,
then re-time everything else to it. Video is generated to fit the voice. Never
the reverse -- you cannot stretch speech to fit a clip without it sounding wrong.

Why estimation cannot work here: the pre-rewrite code used a fixed 2.5 words/sec
constant. Spoken length per word differs substantially across languages, and
Telugu and English are not close. One constant cannot serve both. So: measure.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

import structlog

from providers.base import AudioAsset, TTSProvider, TTSRequest

logger = structlog.get_logger()

# How far over its planned duration a scene's voice may run before we ask the
# LLM to tighten the line. Some overshoot is fine -- video is generated to the
# real duration anyway. This bound exists to stop one runaway scene from eating
# the whole video's budget.
OVERSHOOT_TOLERANCE = 1.25

# Breathing room appended to each clip so speech doesn't butt against a cut.
TAIL_PAD_S = 0.35

MAX_SHORTEN_ATTEMPTS = 2


@dataclass
class TimedScene:
    scene_id: int
    dialogue: str
    planned_duration_s: float
    voice: AudioAsset
    start_s: float = 0.0

    @property
    def actual_duration_s(self) -> float:
        """The measured length of the generated speech. The clock."""
        return self.voice.duration_s

    @property
    def video_duration_s(self) -> float:
        """What the video model must generate to cover the speech."""
        return self.actual_duration_s + TAIL_PAD_S

    @property
    def end_s(self) -> float:
        return self.start_s + self.video_duration_s


@dataclass
class ReconcileReport:
    """Surfaced to the admin dashboard: how far the plan was from reality.

    A consistently large drift means the script agent's pacing model is wrong
    for that language and should be retuned -- which you can only see if it is
    recorded.
    """

    total_duration_s: float
    planned_duration_s: float
    scenes_shortened: list[int]
    max_scene_drift_s: float

    @property
    def drift_s(self) -> float:
        return self.total_duration_s - self.planned_duration_s


async def reconcile_timing(
    scenes: list[dict],
    tts: TTSProvider,
    language: str,
    work_dir: Path,
    shorten_fn=None,
) -> tuple[list[TimedScene], ReconcileReport]:
    """Generate voice for each scene, then lay the timeline out on real durations.

    `shorten_fn(text, target_seconds) -> str` tightens an overlong line. Optional:
    without it, overlong scenes are kept as-is and simply reported.
    """
    timed: list[TimedScene] = []
    shortened: list[int] = []
    max_drift = 0.0

    for scene in scenes:
        scene_id = scene["id"]
        dialogue = scene.get("script", "").strip()
        planned = float(scene["duration"])

        if not dialogue:
            raise ValueError(
                f"Scene {scene_id} has no script text. The script stage must run "
                f"before reconciliation -- voice cannot be the clock if there is "
                f"nothing to say."
            )

        voice = await _synthesize(tts, dialogue, scene, language, work_dir)

        attempts = 0
        while (
            shorten_fn is not None
            and voice.duration_s > planned * OVERSHOOT_TOLERANCE
            and attempts < MAX_SHORTEN_ATTEMPTS
        ):
            attempts += 1
            logger.info(
                "reconcile.shortening",
                scene=scene_id,
                actual=f"{voice.duration_s:.2f}s",
                planned=f"{planned:.2f}s",
                attempt=attempts,
            )
            dialogue = await shorten_fn(dialogue, planned)
            voice = await _synthesize(tts, dialogue, scene, language, work_dir)

            if attempts == MAX_SHORTEN_ATTEMPTS and voice.duration_s > planned * OVERSHOOT_TOLERANCE:
                # Accept it rather than loop. The video stretches to fit; the
                # report makes the overshoot visible instead of silent.
                logger.warning(
                    "reconcile.shorten_gave_up",
                    scene=scene_id,
                    actual=f"{voice.duration_s:.2f}s",
                    planned=f"{planned:.2f}s",
                )

        if attempts:
            shortened.append(scene_id)

        drift = abs(voice.duration_s - planned)
        max_drift = max(max_drift, drift)

        timed.append(
            TimedScene(
                scene_id=scene_id,
                dialogue=dialogue,
                planned_duration_s=planned,
                voice=voice,
            )
        )

    # Lay out the timeline on measured durations. Each scene starts where the
    # previous actually ended -- not where the plan said it would.
    cursor = 0.0
    for scene in timed:
        scene.start_s = cursor
        cursor += scene.video_duration_s

    report = ReconcileReport(
        total_duration_s=cursor,
        planned_duration_s=sum(float(s["duration"]) for s in scenes),
        scenes_shortened=shortened,
        max_scene_drift_s=max_drift,
    )

    logger.info(
        "reconcile.complete",
        total=f"{report.total_duration_s:.2f}s",
        planned=f"{report.planned_duration_s:.2f}s",
        drift=f"{report.drift_s:+.2f}s",
        shortened=len(shortened),
    )

    return timed, report


async def _synthesize(
    tts: TTSProvider,
    dialogue: str,
    scene: dict,
    language: str,
    work_dir: Path,
) -> AudioAsset:
    return await tts.synthesize(
        TTSRequest(
            text=dialogue,
            language=language,
            voice_id=scene.get("character", "narrator_m_01"),
            speed=float(scene.get("voice_speed", 1.0)),
            out_path=work_dir / f"scene_{scene['id']}_voice.wav",
        )
    )
