"""
Curated character library.

DATA ONLY -- this is design intent, not working capability. Preserved from the
pre-rewrite character agent because the descriptions are worth keeping.

What is NOT true yet:
  - `character_packs/` holds ONE metadata file and ZERO reference images.
    Without reference images there is no identity to condition on, so the
    "consistency engine" has nothing to work with. Phase 3 builds the packs.
  - `voice_id` maps to nothing today. Phase 0-1 voice is Kokoro English presets.
    Phase 3 binds each character to a recorded reference voice for IndicF5.

CONSENT: IndicF5 is a few-shot cloning model. Every reference voice needs
explicit, recorded permission from the speaker, and every uploaded face in
manual mode needs the same. This is a legal prerequisite for Phase 3, not
paperwork to sort out later. See ARCHITECTURE.md §2 and §12 decision 3.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Character:
    id: str
    name: str
    gender: str
    age: str
    style: str
    voice_id: str
    appearance: str
    clothing_default: str

    def prompt_fragment(self) -> str:
        """Identity text injected into a scene's image prompt.

        Text alone will NOT hold a face across 12 clips -- that needs image
        conditioning (IP-Adapter/InstantID, Phase 3). This is a floor, not a
        solution.
        """
        parts = [self.appearance]
        if self.clothing_default != "n/a":
            parts.append(f"wearing {self.clothing_default}")
        return ", ".join(parts)

    def pack_dir(self, root: Path) -> Path:
        return root / self.id

    def has_reference_images(self, root: Path) -> bool:
        pack = self.pack_dir(root) / "reference"
        return pack.is_dir() and any(pack.glob("*.png"))


_RAW: dict[str, dict[str, str]] = {
    "narrator_m_01": {
        "name": "Arjun", "gender": "male", "age": "30",
        "style": "cinematic", "voice_id": "narrator_m_01",
        "appearance": "Indian male, 30 years old, clean shaven, black hair, warm brown eyes",
        "clothing_default": "dark navy blazer, white shirt",
    },
    "narrator_f_01": {
        "name": "Priya", "gender": "female", "age": "28",
        "style": "cinematic", "voice_id": "narrator_f_01",
        "appearance": "Indian female, 28 years old, long black hair, brown eyes, confident expression",
        "clothing_default": "professional teal blouse",
    },
    "young_m_01": {
        "name": "Ravi", "gender": "male", "age": "22",
        "style": "cinematic", "voice_id": "young_m_01",
        "appearance": "Young Indian male, 22 years old, short dark hair, eager expression, slim build",
        "clothing_default": "blue t-shirt, jeans",
    },
    "young_m_02": {
        "name": "Alex", "gender": "male", "age": "24",
        "style": "cinematic", "voice_id": "young_m_02",
        "appearance": "Young Caucasian male, 24 years old, brown hair, blue eyes, athletic build",
        "clothing_default": "grey hoodie",
    },
    "young_m_03": {
        "name": "Kenji", "gender": "male", "age": "23",
        "style": "cinematic", "voice_id": "young_m_03",
        "appearance": "Young Japanese male, 23 years old, neat black hair, focused expression",
        "clothing_default": "white shirt, dark pants",
    },
    "young_f_01": {
        "name": "Maya", "gender": "female", "age": "22",
        "style": "cinematic", "voice_id": "young_f_01",
        "appearance": "Young Indian female, 22 years old, shoulder-length black hair, bright smile",
        "clothing_default": "yellow kurta",
    },
    "young_f_02": {
        "name": "Sarah", "gender": "female", "age": "25",
        "style": "cinematic", "voice_id": "young_f_02",
        "appearance": "Young Caucasian female, 25 years old, blonde hair, green eyes",
        "clothing_default": "casual blazer, white top",
    },
    "young_f_03": {
        "name": "Yuki", "gender": "female", "age": "23",
        "style": "cinematic", "voice_id": "young_f_03",
        "appearance": "Young Japanese female, 23 years old, long straight black hair, gentle expression",
        "clothing_default": "light blue blouse",
    },
    "business_m_01": {
        "name": "Vikram", "gender": "male", "age": "40",
        "style": "corporate", "voice_id": "business_m_01",
        "appearance": "Indian male, 40 years old, salt-and-pepper hair, authoritative presence, glasses",
        "clothing_default": "charcoal suit, red tie",
    },
    "business_f_01": {
        "name": "Ananya", "gender": "female", "age": "35",
        "style": "corporate", "voice_id": "business_f_01",
        "appearance": "Indian female, 35 years old, neat bun hairstyle, professional demeanor",
        "clothing_default": "black blazer, pearl earrings",
    },
    "senior_m_01": {
        "name": "Professor Das", "gender": "male", "age": "60",
        "style": "cinematic", "voice_id": "senior_m_01",
        "appearance": "Indian male, 60 years old, grey hair, wise expression, reading glasses",
        "clothing_default": "brown tweed jacket",
    },
    "senior_f_01": {
        "name": "Grandmother Lakshmi", "gender": "female", "age": "65",
        "style": "cinematic", "voice_id": "senior_f_01",
        "appearance": "Indian female, 65 years old, grey hair in braid, warm loving face, saree",
        "clothing_default": "green silk saree",
    },
    "corporate_m_01": {
        "name": "James", "gender": "male", "age": "35",
        "style": "corporate", "voice_id": "corporate_m_01",
        "appearance": "Caucasian male, 35 years old, neat brown hair, clean shaven, sharp jawline",
        "clothing_default": "navy suit, white shirt",
    },
    "corporate_f_01": {
        "name": "Elena", "gender": "female", "age": "32",
        "style": "corporate", "voice_id": "corporate_f_01",
        "appearance": "Caucasian female, 32 years old, auburn hair, confident smile",
        "clothing_default": "tailored grey suit",
    },
    "robot_01": {
        "name": "AIVA", "gender": "neutral", "age": "n/a",
        "style": "cinematic", "voice_id": "robot_01",
        "appearance": "Sleek humanoid robot, white and blue chassis, glowing blue eyes, friendly face",
        "clothing_default": "n/a",
    },
}

LIBRARY: dict[str, Character] = {
    cid: Character(id=cid, **fields) for cid, fields in _RAW.items()
}

DEFAULT_CHARACTER = "narrator_m_01"


def get(character_id: str) -> Character:
    if character_id not in LIBRARY:
        raise KeyError(
            f"Unknown character {character_id!r}. Known: {sorted(LIBRARY)}"
        )
    return LIBRARY[character_id]


def missing_packs(root: Path) -> list[str]:
    """Characters with no reference images on disk.

    Today this returns all 15. Phase 3's job is to make it return none.
    """
    return [c.id for c in LIBRARY.values() if not c.has_reference_images(root)]
