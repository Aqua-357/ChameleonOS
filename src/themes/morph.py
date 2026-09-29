"""Deterministic offline Magic Morph algorithm for ChameleonOS.

Transforms an event's name and purpose into one of the six visual archetypes
with complete design token configuration.

Zero external AI API dependencies. 100% offline, deterministic, and reproducible.
"""

import hashlib
import re
from typing import Any, Dict, List, Tuple
from src.themes.archetypes import ARCHETYPES


LEXICONS: Dict[str, List[str]] = {
    "verdant": [
        "climate", "eco", "green", "nature", "forest", "plant", "agriculture",
        "ocean", "water", "carbon", "energy", "clean", "sustainable", "sustainability",
        "planet", "solar", "tree", "flora", "fauna", "earth", "ecology", "organic",
        "conservation", "renew", "renewable", "wildlife", "agritech", "waste", "recycle",
    ],
    "cosmos": [
        "space", "galaxy", "star", "stars", "celestial", "astro", "rocket", "satellite",
        "cosmic", "telescope", "universe", "orbit", "mars", "lunar", "moon", "astronaut",
        "interstellar", "astrophysics", "gravity", "quantum", "planetary", "spacecraft",
        "orbit", "exoplanet", "constellation", "nebula", "deepspace",
    ],
    "arcade": [
        "game", "games", "gaming", "retro", "pixel", "arcade", "vr", "play", "unity",
        "unreal", "esport", "esports", "8bit", "16bit", "console", "joystick", "level",
        "speedrun", "quest", "render", "multiplayer", "synth", "score", "animation",
        "3d", "player", "gamify", "rpg", "fps", "platformer", "indie",
    ],
    "monolith": [
        "infra", "infrastructure", "system", "systems", "database", "kernel", "security",
        "rust", "compiler", "blockchain", "ledger", "crypto", "hardware", "low-level",
        "benchmark", "storage", "scale", "architecture", "cloud", "enterprise", "devops",
        "backend", "monolith", "unix", "linux", "distributed", "networking", "protocol",
    ],
    "bio": [
        "health", "bio", "biotech", "medicine", "genomic", "dna", "cell", "cellular",
        "medical", "pharma", "neuroscience", "diagnosis", "biology", "patient", "healthcare",
        "synthetic", "clinical", "crispr", "organ", "life", "vaccine", "disease", "drug",
        "pathology", "biomedical", "molecular", "gene", "protein",
    ],
    "atelier": [
        "design", "art", "creative", "craft", "music", "fashion", "culture", "studio",
        "media", "narrative", "content", "film", "sound", "typography", "poetry",
        "aesthetic", "luxury", "publication", "human", "story", "canvas", "writer",
        "artisan", "visual", "photography", "editorial", "curation", "sculpt",
    ],
}

ARCHETYPE_ORDER = ["verdant", "cosmos", "arcade", "monolith", "bio", "atelier"]


def tokenize(text: str) -> List[str]:
    """Extract lowercase alpha-numeric tokens from text."""
    if not text:
        return []
    return re.findall(r"\b[a-z0-9]+\b", text.lower())


def magic_morph(event_name: str, event_purpose: str = "") -> Dict[str, Any]:
    """
    Execute Magic Morph on event name and purpose.

    Algorithm:
    1. Tokenize name and purpose.
    2. Score archetype semantic bags (name tokens count for 3x, purpose counts for 1x).
    3. If any archetype achieves a positive score, select the top-scoring archetype.
    4. Deterministic Tie-Breaker: If scores tie or are 0, use SHA-256 hash modulo 6.
    5. Return selected archetype and its full CSS design token configuration.
    """
    name_tokens = set(tokenize(event_name))
    purpose_tokens = set(tokenize(event_purpose))

    scores: Dict[str, float] = {k: 0.0 for k in ARCHETYPE_ORDER}

    for arch, keywords in LEXICONS.items():
        kw_set = set(keywords)
        # Name matches receive 3x weight
        name_hits = len(name_tokens & kw_set)
        purpose_hits = len(purpose_tokens & kw_set)
        scores[arch] = (name_hits * 3.0) + (purpose_hits * 1.0)

    max_score = max(scores.values())

    if max_score > 0:
        # Filter all archetypes matching max_score
        top_candidates = [arch for arch in ARCHETYPE_ORDER if scores[arch] == max_score]
        if len(top_candidates) == 1:
            selected = top_candidates[0]
        else:
            # Deterministic hash tie-breaker among top candidates
            raw_key = f"{event_name.strip().lower()}::{event_purpose.strip().lower()}"
            hash_val = int(hashlib.sha256(raw_key.encode("utf-8")).hexdigest(), 16)
            selected = top_candidates[hash_val % len(top_candidates)]
    else:
        # Zero semantic match fallback: strictly deterministic hash modulo 6
        raw_key = f"{event_name.strip().lower()}::{event_purpose.strip().lower()}"
        hash_val = int(hashlib.sha256(raw_key.encode("utf-8")).hexdigest(), 16)
        selected = ARCHETYPE_ORDER[hash_val % 6]

    archetype_data = ARCHETYPES[selected]

    return {
        "archetype": selected,
        "selected_archetype": selected,
        "name": archetype_data["name"],
        "description": archetype_data["description"],
        "tokens": archetype_data["tokens"],
        "theme_token_configuration": archetype_data["tokens"],
        "scores": scores,
    }
