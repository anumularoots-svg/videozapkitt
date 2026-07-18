"""
Stage 5: Blueprint Validator

Validates the complete blueprint before GPU resources are allocated.
No agent runs until validation passes.
"""

from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class ValidationResult:
    is_valid: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def fail(self, message: str):
        self.is_valid = False
        self.errors.append(message)

    def warn(self, message: str):
        self.warnings.append(message)


VALID_CAMERAS = {
    "close_up", "medium", "wide", "tracking", "pan",
    "aerial", "low_angle", "high_angle", "over_shoulder",
}

VALID_EMOTIONS = {
    "neutral", "happy", "sad", "angry", "motivated", "funny",
    "serious", "excited", "thoughtful", "determined", "surprised",
}

VALID_STYLES = {"cinematic", "corporate", "motion_graphics", "whiteboard", "storytelling"}

VALID_RATIOS = {"9:16", "16:9", "1:1", "4:5"}


def validate_blueprint(blueprint: dict) -> ValidationResult:
    """Run all validations on a blueprint JSON."""
    result = ValidationResult()

    # ── Required fields ────────────────────────────────
    for field_name in ["video_type", "duration", "language", "scenes"]:
        if field_name not in blueprint:
            result.fail(f"Missing required field: {field_name}")

    if not result.is_valid:
        return result

    # ── Duration ───────────────────────────────────────
    duration = blueprint["duration"]
    if not (15 <= duration <= 60):
        result.fail(f"Duration {duration}s is outside 15-60s range")

    # ── Scenes ─────────────────────────────────────────
    scenes = blueprint.get("scenes", [])
    if len(scenes) < 2:
        result.fail("Video must have at least 2 scenes")
    if len(scenes) > 12:
        result.fail("Video must have at most 12 scenes")

    # ── Scene durations must sum to total ──────────────
    total_scene_duration = sum(s.get("duration", 0) for s in scenes)
    tolerance = 1.5  # seconds
    if abs(total_scene_duration - duration) > tolerance:
        result.fail(
            f"Scene durations sum to {total_scene_duration}s "
            f"but video duration is {duration}s (tolerance: {tolerance}s)"
        )

    # ── Per-scene validation ───────────────────────────
    for i, scene in enumerate(scenes):
        scene_num = scene.get("id", i + 1)

        # Duration
        sdur = scene.get("duration", 0)
        if sdur < 2:
            result.fail(f"Scene {scene_num}: duration {sdur}s is below 2s minimum")
        if sdur > 30:
            result.warn(f"Scene {scene_num}: duration {sdur}s is very long")

        # Camera
        cam = scene.get("camera", "")
        if cam and cam not in VALID_CAMERAS:
            result.warn(f"Scene {scene_num}: unknown camera angle '{cam}'")

        # Emotion
        emo = scene.get("emotion", "")
        if emo and emo not in VALID_EMOTIONS:
            result.warn(f"Scene {scene_num}: unknown emotion '{emo}'")

    # ── Style ──────────────────────────────────────────
    style = blueprint.get("style", "cinematic")
    if style not in VALID_STYLES:
        result.warn(f"Style '{style}' is non-standard, defaulting to cinematic")

    # ── Aspect ratio ───────────────────────────────────
    ratio = blueprint.get("aspect_ratio", "9:16")
    if ratio not in VALID_RATIOS:
        result.fail(f"Unsupported aspect ratio: {ratio}")

    # ── Character consistency ──────────────────────────
    characters_used = set()
    for scene in scenes:
        char = scene.get("character", "")
        if char:
            characters_used.add(char)
    if len(characters_used) > 4:
        result.warn("More than 4 characters may reduce visual consistency")

    return result
