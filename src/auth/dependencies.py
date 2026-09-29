"""Authentication and role-based access control dependencies."""

from typing import Callable, List, Optional, Set
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from src.auth.models import User
from src.auth.service import SESSION_COOKIE_NAME, decode_access_token
from src.database import get_db


def extract_token_from_request(request: Request) -> Optional[str]:
    """Extract bearer token from Authorization header or session cookie."""
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header[7:].strip()

    # Fallback to session cookie
    cookie_token = request.cookies.get(SESSION_COOKIE_NAME)
    if cookie_token:
        return cookie_token.strip()

    return None


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> User:
    """Resolve authenticated user or raise 401 Unauthorized."""
    token = extract_token_from_request(request)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please log in.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_access_token(token)
    if not payload or not payload.get("sub"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = db.query(User).filter(User.id == payload["sub"]).first()
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


def get_optional_user(
    request: Request,
    db: Session = Depends(get_db),
) -> Optional[User]:
    """
    Resolve authenticated user if credentials are provided.
    Returns None for visitors/unauthenticated requests.
    """
    token = extract_token_from_request(request)
    if not token:
        return None

    payload = decode_access_token(token)
    if not payload or not payload.get("sub"):
        return None

    return db.query(User).filter(User.id == payload["sub"], User.is_active.is_(True)).first()


def require_role(*allowed_roles: str) -> Callable[[User], User]:
    """
    Dependency factory requiring user to possess one of the allowed roles.
    Admins are always granted access by default.
    """
    roles_set: Set[str] = set(allowed_roles)

    def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role == "admin":
            return current_user
        if current_user.role not in roles_set:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Forbidden: Access requires one of {sorted(list(roles_set))} roles.",
            )
        return current_user

    return role_checker
