"""
Pipeline tests -- pure logic only.

These run anywhere: no GPU, no model weights, no network. That is deliberate.
The logic that silently breaks a video (timing, routing, subtitle placement) is
all testable without inference, and every test below targets a failure mode the
pre-rewrite code actually shipped with.

GPU paths are exercised by `run_phase0.py` on a real box; faking them here would
prove nothing.

Run: pytest backend/tests/ -v
"""

from __future__ import annotations

from pathlib import Path

import pytest

from providers.base import (
    Alignment,
    AudioAsset,
    Capabilities,
    License,
    Provenance,
    TTSRequest,
    UnsupportedCapability,
    WordTiming,
)
from providers.registry import ProviderRegistry


# ── Fakes ──────────────────────────────────────────────


class FakeTTS:
    """TTS with a controllable duration, so timing logic can be asserted exactly."""

    def __init__(self, languages: set[str], seconds_per_word: float = 0.4):
        self._languages = frozenset(languages)
        self._spw = seconds_per_word
        self.calls: list[str] = []

    def capabilities(self) -> Capabilities:
        return Capabilities(
            name=f"fake-tts-{'-'.join(sorted(self._languages))}",
            license=License.APACHE_2_0,
            languages=self._languages,
        )

    async def synthesize(self, req: TTSRequest) -> AudioAsset:
        self.calls.append(req.text)
        return AudioAsset(
            path=req.out_path or Path("/tmp/fake.wav"),
            duration_s=len(req.text.split()) * self._spw,
            sample_rate=24_000,
            provenance=Provenance(provider="fake", model="fake"),
        )


def _alignment(words: list[tuple[str, float, float]]) -> Alignment:
    return Alignment(
        words=[WordTiming(w, s, e) for w, s, e in words],
        provenance=Provenance(provider="fake", model="fake"),
    )


# ── Registry: fail loud, never substitute ──────────────


def test_registry_routes_by_language():
    registry = ProviderRegistry()
    english = FakeTTS({"en"})
    indic = FakeTTS({"te", "hi"})
    registry.register(english)
    registry.register(indic)

    assert registry.tts_for("en") is english
    assert registry.tts_for("te") is indic
    assert registry.tts_for("hi") is indic


def test_registry_raises_for_unsupported_language():
    """The core regression guard.

    The old voice agent accepted language="Telugu" and narrated in English --
    all 15 of its presets were English Kokoro voices. An unroutable language
    must raise, never fall back.
    """
    registry = ProviderRegistry()
    registry.register(FakeTTS({"en"}))

    with pytest.raises(UnsupportedCapability) as exc:
        registry.tts_for("te")

    assert "te" in str(exc.value)


def test_registry_rejects_non_commercial_when_strict():
    class NonCommercialTTS(FakeTTS):
        def capabilities(self) -> Capabilities:
            return Capabilities(
                name="musicgen-like",
                license=License.CC_BY_NC,
                languages=frozenset({"en"}),
            )

    registry = ProviderRegistry(require_commercial_safe=True)
    with pytest.raises(ValueError, match="commercial"):
        registry.register(NonCommercialTTS({"en"}))


def test_supported_languages_reflects_registration():
    registry = ProviderRegistry()
    registry.register(FakeTTS({"en"}))
    assert registry.supported_languages() == {"en"}

    registry.register(FakeTTS({"te", "hi"}))
    assert registry.supported_languages() == {"en", "te", "hi"}


def test_license_commercial_flags():
    assert License.APACHE_2_0.commercial_safe   # Wan 2.1, FLUX schnell, Kokoro
    assert License.MIT.commercial_safe          # IndicF5, Whisper
    assert not License.CC_BY_NC.commercial_safe        # MusicGen
    assert not License.NON_COMMERCIAL.commercial_safe  # FLUX.1-dev
    assert not License.UNVERIFIED.commercial_safe      # deny by default


# ── Reconcile: voice is the clock ──────────────────────


@pytest.mark.asyncio
async def test_reconcile_uses_measured_duration_not_planned(tmp_path):
    from pipeline.reconcile import reconcile_timing

    # 10 words at 0.4s/word = 4.0s of speech, but the plan said 2.0s.
    scenes = [{"id": 1, "duration": 2.0, "script": " ".join(["word"] * 10)}]

    timed, report = await reconcile_timing(
        scenes, FakeTTS({"en"}, seconds_per_word=0.4), "en", tmp_path
    )

    assert timed[0].actual_duration_s == pytest.approx(4.0)
    assert report.planned_duration_s == 2.0
    assert report.drift_s > 0  # recorded, not hidden


@pytest.mark.asyncio
async def test_reconcile_timeline_has_no_accumulated_drift(tmp_path):
    """Each scene starts where the previous ACTUALLY ended.

    Laid out on planned durations, scene 3 would start at 4.0s while its audio
    starts at 8.0s. That 4s gap is the accumulated-drift bug.
    """
    from pipeline.reconcile import reconcile_timing

    scenes = [
        {"id": i, "duration": 2.0, "script": " ".join(["word"] * 10)} for i in (1, 2, 3)
    ]

    timed, _ = await reconcile_timing(
        scenes, FakeTTS({"en"}, seconds_per_word=0.4), "en", tmp_path
    )

    assert timed[0].start_s == pytest.approx(0.0)
    for prev, nxt in zip(timed, timed[1:]):
        assert nxt.start_s == pytest.approx(prev.end_s)


