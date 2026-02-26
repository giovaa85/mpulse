import logging
import time
from collections import defaultdict
from typing import Optional

import bcrypt
from fastapi import Cookie, Depends, HTTPException, Request, status
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .models import User

logger = logging.getLogger(__name__)

_serializer = URLSafeTimedSerializer(settings.SECRET_KEY, salt="mp-session")

# In-memory rate limiter: {ip: [timestamp, ...]}
_login_attempts: dict[str, list[float]] = defaultdict(list)


# ── Password ──────────────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except Exception:
        return False


# ── Session tokens ────────────────────────────────────────────────────────────

def create_session_token(user_id: int, username: str, role: str) -> str:
    return _serializer.dumps({"id": user_id, "username": username, "role": role})


def decode_session_token(token: str) -> dict:
    """Raises HTTPException(401) on invalid/expired token."""
    try:
        return _serializer.loads(token, max_age=settings.SESSION_MAX_AGE)
    except SignatureExpired:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")
    except BadSignature:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")


# ── FastAPI dependencies ──────────────────────────────────────────────────────

def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> User:
    token = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    data = decode_session_token(token)
    user = db.get(User, data["id"])
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin required")
    return user


# ── Rate limiting ─────────────────────────────────────────────────────────────

def check_login_rate_limit(ip: str) -> None:
    """Raises 429 if too many login attempts from this IP."""
    now = time.time()
    window = settings.LOGIN_WINDOW_SECS
    max_attempts = settings.LOGIN_MAX_ATTEMPTS

    _login_attempts[ip] = [t for t in _login_attempts[ip] if now - t < window]

    if len(_login_attempts[ip]) >= max_attempts:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many login attempts. Try again in {window // 60} minutes.",
        )
    _login_attempts[ip].append(now)


def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
