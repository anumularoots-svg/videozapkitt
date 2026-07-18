"""
Registry construction from settings.

The one place that knows which concrete models are wired in. Swapping Kokoro for
IndicF5 at Phase 2, or 1.3B for 14B at Phase 6, is an edit here -- pipeline code
never names a model.
"""

from __future__ import annotations

import structlog

from config import get_settings
from providers.align.whisper_align import WhisperAligner
from providers.image.flux_image import FluxImage
from providers.llm.openai_compat import OpenAICompatLLM
from providers.music.stable_audio import StableAudioMusic
from providers.registry import ProviderRegistry
from providers.tts.kokoro_tts import KokoroTTS
from providers.video.wan_video import WanVideo

logger = structlog.get_logger()


def build_registry(*, require_commercial_safe: bool = True) -> ProviderRegistry:
    """Wire up the Phase 0 provider set.

    `require_commercial_safe` defaults ON: a non-commercial model is rejected at
    registration rather than discovered in a paid customer's video.
    """
    s = get_settings()
    registry = ProviderRegistry(require_commercial_safe=require_commercial_safe)

    registry.register(OpenAICompatLLM(
        base_url=s.llm_api_url,
        model=s.llm_model,
        api_key=s.llm_api_key or None,
    ))

    # English only at Phase 0-1. Telugu/Hindi arrive with IndicF5 at Phase 2;
    # until then the registry raises for them rather than faking it.
    registry.register(KokoroTTS(device=s.tts_device))

    registry.register(WhisperAligner(
        model_size=s.whisper_model_size,
        device=s.whisper_device,
    ))
    registry.register(FluxImage(model_id=s.image_model, device=s.gpu_device))
    registry.register(WanVideo(model_id=s.video_model, device=s.gpu_device))
    registry.register(StableAudioMusic(device=s.gpu_device))

    unsafe = registry.non_commercial()
    if unsafe:  # unreachable when require_commercial_safe -- belt and braces
        logger.warning("registry.non_commercial_providers", providers=unsafe)

    logger.info(
        "registry.ready",
        providers=len(registry.audit()),
        languages=sorted(registry.supported_languages()),
    )
    return registry
