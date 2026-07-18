"""
FLUX.1-schnell keyframe provider. Apache-2.0, commercial-safe.

SCHNELL, NOT DEV. FLUX.1-dev is non-commercial licensed and cannot ship in a
subscription product -- it is the single easiest license mistake to make here,
because dev is the better-known model and the one the old .env pointed at.
This module hard-refuses dev at construction; see ARCHITECTURE.md §2.

Keyframes exist so the video model gets a strong first frame to animate from,
and so character identity can be pinned (IP-Adapter, Phase 3) at image time
where it is far cheaper to retry than at video time.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import structlog

from providers.base import (
    Capabilities,
    ImageAsset,
    ImageRequest,
    License,
    Provenance,
    ProviderError,
)

logger = structlog.get_logger()

SCHNELL = "black-forest-labs/FLUX.1-schnell"
DEV = "black-forest-labs/FLUX.1-dev"  # non-commercial -- referenced only to reject

# schnell is distilled for very few steps; more does not help.
SCHNELL_STEPS = 4


class FluxImage:
    """FLUX.1-schnell via diffusers."""

    def __init__(self, model_id: str = SCHNELL, device: str = "cuda"):
        if model_id == DEV:
            raise ValueError(
                "FLUX.1-dev is non-commercial licensed and must not be used in a "
                "product you intend to charge for. Use FLUX.1-schnell (Apache-2.0). "
                "See ARCHITECTURE.md §2."
            )
        self._model_id = model_id
        self._device = device
        self._pipe = None

    def capabilities(self) -> Capabilities:
        return Capabilities(
            name="flux.1-schnell",
            license=License.APACHE_2_0,
            aspect_ratios=frozenset({"9:16", "16:9", "1:1", "4:5"}),
            requires_gpu=True,
            min_vram_gb=12.0,
        )

    def _load(self):
        if self._pipe is None:
            import torch
            from diffusers import FluxPipeline

            logger.info("flux.loading", model=self._model_id)
            self._pipe = FluxPipeline.from_pretrained(
                self._model_id, torch_dtype=torch.bfloat16
            )
            # Keyframes are generated between video clips; keep VRAM headroom for Wan.
            self._pipe.enable_model_cpu_offload()
        return self._pipe

    async def generate(self, req: ImageRequest) -> ImageAsset:
        if req.identity_reference is not None:
            raise ProviderError(
                "Identity conditioning (IP-Adapter) is not wired yet -- that is "
                "Phase 3. Failing rather than silently ignoring the reference and "
                "returning a stranger's face."
            )

        out = req.out_path or Path(f"/tmp/render/key_{abs(hash(req.prompt)):x}.png")
        out.parent.mkdir(parents=True, exist_ok=True)

        # FLUX needs dimensions divisible by 16.
        width = (req.width // 16) * 16
        height = (req.height // 16) * 16

        await asyncio.to_thread(self._generate_sync, req, out, width, height)

        logger.info("flux.generated", size=f"{width}x{height}", seed=req.seed)

        return ImageAsset(
            path=out,
            width=width,
            height=height,
            provenance=Provenance(
                provider="flux", model=self._model_id, version="schnell", seed=req.seed
            ),
        )

    def _generate_sync(self, req: ImageRequest, out: Path, width: int, height: int) -> None:
        import torch

        pipe = self._load()
        generator = (
            torch.Generator("cpu").manual_seed(req.seed) if req.seed is not None else None
        )

        image = pipe(
            prompt=req.prompt,
            width=width,
            height=height,
            num_inference_steps=SCHNELL_STEPS,
            guidance_scale=0.0,  # schnell is guidance-distilled
            generator=generator,
        ).images[0]

        image.save(str(out))
