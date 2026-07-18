"""
Capability-based provider routing.

Ask for what you need; the registry finds a provider that declares it can do it,
or raises. There is no fallback-to-something-close, because a fallback is how
`language="Telugu"` quietly becomes an English narration.
"""

from __future__ import annotations

import structlog

from .base import (
    AlignmentProvider,
    ImageProvider,
    License,
    LLMProvider,
    MusicProvider,
    Provider,
    TTSProvider,
    UnsupportedCapability,
    VideoProvider,
)

logger = structlog.get_logger()


class ProviderRegistry:
    """Holds registered providers and routes requests by declared capability."""

    def __init__(self, *, require_commercial_safe: bool = False):
        self._tts: list[TTSProvider] = []
        self._llm: list[LLMProvider] = []
        self._image: list[ImageProvider] = []
        self._video: list[VideoProvider] = []
        self._music: list[MusicProvider] = []
        self._align: list[AlignmentProvider] = []
        self.require_commercial_safe = require_commercial_safe

    # ── Registration ───────────────────────────────────

    def register(self, provider: Provider) -> None:
        """Register a provider under every Protocol it satisfies.

        With `require_commercial_safe`, a non-commercial provider is rejected at
        registration -- the earliest possible point, so it can never reach a
        paying customer's video. CI flips this on.
        """
        caps = provider.capabilities()

        if self.require_commercial_safe and not caps.license.commercial_safe:
            raise ValueError(
                f"Provider {caps.name!r} is licensed {caps.license.label!r}, which "
                f"does not permit commercial use. Refusing to register it in a "
                f"commercial-safe registry. See ARCHITECTURE.md §2."
            )

        buckets = [
            (LLMProvider, self._llm),
            (TTSProvider, self._tts),
            (ImageProvider, self._image),
            (VideoProvider, self._video),
            (MusicProvider, self._music),
            (AlignmentProvider, self._align),
        ]

        matched = False
        for protocol, bucket in buckets:
            if isinstance(provider, protocol):
                bucket.append(provider)
                matched = True

        if not matched:
            raise ValueError(
                f"Provider {caps.name!r} satisfies no known Protocol. "
                f"It cannot be routed to."
            )

        logger.info(
            "provider.registered",
            name=caps.name,
            license=caps.license.label,
            languages=sorted(caps.languages) or None,
        )

    # ── Routing ────────────────────────────────────────

    def tts_for(self, language: str) -> TTSProvider:
        """Route TTS by language.

        Kokoro handles English; IndicF5 handles Telugu/Hindi and the rest of the
        Indic set. Neither can cover for the other, so an unroutable language is
        an error -- not a reason to fall back.
        """
        for p in self._tts:
            if p.capabilities().supports_language(language):
                return p

        supported = sorted({
            lang for p in self._tts for lang in p.capabilities().languages
        })
        raise UnsupportedCapability(
            f"No TTS provider supports language {language!r}. "
            f"Registered providers cover: {supported or '(none registered)'}."
        )

    def llm(self) -> LLMProvider:
        return self._require_one(self._llm, "LLM")

    def image(self) -> ImageProvider:
        return self._require_one(self._image, "image")

    def video(self) -> VideoProvider:
        return self._require_one(self._video, "video")

    def music(self) -> MusicProvider:
        return self._require_one(self._music, "music")

    def alignment(self) -> AlignmentProvider:
        return self._require_one(self._align, "alignment")

    @staticmethod
    def _require_one(bucket: list, kind: str):
        if not bucket:
            raise UnsupportedCapability(f"No {kind} provider is registered.")
        return bucket[0]

    # ── Introspection ──────────────────────────────────

    def supported_languages(self) -> set[str]:
        """Languages the pipeline can actually voice today.

        The API should read this rather than advertising a hardcoded list --
        the two drift apart otherwise.
        """
        return {lang for p in self._tts for lang in p.capabilities().languages}

    def audit(self) -> list[dict]:
        """Every registered provider with its license. Feeds the admin dashboard
        and the CI license gate."""
        seen: dict[int, Provider] = {}
        for bucket in (self._llm, self._tts, self._image, self._video, self._music, self._align):
            for p in bucket:
                seen[id(p)] = p

        rows = []
        for p in seen.values():
            caps = p.capabilities()
            rows.append({
                "name": caps.name,
                "license": caps.license.label,
                "commercial_safe": caps.license.commercial_safe,
                "languages": sorted(caps.languages),
                "requires_gpu": caps.requires_gpu,
                "min_vram_gb": caps.min_vram_gb,
            })
        return sorted(rows, key=lambda r: r["name"])

    def non_commercial(self) -> list[str]:
        """Providers that must not ship in the subscription product."""
        return [r["name"] for r in self.audit() if not r["commercial_safe"]]
