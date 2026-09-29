"""Event and theme API routes."""

from fastapi import APIRouter

router = APIRouter(prefix="/events", tags=["events"])
