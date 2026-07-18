"""
FFmpeg composition: clips + voice + ducked music + subtitles -> final mp4.

Two things here are deliberate quality decisions, not defaults:

1. SIDECHAIN DUCKING. The old pipeline mixed music at a static volume=0.3. Static
   gain either buries the music in the quiet parts or fights the voice in the
   loud ones. Sidechain compression makes the music dip only while someone is
   speaking and recover between lines. Cheap to do, and one of the largest
   perceived-quality wins available at Phase 0.

2. LOUDNESS NORMALISATION to -14 LUFS, the social-platform target. Without it
   YouTube/Instagram normalise for you, unpredictably.

Every command runs through `_run`, which raises with FFmpeg's actual stderr.
A silently-failing render that emits a 0-byte file is worse than a crash.
"""

from __future__ import annotations

import asyncio
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import structlog

logger = structlog.get_logger()

TARGET_LUFS = -14.0

# Ducking: music drops when voice exceeds the threshold, recovers over ~250ms.
DUCK_FILTER = (
    "[1:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo[music];"
    "[0:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo[voice];"
    "[voice]asplit=2[voice_mix][voice_key];"
    "[music][voice_key]sidechaincompress="
    "threshold=0.03:ratio=8:attack=5:release=250:makeup=1[ducked];"
    "[voice_mix][ducked]amix=inputs=2:duration=first:dropout_transition=0[mixed];"
    f"[mixed]loudnorm=I={TARGET_LUFS}:TP=-1.5:LRA=11[out]"
)

SUBTITLE_STYLE = (
    "FontName=Arial,FontSize=16,PrimaryColour=&H00FFFFFF,"
    "OutlineColour=&H00000000,BorderStyle=1,Outline=2,Shadow=1,"
    "Alignment=2,MarginV=60"
)


class FFmpegError(RuntimeError):
    pass


@dataclass(frozen=True)
class ComposeConfig:
    width: int = 480
    height: int = 854
    fps: int = 16
    video_codec: str = "libx264"
    audio_codec: str = "aac"
    crf: int = 20


async def compose(
    clips: list[Path],
    voice_tracks: list[tuple[Path, float]],  # (path, start_s) on the global timeline
    music: Path,
    srt: Path,
    out: Path,
    work_dir: Path,
    config: ComposeConfig = ComposeConfig(),
) -> Path:
    """Assemble the final video. Returns `out`."""
    _require_ffmpeg()
    work_dir.mkdir(parents=True, exist_ok=True)
    out.parent.mkdir(parents=True, exist_ok=True)

    if not clips:
        raise FFmpegError("No clips to compose.")

    missing = [p for p in [*clips, music, srt] if not p.exists()]
    if missing:
        raise FFmpegError(f"Missing inputs: {', '.join(str(m) for m in missing)}")

    stitched = await _concat_clips(clips, work_dir, config)
    voice = await _lay_voice_on_timeline(voice_tracks, work_dir)
    mixed = await _mix_with_ducking(voice, music, work_dir)
    combined = await _mux(stitched, mixed, work_dir, config)
    final = await _burn_subtitles(combined, srt, out, config)

    logger.info("compose.complete", out=str(final), size=final.stat().st_size)
    return final


async def _concat_clips(clips: list[Path], work_dir: Path, config: ComposeConfig) -> Path:
    """Concat via filter, not the demuxer.

    The demuxer + `-c copy` path (what the old renderer used) only works when
    every input shares an identical codec/timebase. Generated clips do not
    reliably, and the failure is a corrupt file rather than an error. Re-encoding
    is slower and always correct.
    """
    out = work_dir / "stitched.mp4"

    args: list[str] = []
    for clip in clips:
        args += ["-i", str(clip)]

    parts = "".join(
        f"[{i}:v]scale={config.width}:{config.height}:force_original_aspect_ratio=decrease,"
        f"pad={config.width}:{config.height}:(ow-iw)/2:(oh-ih)/2,"
        f"setsar=1,fps={config.fps}[v{i}];"
        for i in range(len(clips))
    )
    concat_inputs = "".join(f"[v{i}]" for i in range(len(clips)))
    filter_complex = f"{parts}{concat_inputs}concat=n={len(clips)}:v=1:a=0[outv]"

    await _run([
        *args,
        "-filter_complex", filter_complex,
        "-map", "[outv]",
        "-c:v", config.video_codec, "-crf", str(config.crf), "-pix_fmt", "yuv420p",
        "-y", str(out),
    ])
    return out


