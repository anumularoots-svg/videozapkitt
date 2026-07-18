"""
Kokoro-82M TTS provider. Apache-2.0, commercial-safe.

Phase 0-1 English only. Kokoro officially covers 8 languages; Telugu is NOT
among them, and its Hindi is trained on single-digit hours (quality ~B-). So
this provider declares English only, and the registry raises for anything else
rather than narrating Telugu in an American accent.

Telugu/Hindi arrive in Phase 2 via IndicF5 (MIT, 1417h, 11 Indic languages).
See ARCHITECTURE.md §2.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import soundfile as sf
import structlog

from providers.base import (
    AudioAsset,
    Capabilities,
    License,
    Provenance,
    ProviderError,
    TTSRequest,
)

logger = structlog.get_logger()

SAMPLE_RATE = 24_000
MODEL_ID = "hexgrad/Kokoro-82M"

# Kokoro voice ids are language-prefixed: a=American, b=British.
# All of these are English. That is the point -- see module docstring.
VOICE_MAP = {
    "narrator_m_01": "am_adam",
    "narrator_f_01": "af_sarah",
    "young_m_01": "am_michael",
    "young_f_01": "af_bella",
    "business_m_01": "am_adam",
    "business_f_01": "af_bella",
}
DEFAULT_VOICE = "am_adam"


class KokoroTTS:
    """Kokoro-82M. Runs on CPU acceptably; GPU is faster but not required."""

    def __init__(self, device: str = "cpu", lang_code: str = "a"):
        self._device = device
        self._lang_code = lang_code
        self._pipeline = None  # lazy: don't load weights at import

    def capabilities(self) -> Capabilities:
        return Capabilities(
            name="kokoro-82m",
            license=License.APACHE_2_0,
            languages=frozenset({"en"}),
            supports_voice_cloning=False,
            requires_gpu=False,
        )

    def _load(self):
        if self._pipeline is None:
            from kokoro import KPipeline

            logger.info("kokoro.loading", device=self._device)
            self._pipeline = KPipeline(lang_code=self._lang_code, device=self._device)
        return self._pipeline

    async def synthesize(self, req: TTSRequest) -> AudioAsset:
        if req.language != "en":
            raise ProviderError(
                f"KokoroTTS received language={req.language!r} but declares English "
                f"only. The registry should not have routed this -- check "
                f"ProviderRegistry.tts_for()."
            )
        if not req.text.strip():
            raise ProviderError("KokoroTTS received empty text.")

        out = req.out_path or Path(f"/tmp/render/voice_{abs(hash(req.text)):x}.wav")
        out.parent.mkdir(parents=True, exist_ok=True)

        voice = VOICE_MAP.get(req.voice_id, DEFAULT_VOICE)

        # Kokoro is sync + CPU/GPU-bound; keep the event loop free.
        audio = await asyncio.to_thread(self._synth_sync, req.text, voice, req.speed)

        sf.write(str(out), audio, SAMPLE_RATE)

        # Duration is MEASURED from the samples, never estimated from a
        # words-per-second constant. Pipeline timing depends on this being real.
        duration = len(audio) / SAMPLE_RATE

        logger.info(
            "kokoro.synthesized",
            voice=voice,
            chars=len(req.text),
            duration=f"{duration:.2f}s",
        )

        return AudioAsset(
            path=out,
            duration_s=duration,
            sample_rate=SAMPLE_RATE,
            provenance=Provenance(provider="kokoro-82m", model=MODEL_ID, version="v1.0"),
        )

    def _synth_sync(self, text: str, voice: str, speed: float):
        import numpy as np

        pipeline = self._load()
        chunks = [audio for _, _, audio in pipeline(text, voice=voice, speed=speed)]

        if not chunks:
            raise ProviderError(f"Kokoro produced no audio for text: {text[:80]!r}")

        return np.concatenate(chunks)
