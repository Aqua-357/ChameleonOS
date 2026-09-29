"""Tests for ChameleonOS Visual Archetype System and Deterministic Magic Morph."""

import pytest
from fastapi.testclient import TestClient

from src.main import app
from src.database import get_db, SessionLocal
from src.themes.archetypes import (
    ARCHETYPES,
    get_archetype,
    get_archetype_tokens,
    normalize_archetype,
)
from src.themes.morph import magic_morph
from src.events.models import Event
from src.events.schemas import EventCreateRequest
from src.events.service import create_event


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ==============================================================================
# 1. Archetype Specification & Dimension Verification Tests
# ==============================================================================

def test_all_six_archetypes_defined():
    """Verify all six required archetypes are defined and have descriptions."""
    required = ["verdant", "cosmos", "arcade", "monolith", "bio", "atelier"]
    for arch in required:
        assert arch in ARCHETYPES, f"Archetype {arch} must be defined in ARCHETYPES."
        data = ARCHETYPES[arch]
        assert "name" in data
        assert "description" in data
        assert "tokens" in data


def test_archetypes_modify_all_seven_dimensions():
    """
    Verify each archetype modifies all seven required dimensions:
    1. colors
    2. typography treatment
    3. card treatment
    4. borders
    5. backgrounds
    6. motion intensity
    7. accent patterns
    """
    for arch_name, arch_data in ARCHETYPES.items():
        tokens = arch_data["tokens"]

        # Dimension 1: Colors
        color_keys = [
            "--bg-canvas", "--bg-surface", "--bg-surface-elevated", "--bg-surface-active",
            "--text-primary", "--text-secondary", "--text-muted",
            "--accent-primary", "--accent-primary-hover", "--accent-secondary"
        ]
        for k in color_keys:
            assert k in tokens, f"Archetype {arch_name} missing color token {k}"

        # Dimension 2: Typography treatment
        typography_keys = [
            "--font-heading", "--font-body", "--heading-letter-spacing", "--heading-transform"
        ]
        for k in typography_keys:
            assert k in tokens, f"Archetype {arch_name} missing typography token {k}"

        # Dimension 3: Card treatment
        card_keys = ["--card-radius", "--card-shadow", "--card-backdrop"]
        for k in card_keys:
            assert k in tokens, f"Archetype {arch_name} missing card token {k}"

        # Dimension 4: Borders
        border_keys = ["--border-subtle", "--border-muted", "--border-focus", "--border-width"]
        for k in border_keys:
            assert k in tokens, f"Archetype {arch_name} missing border token {k}"

        # Dimension 5: Backgrounds
        assert "--bg-gradient" in tokens, f"Archetype {arch_name} missing background token"

        # Dimension 6: Motion intensity
        motion_keys = ["--motion-duration", "--motion-easing"]
        for k in motion_keys:
            assert k in tokens, f"Archetype {arch_name} missing motion token {k}"

        # Dimension 7: Accent patterns
        accent_keys = [
            "--accent-badge-bg", "--accent-badge-border", "--accent-badge-color", "--accent-symbol"
        ]
        for k in accent_keys:
            assert k in tokens, f"Archetype {arch_name} missing accent token {k}"


def test_archetype_helpers():
    """Verify normalization and retrieval helper functions."""
    assert normalize_archetype("verdant") == "verdant"
    assert normalize_archetype("verdant-terra") == "verdant"
    assert normalize_archetype("COSMOS") == "cosmos"
    assert normalize_archetype("unknown-theme") == "verdant"
    assert normalize_archetype(None) == "verdant"

    tokens = get_archetype_tokens("arcade")
    assert tokens["--accent-symbol"] == "👾"
    assert tokens["--border-width"] == "2px"

    bio_arch = get_archetype("bio")
    assert bio_arch["name"] == "Bio"
    assert bio_arch["tokens"]["--accent-symbol"] == "🧬"


# ==============================================================================
# 2. Magic Morph Algorithm Determinism & Semantic Matching Tests
# ==============================================================================

def test_magic_morph_semantic_keywords():
    """Verify semantic keyword mapping for each archetype."""
    # Verdant keywords: climate, clean energy, forestry
    res = magic_morph(event_name="Climate Action 2026", event_purpose="Clean energy and forest sustainability")
    assert res["selected_archetype"] == "verdant"
    assert res["archetype"] == "verdant"

    # Cosmos keywords: orbit, interstellar, astronomy
    res = magic_morph(event_name="Orbital Satellites Hack", event_purpose="Deep space telescope telemetry")
    assert res["selected_archetype"] == "cosmos"

    # Arcade keywords: retro, game, 8bit
    res = magic_morph(event_name="8-Bit Retro Game Jam", event_purpose="Speedrun chiptune arcade platformers")
    assert res["selected_archetype"] == "arcade"

    # Monolith keywords: rust, database, infrastructure
    res = magic_morph(event_name="Distributed Rust Database Summit", event_purpose="Low-level storage kernel scale")
    assert res["selected_archetype"] == "monolith"

    # Bio keywords: genomic, dna, cell
    res = magic_morph(event_name="CRISPR Genomic Sequencing", event_purpose="Synthetic cellular biology and healthcare")
    assert res["selected_archetype"] == "bio"

    # Atelier keywords: typography, design, art
    res = magic_morph(event_name="Editorial Type & Craft Studio", event_purpose="Artisanal publication and creative writing")
    assert res["selected_archetype"] == "atelier"


