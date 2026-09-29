"""ChameleonOS - Application Entry Point."""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncGenerator, Dict

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import text

from src.config import get_settings
from src.database import engine, init_db
from src.auth.router import router as auth_router
from src.events.router import router as events_router
from src.submissions.router import router as submissions_router
from src.judging.router import router as judging_router
from src.normalization.router import router as normalization_router
from src.audit.router import router as audit_router

settings = get_settings()
BASE_DIR = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan context manager for startup and shutdown tasks."""
    # Ensure SQLite database schema and tables are initialized
    init_db()
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Self-hostable hackathon submission and judging platform with an adaptive event theme system.",
    lifespan=lifespan,
    # Disable default CDN-dependent documentation to ensure zero external network calls
    docs_url=None,
    redoc_url=None,
)

# Mount self-contained static assets
static_dir = BASE_DIR / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Configure Jinja2 templates (pure local assets, no external CDN)
templates_dir = BASE_DIR / "templates"
templates = Jinja2Templates(directory=str(templates_dir))


@app.get("/health", tags=["system"])
async def health_check() -> Dict[str, Any]:
    """Health check endpoint to verify system and database status."""
    db_status = "connected"
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as e:
        db_status = f"unhealthy: {str(e)}"

    return {
        "status": "healthy" if db_status == "connected" else "degraded",
        "service": settings.app_name,
        "version": settings.app_version,
        "environment": settings.app_env,
        "database": db_status,
    }


@app.get("/", response_class=HTMLResponse, tags=["system"])
async def root_view(request: Request) -> HTMLResponse:
    """Render landing page with system status."""
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"request": request, "settings": settings},
    )


# Register domain routers under API prefix
api_routers = [
    auth_router,
    events_router,
    submissions_router,
    judging_router,
    normalization_router,
    audit_router,
]

for router in api_routers:
    app.include_router(router, prefix=settings.api_v1_str)
