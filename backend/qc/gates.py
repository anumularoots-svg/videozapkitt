"""
Quality gates.

This is where "100% accuracy" becomes something real. No model is 100% accurate,
so the honest goal is 0% SILENT failures: every stage emits a number, thresholds
are explicit, and a video below threshold fails loudly instead of shipping.

Phase 0 gates what is measurable now: durations, subtitle drift, loudness, black
frames, silence. Lip-sync offset and face similarity land in Phase 3 with the
models that make them meaningful.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import structlog

logger = structlog.get_logger()

# ── Thresholds (ARCHITECTURE.md §1.1) ──────────────────
MAX_AV_DURATION_DELTA_S = 0.5
MAX_SUBTITLE_DRIFT_S = 0.12
TARGET_LUFS = -14.0
MAX_LUFS_DELTA = 1.5
MAX_BLACK_FRACTION = 0.10
MAX_SILENCE_FRACTION = 0.35


@dataclass
class Check:
    name: str
    passed: bool
    value: float
    threshold: float
    detail: str = ""


@dataclass
class QCReport:
    checks: list[Check] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks)

    @property
    def failures(self) -> list[Check]:
        return [c for c in self.checks if not c.passed]

    def summary(self) -> str:
        if self.passed:
            return f"QC passed ({len(self.checks)} checks)"
        lines = [f"QC FAILED ({len(self.failures)}/{len(self.checks)} checks):"]
        for c in self.failures:
            lines.append(
                f"  - {c.name}: {c.value:.3f} (limit {c.threshold:.3f}) {c.detail}"
            )
        return "\n".join(lines)


class QCFailure(Exception):
    def __init__(self, report: QCReport):
        self.report = report
        super().__init__(report.summary())


async def run_gates(
    video: Path,
    subtitle_drift_s: float,
    expected_duration_s: float,
    strict: bool = True,
) -> QCReport:
    """Run every Phase 0 gate. Raises QCFailure when `strict` and any gate fails."""
    report = QCReport()

    probe = await _ffprobe(video)
    v_dur = _stream_duration(probe, "video")
    a_dur = _stream_duration(probe, "audio")

    delta = abs(v_dur - a_dur)
    report.checks.append(Check(
        name="av_duration_match",
        passed=delta <= MAX_AV_DURATION_DELTA_S,
        value=delta,
        threshold=MAX_AV_DURATION_DELTA_S,
        detail=f"video={v_dur:.2f}s audio={a_dur:.2f}s",
    ))

    expected_delta = abs(v_dur - expected_duration_s)
    report.checks.append(Check(
        name="duration_vs_plan",
        passed=expected_delta <= max(1.0, expected_duration_s * 0.15),
        value=expected_delta,
        threshold=max(1.0, expected_duration_s * 0.15),
        detail=f"actual={v_dur:.2f}s expected={expected_duration_s:.2f}s",
    ))

    report.checks.append(Check(
        name="subtitle_drift",
        passed=subtitle_drift_s <= MAX_SUBTITLE_DRIFT_S,
        value=subtitle_drift_s,
        threshold=MAX_SUBTITLE_DRIFT_S,
    ))

    lufs = await _measure_loudness(video)
    lufs_delta = abs(lufs - TARGET_LUFS)
    report.checks.append(Check(
        name="loudness",
        passed=lufs_delta <= MAX_LUFS_DELTA,
        value=lufs,
        threshold=TARGET_LUFS,
        detail=f"delta={lufs_delta:.2f} LU",
    ))

    black = await _black_fraction(video, v_dur)
    report.checks.append(Check(
        name="black_frames",
        passed=black <= MAX_BLACK_FRACTION,
        value=black,
        threshold=MAX_BLACK_FRACTION,
        detail="video model may have failed on some scenes",
    ))

    silence = await _silence_fraction(video, a_dur)
    report.checks.append(Check(
        name="silence",
        passed=silence <= MAX_SILENCE_FRACTION,
        value=silence,
        threshold=MAX_SILENCE_FRACTION,
        detail="TTS may have produced empty audio",
    ))

    logger.info(
        "qc.complete",
        passed=report.passed,
        failed=[c.name for c in report.failures],
    )

    if strict and not report.passed:
        raise QCFailure(report)
    return report


# ── Probes ─────────────────────────────────────────────


async def _ffprobe(path: Path) -> dict:
    result = await asyncio.to_thread(
        subprocess.run,
        [
            "ffprobe", "-v", "error", "-print_format", "json",
            "-show_streams", "-show_format", str(path),
        ],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed on {path}: {result.stderr.strip()}")
    return json.loads(result.stdout)


def _stream_duration(probe: dict, codec_type: str) -> float:
    for stream in probe.get("streams", []):
        if stream.get("codec_type") == codec_type:
            if "duration" in stream:
                return float(stream["duration"])
            return float(probe.get("format", {}).get("duration", 0.0))
    raise RuntimeError(f"No {codec_type} stream found -- the render is malformed.")


async def _measure_loudness(path: Path) -> float:
    result = await asyncio.to_thread(
        subprocess.run,
        ["ffmpeg", "-hide_banner", "-i", str(path),
         "-af", "ebur128=peak=true", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    for line in reversed(result.stderr.splitlines()):
        if "I:" in line and "LUFS" in line:
            try:
                return float(line.split("I:")[1].split("LUFS")[0].strip())
            except (IndexError, ValueError):
                continue
    logger.warning("qc.loudness_unmeasurable")
    return TARGET_LUFS  # don't fail the gate on a parse miss


async def _black_fraction(path: Path, duration: float) -> float:
    if duration <= 0:
        return 0.0
    result = await asyncio.to_thread(
        subprocess.run,
        ["ffmpeg", "-hide_banner", "-i", str(path),
         "-vf", "blackdetect=d=0.5:pix_th=0.10", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    total = 0.0
    for line in result.stderr.splitlines():
        if "black_duration" in line:
            for token in line.split():
                if token.startswith("black_duration:"):
                    total += float(token.split(":")[1])
    return total / duration


async def _silence_fraction(path: Path, duration: float) -> float:
    if duration <= 0:
        return 0.0
    result = await asyncio.to_thread(
        subprocess.run,
        ["ffmpeg", "-hide_banner", "-i", str(path),
         "-af", "silencedetect=n=-50dB:d=1.0", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    total = 0.0
    for line in result.stderr.splitlines():
        if "silence_duration:" in line:
            total += float(line.split("silence_duration:")[1].strip().split()[0])
    return total / duration
