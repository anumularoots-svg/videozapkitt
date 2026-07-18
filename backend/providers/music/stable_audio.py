"""
Stable Audio Open BGM provider. Stability Community License.

Commercial use is permitted UNDER $1M annual revenue. Above that you renegotiate
with Stability. That is a real ceiling on the subscription plan -- it is tracked
as open decision #5 in ARCHITECTURE.md §12, not hidden here.

NOT MusicGen: its weights are CC-BY-NC and cannot ship in a paid product.

The model caps around ~47s, so a 60s video needs stitching. We generate PER ACT
(2-3 segments), not per scene -- per-scene music restarts every few seconds and
sounds jarring rather than cinematic.
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
    MusicRequest,
    Provenance,
    ProviderError,
)

logger = structlog.get_logger()

MODEL_ID = "stabilityai/stable-audio-open-1.0"
SAMPLE_RATE = 44_100
MAX_DURATION_S = 47.0


class StableAudioMusic:
    """Stable Audio Open 1.0 via diffusers."""

    def __init__(self, device: str = "cuda"):
        self._device = device
        self._pipe = None

    def capabilities(self) -> Capabilities:
        return Capabilities(
            name="stable-audio-open-1.0",
            license=License.STABILITY_COMMUNITY,
            max_duration_s=MAX_DURATION_S,
            requires_gpu=True,
            min_vram_gb=8.0,
        )

    def _load(self):
        if self._pipe is None:
            import torch
            from diffusers import StableAudioPipeline

            logger.info("stable_audio.loading")
            self._pipe = StableAudioPipeline.from_pretrained(
                MODEL_ID, torch_dtype=torch.float16
            )
            self._pipe.to(self._device)
        return self._pipe

    async def generate(self, req: MusicRequest) -> AudioAsset:
        if req.duration_s > MAX_DURATION_S:
            raise ProviderError(
                f"Requested {req.duration_s:.1f}s but Stable Audio Open caps at "
                f"{MAX_DURATION_S}s. Split into acts and crossfade -- see "
                f"pipeline/stages/music.py."
            )

        out = req.out_path or Path(f"/tmp/render/bgm_{abs(hash(req.prompt)):x}.wav")
        out.parent.mkdir(parents=True, exist_ok=True)

        audio = await asyncio.to_thread(self._generate_sync, req)
        sf.write(str(out), audio.T, SAMPLE_RATE)

        duration = audio.shape[-1] / SAMPLE_RATE
        logger.info("stable_audio.generated", duration=f"{duration:.2f}s")

        return AudioAsset(
            path=out,
            duration_s=duration,
            sample_rate=SAMPLE_RATE,
            provenance=Provenance(
                provider="stable-audio-open", model=MODEL_ID, version="1.0", seed=req.seed
            ),
        )

    def _generate_sync(self, req: MusicRequest):
        import torch

        pipe = self._load()
        generator = (
            torch.Generator(self._device).manual_seed(req.seed)
            if req.seed is not None
            else None
        )

        result = pipe(
            prompt=req.prompt,
            negative_prompt="low quality, distorted, vocals, singing, speech",
            num_inference_steps=100,
            audio_end_in_s=req.duration_s,
            num_waveforms_per_prompt=1,
            generator=generator,
        )
        return result.audios[0].T.float().cpu().numpy()