@pytest.mark.asyncio
async def test_reconcile_shortens_overlong_lines(tmp_path):
    from pipeline.reconcile import reconcile_timing

    scenes = [{"id": 1, "duration": 2.0, "script": " ".join(["word"] * 20)}]

    async def shorten(text: str, target_s: float) -> str:
        return " ".join(["word"] * 4)  # 1.6s

    timed, report = await reconcile_timing(
        scenes, FakeTTS({"en"}, seconds_per_word=0.4), "en", tmp_path, shorten_fn=shorten
    )

    assert report.scenes_shortened == [1]
    assert timed[0].actual_duration_s == pytest.approx(1.6)


@pytest.mark.asyncio
async def test_reconcile_gives_up_shortening_rather_than_looping(tmp_path):
    """A shortener that never shortens must terminate, not spin."""
    from pipeline.reconcile import reconcile_timing

    scenes = [{"id": 1, "duration": 1.0, "script": " ".join(["word"] * 20)}]

    async def useless_shorten(text: str, target_s: float) -> str:
        return text

    timed, report = await reconcile_timing(
        scenes, FakeTTS({"en"}, seconds_per_word=0.4), "en", tmp_path,
        shorten_fn=useless_shorten,
    )

    assert report.scenes_shortened == [1]
    assert timed[0].actual_duration_s == pytest.approx(8.0)  # accepted, and visible


@pytest.mark.asyncio
async def test_reconcile_rejects_scene_without_script(tmp_path):
    from pipeline.reconcile import reconcile_timing

    with pytest.raises(ValueError, match="no script"):
        await reconcile_timing(
            [{"id": 1, "duration": 2.0, "script": "  "}], FakeTTS({"en"}), "en", tmp_path
        )


@pytest.mark.asyncio
async def test_video_duration_pads_past_speech(tmp_path):
    """Clips must outlast their speech, or the last word lands on the cut."""
    from pipeline.reconcile import reconcile_timing

    scenes = [{"id": 1, "duration": 2.0, "script": " ".join(["word"] * 5)}]
    timed, _ = await reconcile_timing(
        scenes, FakeTTS({"en"}, seconds_per_word=0.4), "en", tmp_path
    )

    assert timed[0].video_duration_s > timed[0].actual_duration_s


# ── Subtitles: built from real word timings ────────────


def test_cues_use_real_word_boundaries():
    from pipeline.subtitles import build_cues

    cues = build_cues(_alignment([("Hello", 0.0, 0.5), ("world", 0.6, 1.2)]))

    assert len(cues) == 1
    assert cues[0].start_s == pytest.approx(0.0)
    assert cues[0].end_s == pytest.approx(1.2)
    assert cues[0].text == "Hello world"


def test_cues_offset_onto_global_timeline():
    from pipeline.subtitles import build_cues

    cues = build_cues(_alignment([("Hello", 0.0, 0.5)]), offset_s=10.0)
    assert cues[0].start_s == pytest.approx(10.0)


def test_cue_breaks_on_phrase_gap():
    from pipeline.subtitles import build_cues

    # 1.0s of silence between words -- a natural phrase break.
    cues = build_cues(_alignment([("one", 0.0, 0.4), ("two", 1.4, 1.8)]))
    assert len(cues) == 2


def test_cue_breaks_on_sentence_end():
    from pipeline.subtitles import build_cues

    cues = build_cues(_alignment([("Done.", 0.0, 0.4), ("Next", 0.5, 0.9)]))
    assert len(cues) == 2


def test_subtitle_drift_is_zero_by_construction():
    """Cues derive from word onsets, so drift should be ~0.

    Nonzero means something re-timed cues after alignment -- exactly what the
    even-split approach did by design.
    """
    from pipeline.subtitles import build_cues, max_drift_s

    alignment = _alignment([("Hello", 0.0, 0.5), ("world", 0.6, 1.2)])
    assert max_drift_s(build_cues(alignment), alignment) == pytest.approx(0.0)


def test_srt_time_format():
    from pipeline.subtitles import _srt_time

    assert _srt_time(0.0) == "00:00:00,000"
    assert _srt_time(1.5) == "00:00:01,500"
    assert _srt_time(61.25) == "00:01:01,250"
    assert _srt_time(3661.001) == "01:01:01,001"


def test_srt_renders_sequential_indices():
    from pipeline.subtitles import build_cues, render_srt

    srt = render_srt(build_cues(
        _alignment([("one", 0.0, 0.4), ("two", 1.4, 1.8), ("three", 3.0, 3.4)])
    ))

    assert srt.startswith("1\n")
    assert "\n2\n" in srt
    assert "-->" in srt


def test_empty_alignment_yields_no_cues():
    from pipeline.subtitles import build_cues

    assert build_cues(_alignment([])) == []


# ── Character library: honest about what's missing ─────


def test_character_library_has_fifteen():
    from characters import LIBRARY

    assert len(LIBRARY) == 15


def test_all_character_packs_are_missing_reference_images(tmp_path):
    """Documents a real gap: 15 characters described, 0 usable.

    Phase 3's job is to make this test's expectation flip. Until then, the
    "character consistency engine" has no assets to be consistent about.
    """
    from characters import LIBRARY, missing_packs

    assert set(missing_packs(tmp_path)) == set(LIBRARY)
