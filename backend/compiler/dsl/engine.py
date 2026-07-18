"""
Video DSL Engine

Converts a user idea into a structured Video DSL, then into Blueprint JSON.
The DSL is an intermediate representation — like assembly for video.
"""

from __future__ import annotations
import json
from dataclasses import dataclass, field, asdict
from .templates import get_template, compute_scene_durations


@dataclass
class DSLScene:
    id: int
    act: str
    label: str
    duration: float
    character: str = ""
    camera: str = "medium"
    emotion: str = "neutral"
    environment: str = ""
    voice: str = ""
    music: str = ""
    lighting: str = "natural"
    transition: str = "fade"
    script: str = ""
    subtitle: str = ""
    prompt: str = ""


@dataclass
class VideoDSL:
    """The intermediate representation of a video — the DSL document."""
    video_type: str
    duration: int
    language: str
    style: str = "cinematic"
    aspect_ratio: str = "9:16"
    resolution: str = "1080x1920"
    fps: int = 24
    title: str = ""
    full_script: str = ""
    scenes: list[DSLScene] = field(default_factory=list)
    characters_used: list[str] = field(default_factory=list)

    def to_dsl_text(self) -> str:
        """Render the DSL as a human-readable text format."""
        lines = [
            f"VIDEO {{",
            f"  type: {self.video_type}",
            f"  duration: {self.duration}s",
            f"  language: {self.language}",
            f"  style: {self.style}",
            f"  aspect_ratio: {self.aspect_ratio}",
            f"  resolution: {self.resolution}",
            f"  fps: {self.fps}",
            f"  title: {self.title}",
            "",
        ]
        for scene in self.scenes:
            lines.append(f"  SCENE {scene.id} {{")
            lines.append(f"    act: {scene.act}")
            lines.append(f"    duration: {scene.duration}s")
            lines.append(f"    character: {scene.character}")
            lines.append(f"    camera: {scene.camera}")
            lines.append(f"    emotion: {scene.emotion}")
            lines.append(f"    environment: {scene.environment}")
            lines.append(f"    voice: {scene.voice}")
            lines.append(f"    music: {scene.music}")
            lines.append(f"    lighting: {scene.lighting}")
            lines.append(f"    transition: {scene.transition}")
            if scene.script:
                lines.append(f'    script: "{scene.script}"')
            lines.append(f"  }}")
            lines.append("")
        lines.append("}")
        return "\n".join(lines)

    def to_blueprint_json(self, project_id: str, version: int = 1) -> dict:
        """Convert DSL to Blueprint JSON (the source of truth)."""
        return {
            "project_id": project_id,
            "version": version,
            "video_type": self.video_type,
            "duration": self.duration,
            "language": self.language,
            "style": self.style,
            "aspect_ratio": self.aspect_ratio,
            "resolution": self.resolution,
            "fps": self.fps,
            "title": self.title,
            "script": self.full_script,
            "characters_used": self.characters_used,
            "status": "draft",
            "render_status": "pending",
            "scenes": [asdict(s) for s in self.scenes],
        }


def create_skeleton_dsl(
    video_type: str,
    duration: int,
    language: str,
    style: str = "cinematic",
) -> VideoDSL:
    """
    Create a skeleton DSL from the template.
    The Script Agent will fill in script/subtitle/prompt later.
    The Character Agent will assign characters.
    """
    scene_plan = compute_scene_durations(video_type, duration)
    scenes = []
    for sp in scene_plan:
        scenes.append(DSLScene(
            id=sp["scene_number"],
            act=sp["act"],
            label=sp["label"],
            duration=sp["duration"],
            camera=sp["camera"],
            music=sp["music_mood"],
        ))

    return VideoDSL(
        video_type=video_type,
        duration=duration,
        language=language,
        style=style,
        scenes=scenes,
    )
