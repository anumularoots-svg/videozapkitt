"""
Wan 2.1 video provider. Apache-2.0, commercial-safe (outputs unrestricted).

Phase 0 uses T2V-1.3B: ~8.2GB VRAM, runs on a single 24GB card with room to
spare. Quality is decent, not cinematic -- that is the accepted trade for fast,
cheap iteration. Judge Phase 0 on whether audio/subtitles/video stay locked,
NOT on beauty. Beauty is Phase 6's problem.

Tier reference (verified, ARCHITECTURE.md §1.2):
  T2V-1.3B          ~8.2 GB   -> g5.xlarge / any 24GB card
  I2V-14B @480p     40-48 GB  -> g5.12xlarge / A100 -- 5-10x the cost
  14B @720p         65-80 GB  -> A100 80GB

Wan generates short clips (~5s). A 60s video is 12+ clips that must hold the
same character. That chaining problem -- not the deployment -- is the real risk
in this project.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import structlog

from providers.base import (
    Capabilities,
    License,
    Provenance,
    ProviderError,
    VideoAsset,
    VideoRequest,
)

logger = structlog.get_logger()

# The diffusers integration loads from the "-Diffusers" repos, NOT the original
# Wan checkpoints. WanPipeline.from_pretrained on the base repo would fail --
# it expects the diffusers-format layout (subfolder vae, etc.).
TIER_1_3B = "Wan-AI/Wan2.1-T2V-1.3B-Diffusers"
TIER_14B = "Wan-AI/Wan2.1-I2V-14B-480P-Diffusers"

VRAM_GB = {TIER_1_3B: 8.2, TIER_14B: 48.0}

# Wan's practical per-clip ceiling. Longer requests are split upstream.
MAX_CLIP_S = 5.0

DEFAULT_NEGATIVE = (
    "blurry, low quality, distorted, watermark, text, deformed hands, "
    "extra limbs, jpeg artifacts, oversaturated"
)


class WanVideo:
    """Wan 2.1 via diffusers."""

    def __init__(self, model_id: str = TIER_1_3B, device: str = "cuda", dtype: str = "bf16"):
        self._model_id = model_id
        self._device = device
        self._dtype = dtype
        self._pipe = None

    def capabilities(self) -> Capabilities:
        return Capabilities(
            name=f"wan2.1-{'1.3b' if self._model_id == TIER_1_3B else '14b'}",
            license=License.APACHE_2_0,
            max_duration_s=MAX_CLIP_S,
            aspect_ratios=frozenset({"9:16", "16:9", "1:1", "4:5"}),
            requires_gpu=True,
            min_vram_gb=VRAM_GB.get(self._model_id, 8.2),
        )

    def _load(self):
        if self._pipe is None:
            import torch
            from diffusers import AutoencoderKLWan, WanPipeline

            logger.info("wan.loading", model=self._model_id, device=self._device)
            torch_dtype = torch.bfloat16 if self._dtype == "bf16" else torch.float16

            vae = AutoencoderKLWan.from_pretrained(
                self._model_id, subfolder="vae", torch_dtype=torch.float32
            )
            self._pipe = WanPipeline.from_pretrained(
                self._model_id, vae=vae, torch_dtype=torch_dtype
            )
            self._pipe.to(self._device)
        return self._pipe

    async def generate(self, req: VideoRequest) -> VideoAsset:
        if req.duration_s > MAX_CLIP_S:
            raise ProviderError(
                f"Requested {req.duration_s:.1f}s but Wan 2.1 caps at {MAX_CLIP_S}s "
                f"per clip. Split the scene upstream and chain the clips -- see "
                f"pipeline/stages/video.py."
            )

        out = req.out_path or Path(f"/tmp/render/clip_{abs(hash(req.prompt)):x}.mp4")
        out.parent.mkdir(parents=True, exist_ok=True)

        # Wan wants a 4n+1 frame count.
        num_frames = int(req.duration_s * req.fps)
        num_frames = max(5, ((num_frames - 1) // 4) * 4 + 1)

        await asyncio.to_thread(self._generate_sync, req, out, num_frames)

        actual_duration = num_frames / req.fps
        logger.info(
            "wan.generated",
            frames=num_frames,
            duration=f"{actual_duration:.2f}s",
            size=f"{req.width}x{req.height}",
        )

        return VideoAsset(
            path=out,
            duration_s=actual_duration,
            width=req.width,
            height=req.height,
            fps=req.fps,
            provenance=Provenance(
                provider="wan2.1",
                model=self._model_id,
                version="2.1",
                seed=req.seed,
            ),
        )

    def _generate_sync(self, req: VideoRequest, out: Path, num_frames: int) -> None:
        import torch
        from diffusers.utils import export_to_video

        pipe = self._load()
        generator = (
            torch.Generator(device=self._device).manual_seed(req.seed)
            if req.seed is not None
            else None
        )

        result = pipe(
            prompt=req.prompt,
            negative_prompt=req.negative_prompt or DEFAULT_NEGATIVE,
            height=req.height,
            width=req.width,
            num_frames=num_frames,
            guidance_scale=5.0,
            generator=generator,
        )
        export_to_video(result.frames[0], str(out), fps=req.fps)
