from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..db import get_db
from ..models import User, UserSettings
from ..schemas import SettingsOut, SettingsUpdate

router = APIRouter(prefix="/api/settings", tags=["settings"])


def _ensure_settings(user: User, db: Session) -> UserSettings:
    s = db.get(UserSettings, user.id)
    if not s:
        s = UserSettings(user_id=user.id)
        db.add(s)
        db.commit()
        db.refresh(s)
    return s


@router.get("", response_model=SettingsOut)
def get_settings(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _ensure_settings(user, db)


@router.put("", response_model=SettingsOut)
def update_settings(
    body: SettingsUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    s = _ensure_settings(user, db)
    if body.theme is not None:
        if body.theme not in ("dark", "light"):
            from fastapi import HTTPException
            raise HTTPException(status_code=400, detail="theme must be 'dark' or 'light'")
        s.theme = body.theme
    if body.refresh_interval_sec is not None:
        s.refresh_interval_sec = max(10, min(3600, body.refresh_interval_sec))
    if body.default_currency is not None:
        s.default_currency = body.default_currency
    db.commit()
    db.refresh(s)
    return s
