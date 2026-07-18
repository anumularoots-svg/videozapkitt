"""
Script stage: idea -> scenes with dialogue and visual prompts.

Also exposes `shorten()`, which reconcile.py calls when a generated line runs
long. Pacing here is a GUESS -- reconcile measures the truth. Words-per-second
differs enough across languages that no constant survives contact with Telugu.
"""

from __future__ import annotations

import structlog

from providers.base import LLMProvider, ProviderError

logger = structlog.get_logger()

SYSTEM = """You are a screenwriter for short-form vertical video.

Given an idea, produce a scene-by-scene plan.

RULES:
- Each scene: ONE spoken line, naturally speakable aloud
- Aim for ~{wps} words per second of scene duration (a guide, not a rule --
  the system measures real speech length afterwards)
- visual_prompt describes what the CAMERA SEES. No dialogue, no character names.
  Be concrete: subject, action, setting, lighting, camera angle.
- Give the whole thing a narrative arc: hook, development, payoff
- music_mood: one of soft, epic, emotional, hopeful, upbeat, tense, motivational

Respond with JSON:
{{
  "title": "...",
  "scenes": [
    {{
      "id": 1,
      "duration": 5.0,
      "script": "The one spoken line.",
      "visual_prompt": "Concrete description of the shot.",
      "emotion": "neutral",
      "music_mood": "soft"
    }}
  ]
}}"""

SHORTEN_SYSTEM = """You tighten voice-over lines to fit a time budget.
Return ONLY the rewritten line -- no quotes, no explanation, no preamble.
Keep the meaning and tone. Cut words, don't summarise into a new sentence."""

WORDS_PER_SECOND = 2.5  # first guess only; reconcile.py measures reality


class ScriptStage:
    def __init__(self, llm: LLMProvider):
        self._llm = llm

    async def generate(
        self, idea: str, duration_s: int, language: str, scene_count: int
    ) -> dict:
        per_scene = duration_s / scene_count

        user = f"""Idea: {idea}
Language: {language}
Total duration: {duration_s} seconds
Number of scenes: EXACTLY {scene_count}
Duration per scene: about {per_scene:.1f} seconds
Target words per scene: about {int(per_scene * WORDS_PER_SECOND)}

Write the scene plan in {language}."""

        result = await self._llm.generate_json(SYSTEM.format(wps=WORDS_PER_SECOND), user)

        scenes = result.get("scenes", [])
        if not scenes:
            raise ProviderError(
                f"Script stage returned no scenes for idea {idea[:60]!r}. "
                f"Nothing downstream can run."
            )

        if len(scenes) != scene_count:
            logger.warning(
                "script.scene_count_mismatch",
                requested=scene_count,
                got=len(scenes),
            )
            scenes = scenes[:scene_count]

        for i, scene in enumerate(scenes, start=1):
            scene["id"] = i
            scene.setdefault("duration", per_scene)
            scene.setdefault("emotion", "neutral")
            scene.setdefault("music_mood", "soft")

            if not scene.get("script", "").strip():
                raise ProviderError(f"Scene {i} came back with no dialogue.")
            if not scene.get("visual_prompt", "").strip():
                raise ProviderError(f"Scene {i} came back with no visual_prompt.")

        logger.info("script.generated", title=result.get("title"), scenes=len(scenes))

        return {
            "title": result.get("title", idea[:80]),
            "scenes": scenes,
            "language": language,
            "duration": duration_s,
        }

    async def shorten(self, text: str, target_s: float) -> str:
        """Tighten a line to roughly `target_s` of speech. Called by reconcile."""
        target_words = max(3, int(target_s * WORDS_PER_SECOND))
        rewritten = await self._llm.generate(
            SHORTEN_SYSTEM,
            f"Rewrite in at most {target_words} words:\n\n{text}",
            temperature=0.3,
        )
        return rewritten.strip().strip('"')
