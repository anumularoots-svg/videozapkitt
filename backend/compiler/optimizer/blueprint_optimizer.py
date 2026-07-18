"""
Stage 4: Blueprint Optimizer

Adjusts the blueprint for better pacing, GPU efficiency, and quality.
Runs after validation passes.
"""

from __future__ import annotations
import copy


def optimize_blueprint(blueprint: dict) -> dict:
    """Optimize the validated blueprint for rendering efficiency."""
    bp = copy.deepcopy(blueprint)
    scenes = bp["scenes"]

    # ── Merge very short scenes ────────────────────────
    # If two consecutive scenes are both under 3s, merge them.
    optimized_scenes = []
    i = 0
    while i < len(scenes):
        scene = scenes[i]
        if (
            i + 1 < len(scenes)
            and scene["duration"] < 3
            and scenes[i + 1]["duration"] < 3
        ):
            merged = copy.deepcopy(scene)
            merged["duration"] = scene["duration"] + scenes[i + 1]["duration"]
            merged["label"] = f"{scene.get('label', '')} + {scenes[i+1].get('label', '')}"
            optimized_scenes.append(merged)
            i += 2
        else:
            optimized_scenes.append(scene)
            i += 1

    # Re-number scenes
    for idx, scene in enumerate(optimized_scenes):
        scene["id"] = idx + 1

    # ── Optimize transitions ───────────────────────────
    # First scene: no transition in. Last scene: fade out.
    for idx, scene in enumerate(optimized_scenes):
        if idx == 0:
            scene["transition"] = "none"
        elif idx == len(optimized_scenes) - 1:
            scene["transition"] = "fade_out"
        else:
            # Vary transitions to avoid monotony
            transitions = ["fade", "cut", "dissolve", "slide"]
            scene["transition"] = transitions[idx % len(transitions)]

    # ── Optimize for GPU batching ──────────────────────
    # Tag scenes that can be rendered in parallel
    # (scenes with different characters can be parallelized)
    character_groups = {}
    for scene in optimized_scenes:
        char = scene.get("character", "default")
        character_groups.setdefault(char, []).append(scene["id"])

    bp["scenes"] = optimized_scenes
    bp["render_groups"] = character_groups
    bp["scene_count"] = len(optimized_scenes)

    return bp
