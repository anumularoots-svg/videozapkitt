"""
Video DSL Templates

Predefined story structures. The LLM fills the content;
the template controls pacing and structure.
"""

TEMPLATES = {
    "story": {
        "name": "Storytelling",
        "structure": [
            {"act": "hook", "label": "Hook / Attention Grabber", "pct": 0.08},
            {"act": "setup", "label": "Character Introduction", "pct": 0.12},
            {"act": "problem", "label": "Problem / Conflict", "pct": 0.20},
            {"act": "journey", "label": "Journey / Struggle", "pct": 0.25},
            {"act": "climax", "label": "Climax / Turning Point", "pct": 0.20},
            {"act": "resolution", "label": "Resolution / Success", "pct": 0.15},
        ],
        "music_arc": ["suspense", "soft", "tense", "building", "epic", "uplifting"],
        "camera_arc": ["close_up", "medium", "wide", "tracking", "close_up", "wide"],
    },

    "educational": {
        "name": "Educational Explainer",
        "structure": [
            {"act": "hook", "label": "Hook Question", "pct": 0.10},
            {"act": "problem", "label": "Problem Statement", "pct": 0.15},
            {"act": "explain_1", "label": "Core Explanation", "pct": 0.25},
            {"act": "example", "label": "Example / Analogy", "pct": 0.20},
            {"act": "explain_2", "label": "Key Benefits", "pct": 0.15},
            {"act": "cta", "label": "Summary & CTA", "pct": 0.15},
        ],
        "music_arc": ["corporate_soft", "thinking", "upbeat", "upbeat", "corporate", "uplifting"],
        "camera_arc": ["close_up", "medium", "wide", "medium", "close_up", "medium"],
    },

    "motivational": {
        "name": "Motivational Story",
        "structure": [
            {"act": "hook", "label": "Emotional Hook", "pct": 0.10},
            {"act": "struggle", "label": "The Struggle", "pct": 0.20},
            {"act": "turning", "label": "Turning Point", "pct": 0.15},
            {"act": "growth", "label": "Growth / Learning", "pct": 0.20},
            {"act": "triumph", "label": "Triumph", "pct": 0.20},
            {"act": "message", "label": "Closing Message", "pct": 0.15},
        ],
        "music_arc": ["emotional", "sad", "hopeful", "building", "epic", "uplifting"],
        "camera_arc": ["close_up", "wide", "medium", "tracking", "close_up", "wide"],
    },

    "corporate": {
        "name": "Corporate Explainer",
        "structure": [
            {"act": "hook", "label": "Problem Hook", "pct": 0.12},
            {"act": "problem", "label": "Industry Pain Point", "pct": 0.18},
            {"act": "solution", "label": "Product / Solution", "pct": 0.25},
            {"act": "features", "label": "Key Features", "pct": 0.20},
            {"act": "proof", "label": "Social Proof / Stats", "pct": 0.10},
            {"act": "cta", "label": "Call to Action", "pct": 0.15},
        ],
        "music_arc": ["corporate", "corporate", "upbeat", "upbeat", "corporate", "uplifting"],
        "camera_arc": ["medium", "wide", "close_up", "medium", "medium", "close_up"],
    },
}


def get_template(video_type: str) -> dict:
    """Return the template for a video type, defaulting to 'story'."""
    return TEMPLATES.get(video_type, TEMPLATES["story"])


def compute_scene_durations(video_type: str, total_duration: int) -> list[dict]:
    """Given a type and total seconds, return scenes with concrete durations."""
    template = get_template(video_type)
    scenes = []
    for i, act in enumerate(template["structure"]):
        dur = round(total_duration * act["pct"], 1)
        # Enforce minimum 3s per scene
        dur = max(dur, 3.0)
        scenes.append({
            "scene_number": i + 1,
            "act": act["act"],
            "label": act["label"],
            "duration": dur,
            "music_mood": template["music_arc"][i],
            "camera": template["camera_arc"][i],
        })

    # Adjust to exactly match total duration
    current = sum(s["duration"] for s in scenes)
    diff = total_duration - current
    if diff != 0:
        # Distribute remainder across the longest scene
        longest = max(scenes, key=lambda s: s["duration"])
        longest["duration"] = round(longest["duration"] + diff, 1)

    return scenes