def test_magic_morph_deterministic_offline_reproducibility():
    """Verify Magic Morph works 100% deterministically and repeatedly offline."""
    sample_inputs = [
        ("Quantum Computing Challenge", "Hardware qubits and quantum gate scale"),
        ("Global Food Security", "Agricultural robotics and crop yield analysis"),
        ("Random Noise 12345", "Arbitrary text with no keyword bag matches"),
        ("", ""),
        ("X", "Y"),
    ]

    for name, purpose in sample_inputs:
        res1 = magic_morph(name, purpose)
        res2 = magic_morph(name, purpose)
        res3 = magic_morph(name, purpose)

        assert res1["selected_archetype"] == res2["selected_archetype"] == res3["selected_archetype"]
        assert res1["tokens"] == res2["tokens"] == res3["tokens"]
        assert res1["selected_archetype"] in ARCHETYPES
        assert "theme_token_configuration" in res1


# ==============================================================================
# 3. HTTP API Endpoints for Themes & Magic Morph
# ==============================================================================

def test_api_themes_magic_morph_endpoint(client):
    """Test POST /api/v1/themes/magic-morph endpoint."""
    payload = {
        "event_name": "Nebula Starship Navigation",
        "event_purpose": "Celestial astrophysics deepspace orbit"
    }
    resp = client.post("/api/v1/themes/magic-morph", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["archetype"] == "cosmos"
    assert data["selected_archetype"] == "cosmos"
    assert data["tokens"]["--accent-symbol"] == "✨"
    assert "--bg-canvas" in data["tokens"]
    assert "--card-shadow" in data["tokens"]


def test_api_themes_archetypes_list(client):
    """Test GET /api/v1/themes/archetypes endpoint."""
    resp = client.get("/api/v1/themes/archetypes")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 6
    for key in ["verdant", "cosmos", "arcade", "monolith", "bio", "atelier"]:
        assert key in data
        assert "--font-heading" in data[key]["tokens"]


# ==============================================================================
# 4. Automatic Event Creation Integration with Magic Morph
# ==============================================================================

def test_event_creation_auto_populates_theme_config(db_session):
    """Test that creating an event automatically assigns theme_config via Magic Morph."""
    import uuid
    organizer = db_session.query(Event).first()
    creator_id = organizer.created_by_id if organizer else "usr_organizer"

    unique_slug = f"arcade-jam-{uuid.uuid4().hex[:8]}"
    req = EventCreateRequest(
        title="Arcade Retro Speedrun Jam",
        slug=unique_slug,
        description="Build 8bit arcade multiplayer platformers with retro synth",
        phase="active",
    )
    event = create_event(db_session, req, creator_id=creator_id)
    assert event.theme_config is not None
    assert event.theme_config.get("archetype") == "arcade"
    assert "--motion-duration" in event.theme_config.get("tokens", {})
    assert event.theme_config["tokens"]["--accent-symbol"] == "👾"


# ==============================================================================
# 5. Shared Component System & Consistent Theme Application Across Pages
# ==============================================================================

def test_landing_page_renders_with_theme(client):
    """Verify public landing page renders data-theme and archetype controls."""
    resp = client.get("/")
    assert resp.status_code == 200
    text = resp.text
    assert 'data-theme="' in text
    assert "theme-switcher-select" in text
    assert 'switchTheme("arcade")' in text or "switchTheme('arcade')" in text


def test_theme_query_param_override_across_routes(client):
    """
    Verify single shared component system switches themes via query parameter:
    - public landing page (/)
    - gallery (/gallery)
    - organizer dashboard (/events/{slug})
    """
    # Landing page with arcade
    r_landing = client.get("/?theme=arcade")
    assert r_landing.status_code == 200
    assert 'data-theme="arcade"' in r_landing.text

    # Gallery with monolith
    r_gallery = client.get("/gallery?theme=monolith")
    assert r_gallery.status_code == 200
    assert 'data-theme="monolith"' in r_gallery.text

    # Events detail with cosmos
    r_event = client.get("/events/dogfood-2026?theme=cosmos")
    assert r_event.status_code == 200
    assert 'data-theme="cosmos"' in r_event.text

    # Bio theme
    r_bio = client.get("/gallery?theme=bio")
    assert r_bio.status_code == 200
    assert 'data-theme="bio"' in r_bio.text

    # Atelier theme
    r_atelier = client.get("/?theme=atelier")
    assert r_atelier.status_code == 200
    assert 'data-theme="atelier"' in r_atelier.text
