from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..db import get_db
from ..models import User
from ..services.crypto import get_crypto_overview
from ..services.market import get_markets_overview

router = APIRouter(prefix="/api", tags=["markets"])


@router.get("/markets/overview")
def markets_overview(
    force: bool = False,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    data = get_markets_overview(db)
    return {"data": data, "count": len(data)}


@router.get("/crypto/overview")
def crypto_overview(
    force: bool = False,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    data = get_crypto_overview(db, force_refresh=force)
    return {"data": data, "count": len(data)}
