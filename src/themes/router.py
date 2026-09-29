"""Themes & Magic Morph API endpoints."""

from typing import Any, Dict, Optional
from fastapi import APIRouter
from pydantic import BaseModel, Field

from src.themes.archetypes import ARCHETYPES
from src.themes.morph import magic_morph

router = APIRouter(tags=["themes"])


class MagicMorphRequest(BaseModel):
    event_name: str = Field(..., min_length=1, max_length=128)
    event_purpose: Optional[str] = Field(default="", max_length=1000)


class MagicMorphResponse(BaseModel):
    archetype: str
    selected_archetype: str
    name: str
    description: str
    tokens: Dict[str, Any]
    theme_token_configuration: Dict[str, Any]
    scores: Optional[Dict[str, float]] = None


@router.post("/api/v1/themes/magic-morph", response_model=MagicMorphResponse)
def api_magic_morph(req: MagicMorphRequest):
    """
    Execute offline deterministic Magic Morph.
    Selects archetype and generates token configuration from event name and purpose.
    """
    return magic_morph(event_name=req.event_name, event_purpose=req.event_purpose or "")


@router.get("/api/v1/themes/archetypes")
def api_list_archetypes():
    """List all six available visual archetypes and their design token specifications."""
    return ARCHETYPES