async def _lay_voice_on_timeline(
    voice_tracks: list[tuple[Path, float]], work_dir: Path
) -> Path:
    """Place each scene's voice at its reconciled start time.

    `adelay` positions each track; `amix` sums them. Because starts come from
    reconcile.py (measured), voice lands under the matching visuals.
    """
    out = work_dir / "voice_timeline.wav"

    if not voice_tracks:
        raise FFmpegError("No voice tracks to lay out.")

    args: list[str] = []
    for path, _ in voice_tracks:
        args += ["-i", str(path)]

    delays = "".join(
        f"[{i}:a]adelay={int(start * 1000)}|{int(start * 1000)}[d{i}];"
        for i, (_, start) in enumerate(voice_tracks)
    )
    mix_inputs = "".join(f"[d{i}]" for i in range(len(voice_tracks)))
    # normalize=0: amix otherwise divides gain by input count, so an 8-scene
    # video would come out 8x quieter than a 1-scene one.
    filter_complex = (
        f"{delays}{mix_inputs}amix=inputs={len(voice_tracks)}:"
        f"duration=longest:normalize=0[outa]"
    )

    await _run([
        *args,
        "-filter_complex", filter_complex,
        "-map", "[outa]",
        "-y", str(out),
    ])
    return out


async def _mix_with_ducking(voice: Path, music: Path, work_dir: Path) -> Path:
    out = work_dir / "mixed.wav"
    await _run([
        "-i", str(voice),
        "-i", str(music),
        "-filter_complex", DUCK_FILTER,
        "-map", "[out]",
        "-y", str(out),
    ])
    return out


async def _mux(video: Path, audio: Path, work_dir: Path, config: ComposeConfig) -> Path:
    out = work_dir / "combined.mp4"
    await _run([
        "-i", str(video),
        "-i", str(audio),
        "-map", "0:v", "-map", "1:a",
        "-c:v", "copy",
        "-c:a", config.audio_codec, "-b:a", "192k",
        "-shortest",
        "-y", str(out),
    ])
    return out


async def _burn_subtitles(video: Path, srt: Path, out: Path, config: ComposeConfig) -> Path:
    # FFmpeg's filter parser needs the path escaped; on Windows the drive colon
    # would otherwise read as an option separator.
    escaped = str(srt).replace("\\", "/").replace(":", "\\:")
    await _run([
        "-i", str(video),
        "-vf", f"subtitles='{escaped}':force_style='{SUBTITLE_STYLE}'",
        "-c:v", config.video_codec, "-crf", str(config.crf), "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        "-y", str(out),
    ])
    return out


def _require_ffmpeg() -> None:
    if shutil.which("ffmpeg") is None:
        raise FFmpegError(
            "ffmpeg not found on PATH. Install it (apt install ffmpeg) -- the "
            "compositor cannot run without it."
        )


async def _run(args: list[str]) -> None:
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", *args]
    logger.debug("ffmpeg.run", cmd=" ".join(cmd[:8]) + " ...")

    result = await asyncio.to_thread(
        subprocess.run, cmd, capture_output=True, text=True
    )
    if result.returncode != 0:
        raise FFmpegError(
            f"ffmpeg failed (exit {result.returncode}).\n"
            f"Command: {' '.join(cmd)}\n"
            f"stderr: {result.stderr.strip()}"
        )
