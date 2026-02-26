import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from ..auth import (
    check_login_rate_limit,
    create_session_token,
    get_client_ip,
    get_current_user,
    hash_password,
    verify_password,
)
from ..config import settings
from ..db import get_db
from ..models import User
from ..schemas import ChangePasswordRequest, LoginRequest, UserOut

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login")
def login(body: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    ip = get_client_ip(request)
    check_login_rate_limit(ip)

    user = db.query(User).filter(User.username == body.username).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    token = create_session_token(user.id, user.username, user.role)
    response.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=token,
        max_age=settings.SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=False,  # localhost
    )
    logger.info("User %s logged in from %s", user.username, ip)
    return {"id": user.id, "username": user.username, "role": user.role}


@router.post("/logout")
def logout(response: Response):
    # No auth required — just delete the cookie unconditionally.
    response.delete_cookie(settings.SESSION_COOKIE_NAME)
    return {"ok": True}


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@router.post("/change-password")
def change_password(
    body: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password incorrect")
    user.password_hash = hash_password(body.new_password)
    db.commit()
    return {"ok": True}
