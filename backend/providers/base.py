"""
Provider base layer.

Every AI capability (LLM, TTS, image, video, music, alignment) sits behind a
Protocol here. Pipeline stages depend on these Protocols, never on a concrete
model. That is what makes Kokoro->IndicF5 and Wan-1.3B->Wan-14B config changes
instead of rewrites, and what makes the worker host (RunPod now, AWS at Phase 4)
irrelevant to the pipeline.

Two rules this module enforces:

1. FAIL LOUD. A provider declares what it supports via `capabilities()`. Asking
   for something unsupported raises `UnsupportedCapability`. It must never
   silently substitute (the pre-rewrite voice agent accepted `language="Telugu"`
   and narrated in English -- that class of bug is what this prevents).

2. LICENSE IS DATA. Every provider declares its license. Non-commercial weights
   in a commercial path is a lawsuit, not a shortcut, so CI can assert on this.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Protocol, runtime_checkable


# ── Licensing ──────────────────────────────────────────


class License(Enum):
    """Model weight licenses, tagged with whether output may be sold.

    `commercial_safe` gates the subscription product. See ARCHITECTURE.md §2.
    """

    APACHE_2_0 = ("Apache-2.0", True)
    MIT = ("MIT", True)
    BSD_3 = ("BSD-3-Clause", True)
    LLAMA = ("Llama Community", True)  # commercial OK under 700M MAU
    STABILITY_COMMUNITY = ("Stability Community", True)  # OK under $1M revenue
    CC_BY_NC = ("CC-BY-NC", False)  # MusicGen -- do not ship
    NON_COMMERCIAL = ("Non-Commercial", False)  # FLUX.1-dev -- do not ship
    UNVERIFIED = ("Unverified", False)  # deny by default until checked

    def __init__(self, label: str, commercial_safe: bool):
        self.label = label
        self.commercial_safe = commercial_safe


class UnsupportedCapability(Exception):
    """Raised when no provider satisfies a request. Never substitute silently."""


class ProviderError(Exception):
    """Raised when a provider fails at inference time."""


# ── Capability declaration ─────────────────────────────


@dataclass(frozen=True)
class Capabilities:
    """What a provider can actually do. Used by the registry to route.

    `languages` holds ISO 639-1 codes. Empty means language is not applicable
    (image/video/music providers).
    """

    name: str
    license: License
    languages: frozenset[str] = frozenset()
    max_duration_s: float | None = None
    aspect_ratios: frozenset[str] = frozenset()
    supports_voice_cloning: bool = False
    requires_gpu: bool = False
    min_vram_gb: float | None = None

    def supports_language(self, language: str) -> bool:
        return language in self.languages


# ── Assets ─────────────────────────────────────────────
#
# Every asset carries the model, version and seed that produced it. Without
# this, a quality regression is unfixable: you cannot diff what you did not
# record. ARCHITECTURE.md §9.


@dataclass(frozen=True)
class Provenance:
    provider: str
    model: str
    version: str = "unknown"
    seed: int | None = None


@dataclass(frozen=True)
class AudioAsset:
    path: Path
    duration_s: float  # measured from the file, never estimated
    sample_rate: int
    provenance: Provenance


@dataclass(frozen=True)
class ImageAsset:
    path: Path
    width: int
    height: int
    provenance: Provenance


@dataclass(frozen=True)
class VideoAsset:
    path: Path
    duration_s: float
    width: int
    height: int
    fps: int
    provenance: Provenance


@dataclass(frozen=True)
class WordTiming:
    word: str
    start_s: float
    end_s: float


@dataclass(frozen=True)
class Alignment:
    """Word-level timings measured against real audio.

    This is what makes subtitles exact. Distributing scene time evenly across
    text chunks (the pre-rewrite approach) guarantees drift.
    """

    words: list[WordTiming]
    provenance: Provenance


# ── Requests ───────────────────────────────────────────


@dataclass(frozen=True)
class TTSRequest:
    text: str
    language: str
    voice_id: str
    speed: float = 1.0
    # Few-shot voice cloning (IndicF5, Phase 2). IndicF5 needs BOTH a reference
    # audio clip AND its transcript -- the transcript is not optional for that
    # model. Kokoro ignores both. Present now so the Phase 2 provider slots in
    # without changing this dataclass.
    reference_audio: Path | None = None
    reference_text: str | None = None
    out_path: Path | None = None


@dataclass(frozen=True)
class ImageRequest:
    prompt: str
    negative_prompt: str = ""
    width: int = 1080
    height: int = 1920
    seed: int | None = None
    identity_reference: Path | None = None  # IP-Adapter / InstantID
    out_path: Path | None = None


@dataclass(frozen=True)
class VideoRequest:
    prompt: str
    duration_s: float
    first_frame: Path | None = None  # I2V; also the continuity chain
    negative_prompt: str = ""
    width: int = 480
    height: int = 854
    fps: int = 16
    seed: int | None = None
    out_path: Path | None = None


@dataclass(frozen=True)
class MusicRequest:
    prompt: str
    duration_s: float
    seed: int | None = None
    out_path: Path | None = None


# ── Protocols ──────────────────────────────────────────


@runtime_checkable
class Provider(Protocol):
    def capabilities(self) -> Capabilities: ...


@runtime_checkable
class LLMProvider(Provider, Protocol):
    async def generate(self, system: str, user: str, temperature: float = 0.7) -> str: ...
    async def generate_json(self, system: str, user: str, temperature: float = 0.3) -> dict: ...


@runtime_checkable
class TTSProvider(Provider, Protocol):
    async def synthesize(self, req: TTSRequest) -> AudioAsset: ...


@runtime_checkable
class ImageProvider(Provider, Protocol):
    async def generate(self, req: ImageRequest) -> ImageAsset: ...


@runtime_checkable
class VideoProvider(Provider, Protocol):
    async def generate(self, req: VideoRequest) -> VideoAsset: ...


@runtime_checkable
class MusicProvider(Provider, Protocol):
    async def generate(self, req: MusicRequest) -> AudioAsset: ...


@runtime_checkable
class AlignmentProvider(Provider, Protocol):
    async def align(self, audio: Path, text: str, language: str) -> Alignment: ...
