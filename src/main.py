"""ChameleonOS - Application Entry Point."""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, Optional

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.config import get_settings
from src.database import engine, get_db, init_db, SessionLocal
from src.auth.service import seed_users, print_auth_headers
from src.fixtures import load_fixtures
from src.auth.router import router as auth_router
from src.events.router import router as events_router
from src.submissions.router import router as submissions_router
from src.judging.router import router as judging_router
from src.normalization.router import router as normalization_router
from src.audit.router import router as audit_router
from src.themes.router import router as themes_router

settings = get_settings()
BASE_DIR = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan context manager for startup and shutdown tasks."""
    # Ensure SQLite database schema and tables are initialized
    init_db()

    # Seed users and print usable authentication headers to standard output
    with SessionLocal() as db:
        seed_data = seed_users(db)
        print_auth_headers(seed_data)

        # Idempotently load default fixtures if fixtures.json is present
        fixtures_path = BASE_DIR.parent / "fixtures.json"
        if fixtures_path.exists():
            load_fixtures(fixtures_path, db)

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


from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.responses import JSONResponse
from src.auth.dependencies import get_optional_user, extract_token_from_request
from src.auth.service import decode_access_token
from src.auth.models import User


@app.exception_handler(StarletteHTTPException)
async def custom_http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Handle HTTP exceptions with JSON for API routes and themed error pages for browser views."""
    if request.url.path.startswith("/api/"):
        headers = getattr(exc, "headers", None)
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail}, headers=headers)

    user = None
    try:
        token = extract_token_from_request(request)
        if token:
            payload = decode_access_token(token)
            if payload and payload.get("sub"):
                with SessionLocal() as db:
                    user = db.query(User).filter(User.id == payload["sub"], User.is_active.is_(True)).first()
    except Exception:
        user = None

    return templates.TemplateResponse(
        request=request,
        name="error.html",
        context={
            "request": request,
            "status_code": exc.status_code,
            "detail": exc.detail,
            "user": user,
            "settings": settings,
        },
        status_code=exc.status_code,
    )


@app.get("/", response_class=HTMLResponse, tags=["system"])
async def root_view(
    request: Request,
    user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Render landing page with active events, project stats, and current user status."""
    from src.events.models import Event
    from src.submissions.models import Project

    events = db.query(Event).all()
    recent_projects = db.query(Project).filter(Project.is_submitted.is_(True)).order_by(Project.submitted_at.desc()).limit(6).all()

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "request": request,
            "settings": settings,
            "user": user,
            "events": events,
            "recent_projects": recent_projects,
        },
    )


# Register domain routers
app.include_router(auth_router)
app.include_router(events_router)
app.include_router(submissions_router)
app.include_router(judging_router)
app.include_router(normalization_router)
app.include_router(audit_router)
app.include_router(themes_router)
