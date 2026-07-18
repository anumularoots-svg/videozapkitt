"""
Subtitle generation from measured word timings.

Builds SRT from Whisper's word-level alignment of the GENERATED audio, so cue
boundaries land on real word boundaries at real times.

This replaces an approach that split text into 8-word chunks and divided the
scene's PLANNED duration evenly among them. That is wrong three ways: the
planned duration isn't the real one, words aren't equal length, and the error
compounds scene over scene.
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog

from providers.base import Alignment, WordTiming

logger = structlog.get_logger()

MAX_CHARS_PER_CUE = 42  # comfortable single line on a 9:16 phone screen
MAX_WORDS_PER_CUE = 7
MAX_CUE_DURATION_S = 3.5
# A gap this long between words is a natural phrase break -- cut the cue there.
PHRASE_GAP_S = 0.35


@dataclass
class Cue:
    index: int
    start_s: float
    end_s: float
    text: str


def build_cues(alignment: Alignment, offset_s: float = 0.0) -> list[Cue]:
    """Group aligned words into cues. `offset_s` shifts scene-local times onto
    the global timeline (a scene's voice starts at its reconciled start_s)."""
    if not alignment.words:
        return []

    cues: list[Cue] = []
    current: list[WordTiming] = []

    def flush() -> None:
        if not current:
            return
        cues.append(
            Cue(
                index=len(cues) + 1,
                start_s=current[0].start_s + offset_s,
                end_s=current[-1].end_s + offset_s,
                text=" ".join(w.word for w in current),
            )
        )
        current.clear()

    for word in alignment.words:
        if current and _should_break(current, word):
            flush()
        current.append(word)

    flush()
    return cues


def _should_break(current: list[WordTiming], nxt: WordTiming) -> bool:
    text_len = sum(len(w.word) + 1 for w in current) + len(nxt.word)
    if text_len > MAX_CHARS_PER_CUE:
        return True
    if len(current) >= MAX_WORDS_PER_CUE:
        return True
    if nxt.end_s - current[0].start_s > MAX_CUE_DURATION_S:
        return True
    if nxt.start_s - current[-1].end_s > PHRASE_GAP_S:
        return True
    # Sentence end -- a natural cue boundary.
    return current[-1].word.endswith((".", "!", "?"))


def render_srt(cues: list[Cue]) -> str:
    blocks = []
    for i, cue in enumerate(cues, start=1):
        blocks.append(
            f"{i}\n{_srt_time(cue.start_s)} --> {_srt_time(cue.end_s)}\n{cue.text}\n"
        )
    return "\n".join(blocks)


def _srt_time(seconds: float) -> str:
    seconds = max(0.0, seconds)
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int(round((seconds - int(seconds)) * 1000))
    if ms == 1000:  # rounding carry
        s += 1
        ms = 0
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def max_drift_s(cues: list[Cue], alignment: Alignment, offset_s: float = 0.0) -> float:
    """Largest gap between a cue's start and its first word's real onset.

    Feeds the QC gate (threshold ~120ms). Should be ~0 by construction -- a
    nonzero value means something re-timed cues after alignment, which is
    exactly the bug class this module exists to prevent.
    """
    if not cues or not alignment.words:
        return 0.0

    drift = 0.0
    word_starts = [w.start_s + offset_s for w in alignment.words]
    for cue in cues:
        nearest = min(word_starts, key=lambda ws: abs(ws - cue.start_s))
        drift = max(drift, abs(nearest - cue.start_s))
    return drift
