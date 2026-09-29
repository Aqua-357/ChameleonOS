"""Authentication service with password hashing, signed bearer tokens, and seed credentials."""

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any, Dict, Optional
from sqlalchemy.orm import Session

from src.auth.models import User
from src.config import get_settings

settings = get_settings()

SEED_USERS_CONFIG = [
    {
        "id": "usr_organizer",
        "username": "organizer",
        "email": "organizer@chameleon.local",
        "password": "organizer_pass_2026",
        "role": "organizer",
    },
    {
        "id": "usr_judge_a",
        "username": "judge_a",
        "email": "judge_a@chameleon.local",
        "password": "judge_a_pass_2026",
        "role": "judge",
    },
    {
        "id": "usr_judge_b",
        "username": "judge_b",
        "email": "judge_b@chameleon.local",
        "password": "judge_b_pass_2026",
        "role": "judge",
    },
    {
        "id": "usr_participant",
        "username": "participant",
        "email": "participant@chameleon.local",
        "password": "participant_pass_2026",
        "role": "participant",
    },
]


def hash_password(password: str) -> str:
    """Hash password with secure salt using SHA-256."""
    salt = secrets.token_hex(16)
    hashed = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
    return f"{salt}:{hashed}"


def verify_password(password: str, hashed_password: str) -> bool:
    """Verify raw password against salted hash."""
    if not hashed_password or ":" not in hashed_password:
        return False
    salt, expected = hashed_password.split(":", 1)
    computed = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
    return hmac.compare_digest(computed, expected)


def create_access_token(
    user_id: str,
    role: str,
    username: str,
    secret_key: Optional[str] = None,
    expires_in_seconds: int = 30 * 24 * 3600,
) -> str:
    """Generate self-contained HMAC-SHA256 signed bearer token."""
    key = secret_key or settings.secret_key
    payload = {
        "sub": user_id,
        "username": username,
        "role": role,
        "iat": int(time.time()),
        "exp": int(time.time()) + expires_in_seconds,
    }
    payload_json = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    payload_b64 = base64.urlsafe_b64encode(payload_json).decode("utf-8").rstrip("=")
    signature = hmac.new(key.encode("utf-8"), payload_b64.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload_b64}.{signature}"


def decode_access_token(token: str, secret_key: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Verify and decode signed bearer token."""
    key = secret_key or settings.secret_key
    try:
        if "." not in token:
            return None
        payload_b64, signature = token.split(".", 1)
        expected_sig = hmac.new(key.encode("utf-8"), payload_b64.encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected_sig):
            return None

        # Restore base64 padding
        remainder = len(payload_b64) % 4
        if remainder > 0:
            payload_b64 += "=" * (4 - remainder)

        payload_bytes = base64.urlsafe_b64decode(payload_b64.encode("utf-8"))
        payload = json.loads(payload_bytes.decode("utf-8"))

        if payload.get("exp") and payload["exp"] < time.time():
            return None
        return payload
    except Exception:
        return None


def seed_users(db: Session) -> Dict[str, Dict[str, Any]]:
    """
    Idempotently seed default users (organizer, judge_a, judge_b, participant)
    and return their credentials and authentication tokens.
    """
    results: Dict[str, Dict[str, Any]] = {}

    for cfg in SEED_USERS_CONFIG:
        user = db.query(User).filter(
            (User.id == cfg["id"]) | (User.username == cfg["username"])
        ).first()

        if not user:
            user = User(
                id=cfg["id"],
                username=cfg["username"],
                email=cfg["email"],
                hashed_password=hash_password(cfg["password"]),
                role=cfg["role"],
                is_active=True,
            )
            db.add(user)
            db.commit()
            db.refresh(user)

        token = create_access_token(user_id=user.id, role=user.role, username=user.username)
        results[user.username] = {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "role": user.role,
            "password": cfg["password"],
            "token": token,
            "auth_header": f"Bearer {token}",
        }

    return results


def print_auth_headers(seed_data: Dict[str, Dict[str, Any]]) -> None:
    """Print usable authentication headers to standard output upon application start."""
    border = "=" * 80
    print("\n" + border)
    print("[ChameleonOS] Seed Authentication Headers")
    print(border)
    for username, data in seed_data.items():
        role_label = data["role"].upper().replace("_", " ")
        print(f"[{role_label:12}] Username : {data['username']:<15} (Email: {data['email']})")
        print(f"               Password : {data['password']}")
        print(f"               Header   : Authorization: {data['auth_header']}")
        print("-" * 80)
    print(border + "\n", flush=True)
