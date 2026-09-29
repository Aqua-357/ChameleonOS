"""Authentication API and HTML routes."""

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
from sqlalchemy.orm import Session

from src.auth.dependencies import get_current_user, get_optional_user
from src.auth.models import User
from src.auth.schemas import (
    TokenResponse,
    UserLoginRequest,
    UserRegisterRequest,
    UserResponse,
)
from src.auth.service import (
    SESSION_COOKIE_NAME,
    authenticate_user,
    create_access_token,
    register_user,
)
from src.database import get_db

router = APIRouter(tags=["auth"])

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


# ==============================================================================
# JSON API ENDPOINTS
# ==============================================================================

@router.post("/api/v1/auth/register", response_model=TokenResponse)
def api_register(
    req: UserRegisterRequest,
    response: Response,
    db: Session = Depends(get_db),
):
    try:
        user = register_user(
            db=db,
            username=req.username,
            email=req.email,
            password=req.password,
            role=req.role,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    token = create_access_token(user_id=user.id, role=user.role, username=user.username)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        max_age=30 * 24 * 3600,
        samesite="lax",
    )
    return TokenResponse(
        access_token=token,
        user=UserResponse.model_validate(user),
    )


@router.post("/api/v1/auth/login", response_model=TokenResponse)
def api_login(
    req: UserLoginRequest,
    response: Response,
    db: Session = Depends(get_db),
):
    user = authenticate_user(
        db=db,
        username_or_email=req.username_or_email,
        password=req.password,
    )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username/email or password.",
        )

    token = create_access_token(user_id=user.id, role=user.role, username=user.username)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        max_age=30 * 24 * 3600,
        samesite="lax",
    )
    return TokenResponse(
        access_token=token,
        user=UserResponse.model_validate(user),
    )


@router.post("/api/v1/auth/logout")
def api_logout(response: Response):
    response.delete_cookie(key=SESSION_COOKIE_NAME)
    return {"status": "logged_out"}


@router.get("/api/v1/auth/me", response_model=UserResponse)
def api_me(current_user: User = Depends(get_current_user)):
    return UserResponse.model_validate(current_user)


# ==============================================================================
# HTML VIEW ROUTES
# ==============================================================================

@router.get("/login", response_class=HTMLResponse)
def login_view(request: Request, user: User = Depends(get_optional_user)):
    if user:
        return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"request": request, "user": None},
    )


@router.post("/login", response_class=HTMLResponse)
def login_form_post(
    request: Request,
    username_or_email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = authenticate_user(db, username_or_email, password)
    if not user:
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"request": request, "error": "Invalid username or password.", "user": None},
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    token = create_access_token(user_id=user.id, role=user.role, username=user.username)
    redirect = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    redirect.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        max_age=30 * 24 * 3600,
        samesite="lax",
    )
    return redirect


@router.get("/register", response_class=HTMLResponse)
def register_view(request: Request, user: User = Depends(get_optional_user)):
    if user:
        return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    return templates.TemplateResponse(
        request=request,
        name="register.html",
        context={"request": request, "user": None},
    )


@router.post("/register", response_class=HTMLResponse)
def register_form_post(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    role: str = Form("participant"),
    db: Session = Depends(get_db),
):
    try:
        user = register_user(db, username, email, password, role)
    except ValueError as e:
        return templates.TemplateResponse(
            request=request,
            name="register.html",
            context={"request": request, "error": str(e), "user": None},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    token = create_access_token(user_id=user.id, role=user.role, username=user.username)
    redirect = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    redirect.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        max_age=30 * 24 * 3600,
        samesite="lax",
    )
    return redirect


@router.get("/logout")
def logout_view():
    redirect = RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    redirect.delete_cookie(key=SESSION_COOKIE_NAME)
    return redirect
