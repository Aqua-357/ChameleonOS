"""ChameleonOS Visual Archetypes & Design Token System.

Defines the six visual archetypes:
- verdant: Ecological, organic, vitality, deep forest, regenerative.
- cosmos: Celestial, astrophysics, stellar exploration, deep space.
- arcade: Retro gaming, 80s synthwave, punchy neon, energetic pixel feel.
- monolith: Architectural brutalism, stark obsidian, raw titanium, strict precision.
- bio: Synthetic biology, genomic sequencing, bioluminescent laboratory.
- atelier: Artisanal craftsmanship, editorial luxury, gilded terracotta & warm paper.

Each archetype strictly customizes:
1. colors
2. typography treatment
3. card treatment
4. borders
5. backgrounds
6. motion intensity
7. accent patterns
"""

from typing import Any, Dict, Optional


ARCHETYPES: Dict[str, Dict[str, Any]] = {
    # --------------------------------------------------------------------------
    # 1. VERDANT - Organic Ecological Vitality
    # --------------------------------------------------------------------------
    "verdant": {
        "name": "Verdant",
        "description": "Organic ecological aesthetic featuring deep forest greens, emerald bioluminescence, and calm botanical eases.",
        "tokens": {
            # Colors
            "--bg-canvas": "#07130c",
            "--bg-surface": "#0f2117",
            "--bg-surface-elevated": "#173022",
            "--bg-surface-active": "#1f3e2d",
            "--text-primary": "#f2fbf5",
            "--text-secondary": "#8ebba0",
            "--text-muted": "#5a886d",
            "--accent-primary": "#10b981",
            "--accent-primary-hover": "#059669",
            "--accent-secondary": "#34d399",
            # Typography treatment
            "--font-heading": "system-ui, -apple-system, sans-serif",
            "--font-body": "system-ui, -apple-system, sans-serif",
            "--heading-letter-spacing": "-0.01em",
            "--heading-transform": "none",
            # Card treatment
            "--card-radius": "16px",
            "--card-shadow": "0 8px 30px rgba(7, 19, 12, 0.4)",
            "--card-backdrop": "none",
            # Borders
            "--border-subtle": "rgba(16, 185, 129, 0.15)",
            "--border-muted": "rgba(16, 185, 129, 0.3)",
            "--border-focus": "#10b981",
            "--border-width": "1px",
            # Backgrounds
            "--bg-gradient": "radial-gradient(ellipse at 50% 0%, #132a1e 0%, #07130c 75%)",
            # Motion intensity
            "--motion-duration": "0.35s",
            "--motion-easing": "cubic-bezier(0.4, 0, 0.2, 1)",
            # Accent patterns
            "--accent-badge-bg": "rgba(16, 185, 129, 0.12)",
            "--accent-badge-border": "rgba(16, 185, 129, 0.3)",
            "--accent-badge-color": "#34d399",
            "--accent-symbol": "🌿",
        },
    },

    # --------------------------------------------------------------------------
    # 2. COSMOS - Celestial Space Exploration
    # --------------------------------------------------------------------------
    "cosmos": {
        "name": "Cosmos",
        "description": "Deep interstellar space with nebula ultraviolet hues, starlight cyan accents, and frosted glass cards.",
        "tokens": {
            # Colors
            "--bg-canvas": "#040714",
            "--bg-surface": "#0a1026",
            "--bg-surface-elevated": "#121a3a",
            "--bg-surface-active": "#1c2652",
            "--text-primary": "#f8fafc",
            "--text-secondary": "#94a3b8",
            "--text-muted": "#64748b",
            "--accent-primary": "#6366f1",
            "--accent-primary-hover": "#4f46e5",
            "--accent-secondary": "#38bdf8",
            # Typography treatment
            "--font-heading": "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
            "--font-body": "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
            "--heading-letter-spacing": "0.04em",
            "--heading-transform": "uppercase",
            # Card treatment
            "--card-radius": "14px",
            "--card-shadow": "0 10px 40px rgba(99, 102, 241, 0.12)",
            "--card-backdrop": "blur(16px)",
            # Borders
            "--border-subtle": "rgba(99, 102, 241, 0.2)",
            "--border-muted": "rgba(56, 189, 248, 0.3)",
            "--border-focus": "#38bdf8",
            "--border-width": "1px",
            # Backgrounds
            "--bg-gradient": "radial-gradient(circle at 50% 10%, #151838 0%, #040714 80%)",
            # Motion intensity
            "--motion-duration": "0.45s",
            "--motion-easing": "cubic-bezier(0.16, 1, 0.3, 1)",
            # Accent patterns
            "--accent-badge-bg": "rgba(99, 102, 241, 0.15)",
            "--accent-badge-border": "rgba(99, 102, 241, 0.35)",
            "--accent-badge-color": "#818cf8",
            "--accent-symbol": "✨",
        },
    },

    # --------------------------------------------------------------------------
    # 3. ARCADE - Retro Gaming & Chiptune Synthwave
    # --------------------------------------------------------------------------
    "arcade": {
        "name": "Arcade",
        "description": "High-octane retro gaming with punchy neon magenta and cyan, pixelated hard drop-shadows, and snappy instant transitions.",
        "tokens": {
            # Colors
            "--bg-canvas": "#0f0b1a",
            "--bg-surface": "#1b142e",
            "--bg-surface-elevated": "#271c42",
            "--bg-surface-active": "#352659",
            "--text-primary": "#fdf4ff",
            "--text-secondary": "#d8b4fe",
            "--text-muted": "#9333ea",
            "--accent-primary": "#ec4899",
            "--accent-primary-hover": "#db2777",
            "--accent-secondary": "#06b6d4",
            # Typography treatment
            "--font-heading": "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
            "--font-body": "system-ui, -apple-system, sans-serif",
            "--heading-letter-spacing": "0.02em",
            "--heading-transform": "uppercase",
            # Card treatment
            "--card-radius": "4px",
            "--card-shadow": "4px 4px 0px rgba(236, 72, 153, 0.35)",
            "--card-backdrop": "none",
            # Borders
            "--border-subtle": "rgba(236, 72, 153, 0.35)",
            "--border-muted": "rgba(6, 182, 212, 0.5)",
            "--border-focus": "#ec4899",
            "--border-width": "2px",
            # Backgrounds
            "--bg-gradient": "linear-gradient(180deg, #1b122e 0%, #0f0b1a 100%)",
            # Motion intensity
            "--motion-duration": "0.09s",
            "--motion-easing": "cubic-bezier(0, 0, 0.2, 1)",
            # Accent patterns
            "--accent-badge-bg": "rgba(236, 72, 153, 0.18)",
            "--accent-badge-border": "rgba(236, 72, 153, 0.45)",
            "--accent-badge-color": "#f472b6",
            "--accent-symbol": "👾",
        },
    },

    # --------------------------------------------------------------------------
    # 4. MONOLITH - Architectural Brutalism & Obsidian Precision
    # --------------------------------------------------------------------------
    "monolith": {
        "name": "Monolith",
        "description": "Stark brutalist minimalism with razor-sharp square edges, chalk-white high contrast typography, and unyielding mechanical transitions.",
        "tokens": {
            # Colors
            "--bg-canvas": "#09090b",
            "--bg-surface": "#141417",
            "--bg-surface-elevated": "#1e1e24",
            "--bg-surface-active": "#2b2b34",
            "--text-primary": "#fafafa",
            "--text-secondary": "#a1a1aa",
            "--text-muted": "#71717a",
            "--accent-primary": "#f4f4f5",
            "--accent-primary-hover": "#e4e4e7",
            "--accent-secondary": "#a1a1aa",
            # Typography treatment
            "--font-heading": "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif",
            "--font-body": "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif",
            "--heading-letter-spacing": "-0.04em",
            "--heading-transform": "none",
            # Card treatment
            "--card-radius": "0px",
            "--card-shadow": "5px 5px 0px #000000",
            "--card-backdrop": "none",
            # Borders
            "--border-subtle": "#27272a",
            "--border-muted": "#3f3f46",
            "--border-focus": "#fafafa",
            "--border-width": "2px",
            # Backgrounds
            "--bg-gradient": "linear-gradient(180deg, #121215 0%, #09090b 100%)",
            # Motion intensity
            "--motion-duration": "0.12s",
            "--motion-easing": "linear",
            # Accent patterns
            "--accent-badge-bg": "#27272a",
            "--accent-badge-border": "#52525b",
            "--accent-badge-color": "#f4f4f5",
            "--accent-symbol": "⬛",
        },
    },

    # --------------------------------------------------------------------------
    # 5. BIO - Synthetic Biology & Bioluminescent Laboratory
    # --------------------------------------------------------------------------
    "bio": {
        "name": "Bio",
        "description": "Biomedical genomic precision with crisp electric lime, deep cyan petri-dish surfaces, and cellular pill silhouettes.",
        "tokens": {
            # Colors
            "--bg-canvas": "#051317",
            "--bg-surface": "#0c2026",
            "--bg-surface-elevated": "#122c34",
            "--bg-surface-active": "#193c47",
            "--text-primary": "#f0fdf4",
            "--text-secondary": "#7dd3fc",
            "--text-muted": "#38bdf8",
            "--accent-primary": "#84cc16",
            "--accent-primary-hover": "#65a30d",
            "--accent-secondary": "#06b6d4",
            # Typography treatment
            "--font-heading": "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
            "--font-body": "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
            "--heading-letter-spacing": "0.01em",
            "--heading-transform": "none",
            # Card treatment
            "--card-radius": "20px",
            "--card-shadow": "0 6px 25px rgba(132, 204, 22, 0.1)",
            "--card-backdrop": "none",
            # Borders
            "--border-subtle": "rgba(132, 204, 22, 0.2)",
            "--border-muted": "rgba(6, 182, 212, 0.35)",
            "--border-focus": "#84cc16",
            "--border-width": "1px",
            # Backgrounds
            "--bg-gradient": "radial-gradient(ellipse at 30% 0%, #0d2830 0%, #051317 75%)",
            # Motion intensity
            "--motion-duration": "0.3s",
            "--motion-easing": "cubic-bezier(0.25, 0.8, 0.25, 1)",
            # Accent patterns
            "--accent-badge-bg": "rgba(132, 204, 22, 0.15)",
            "--accent-badge-border": "rgba(132, 204, 22, 0.35)",
            "--accent-badge-color": "#a3e635",
            "--accent-symbol": "🧬",
        },
    },

    # --------------------------------------------------------------------------
    # 6. ATELIER - Artisanal Editorial & Roasted Umber
    # --------------------------------------------------------------------------
    "atelier": {
        "name": "Atelier",
        "description": "Refined editorial craftsmanship with roasted umber paper tones, gilded ochre accents, and classical serif headers.",
        "tokens": {
            # Colors
            "--bg-canvas": "#120e0b",
            "--bg-surface": "#1c1713",
            "--bg-surface-elevated": "#29211c",
            "--bg-surface-active": "#382d26",
            "--text-primary": "#fef3c7",
            "--text-secondary": "#d6c7b2",
            "--text-muted": "#9c8b77",
            "--accent-primary": "#d97706",
            "--accent-primary-hover": "#b45309",
            "--accent-secondary": "#f59e0b",
            # Typography treatment
            "--font-heading": "Charter, 'Iowan Old Style', 'Times New Roman', Georgia, serif",
            "--font-body": "-apple-system, BlinkMacSystemFont, 'Segoe UI', Georgia, serif",
            "--heading-letter-spacing": "-0.015em",
            "--heading-transform": "none",
            # Card treatment
            "--card-radius": "8px",
            "--card-shadow": "0 6px 20px rgba(18, 14, 11, 0.6)",
            "--card-backdrop": "none",
            # Borders
            "--border-subtle": "rgba(217, 119, 6, 0.25)",
            "--border-muted": "rgba(245, 158, 11, 0.35)",
            "--border-focus": "#f59e0b",
            "--border-width": "1px",
            # Backgrounds
            "--bg-gradient": "radial-gradient(ellipse at 50% 10%, #28201a 0%, #120e0b 80%)",
            # Motion intensity
            "--motion-duration": "0.4s",
            "--motion-easing": "cubic-bezier(0.16, 1, 0.3, 1)",
            # Accent patterns
            "--accent-badge-bg": "rgba(217, 119, 6, 0.15)",
            "--accent-badge-border": "rgba(217, 119, 6, 0.35)",
            "--accent-badge-color": "#fbbf24",
            "--accent-symbol": "⚜️",
        },
    },
}


def normalize_archetype(name: Optional[str]) -> str:
    """Normalize any archetype name or variant into one of the canonical six."""
    if not name:
        return "verdant"
    cleaned = name.strip().lower()
    if cleaned in ARCHETYPES:
        return cleaned
    for k in ARCHETYPES:
        if k in cleaned:
            return k
    return "verdant"


def get_archetype(name: Optional[str]) -> Dict[str, Any]:
    """Retrieve archetype definition by name with fallback."""
    canonical = normalize_archetype(name)
    return ARCHETYPES[canonical]


def get_archetype_tokens(name: Optional[str]) -> Dict[str, Any]:
    """Retrieve design tokens for archetype."""
    return get_archetype(name)["tokens"]
