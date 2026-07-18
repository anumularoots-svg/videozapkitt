"""
Whisper forced alignment. MIT, commercial-safe.

Produces word-level timings by transcribing the GENERATED voice audio. This is
what makes subtitles exact rather than approximately right.

The approach this replaces divided each scene's planned duration evenly across
text chunks. That is wrong from the first scene and the error accumulates: by
scene 10 of a 12-scene video the subtitles are visibly detached from the audio.
Measuring the real audio has no such failure mode.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import structlog

from providers.base import (
    Alignment,
    Capabilities,
    License,
    Provenance,
    ProviderError,
    WordTiming,
)

logger = structlog.get_logger()

# Whisper's own language set is wide and includes Telugu and Hindi, so alignment
# is not the constraint at Phase 2 -- TTS is.
SUPPORTED = frozenset({
    "en", "hi", "te", "ta", "kn", "ml", "mr", "bn", "gu", "pa", "or",
    "es", "fr", "de", "it", "pt", "ja", "zh", "ko", "ru", "ar",
})


class WhisperAligner:
    """faster-whisper with word timestamps."""

    def __init__(self, model_size: str = "base", device: str = "cpu", compute_type: str = "int8"):
        self._model_size = model_size
        self._device = device
        self._compute_type = compute_type
        self._model = None

    def capabilities(self) -> Capabilities:
        return Capabilities(
            name=f"whisper-{self._model_size}",
            license=License.MIT,
            languages=SUPPORTED,
            requires_gpu=False,
        )

    def _load(self):
        if self._model is None:
            from faster_whisper import WhisperModel

            logger.info("whisper.loading", size=self._model_size, device=self._device)
            self._model = WhisperModel(
                self._model_size, device=self._device, compute_type=self._compute_type
            )
        return self._model

    async def align(self, audio: Path, text: str, language: str) -> Alignment:
        if language not in SUPPORTED:
            raise ProviderError(f"Whisper alignment does not support {language!r}.")
        if not audio.exists():
            raise ProviderError(f"Audio file not found for alignment: {audio}")

        words = await asyncio.to_thread(self._align_sync, audio, language)

        if not words:
            raise ProviderError(
                f"Whisper returned no word timings for {audio}. The audio may be "
                f"silent -- check the TTS output before this stage."
            )

        logger.info("whisper.aligned", audio=str(audio.name), words=len(words))

        return Alignment(
            words=words,
            provenance=Provenance(
                provider="faster-whisper", model=self._model_size, version="v1"
            ),
        )

    def _align_sync(self, audio: Path, language: str) -> list[WordTiming]:
        model = self._load()
        segments, _ = model.transcribe(
            str(audio), language=language, word_timestamps=True, vad_filter=False
        )

        words: list[WordTiming] = []
        for segment in segments:
            for w in segment.words or []:
                words.append(
                    WordTiming(word=w.word.strip(), start_s=w.start, end_s=w.end)
                )
        return words
