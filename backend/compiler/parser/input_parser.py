"""
Stage 1: Input Parser

Takes the raw user input and extracts structured metadata.
Classifies the video type, normalizes language, validates duration.
"""

from __future__ import annotations
import re
from dataclasses import dataclass

# Keyword-based classification for V1 (no LLM call needed)
TYPE_KEYWORDS = {
    "educational": [
        "explain", "tutorial", "learn", "teach", "how to", "guide",
        "what is", "introduction to", "basics", "beginner", "course",
    ],
    "motivational": [
        "motivat", "inspir", "success", "dream", "never give up",
        "struggle", "overcome", "believe", "grind", "hustle", "journey",
    ],
    "corporate": [
        "product", "company", "startup", "business", "enterprise",
        "saas", "b2b", "service", "solution", "platform", "tool",
    ],
    "story": [
        "story", "tale", "once upon", "boy", "girl", "person",
        "village", "city", "adventure", "life",
    ],
}

SUPPORTED_LANGUAGES = {
    "english": "en", "telugu": "te", "hindi": "hi", "tamil": "ta",
    "kannada": "kn", "malayalam": "ml", "bengali": "bn", "marathi": "mr",
    "gujarati": "gu", "punjabi": "pa", "urdu": "ur",
    "japanese": "ja", "korean": "ko", "chinese": "zh",
    "spanish": "es", "french": "fr", "german": "de", "italian": "it",
    "portuguese": "pt", "russian": "ru", "arabic": "ar",
    "thai": "th", "vietnamese": "vi", "indonesian": "id",
    "turkish": "tr", "dutch": "nl", "polish": "pl", "swedish": "sv",
}


@dataclass
class ParsedInput:
    idea: str
    language: str
    language_code: str
    duration: int
    video_type: str
    confidence: float


def classify_video_type(idea: str) -> tuple[str, float]:
    """Classify video type from keywords. Returns (type, confidence)."""
    idea_lower = idea.lower()
    scores = {}
    for vtype, keywords in TYPE_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in idea_lower)
        if score > 0:
            scores[vtype] = score

    if not scores:
        return "story", 0.5  # default

    best = max(scores, key=scores.get)
    confidence = min(scores[best] / 3.0, 1.0)
    return best, confidence


def normalize_language(language: str) -> tuple[str, str]:
    """Return (display_name, iso_code)."""
    lang_lower = language.lower().strip()
    if lang_lower in SUPPORTED_LANGUAGES:
        return language.title(), SUPPORTED_LANGUAGES[lang_lower]
    # Fuzzy match
    for name, code in SUPPORTED_LANGUAGES.items():
        if name.startswith(lang_lower[:3]):
            return name.title(), code
    return "English", "en"


def parse_input(idea: str, language: str, duration: int) -> ParsedInput:
    """Stage 1: Parse and validate raw user input."""
    # Normalize
    idea = idea.strip()
    duration = max(15, min(duration, 60))
    lang_display, lang_code = normalize_language(language)
    video_type, confidence = classify_video_type(idea)

    return ParsedInput(
        idea=idea,
        language=lang_display,
        language_code=lang_code,
        duration=duration,
        video_type=video_type,
        confidence=confidence,
    )
