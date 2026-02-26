from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..db import get_db
from ..models import Alert, AlertEvent, User
from ..schemas import AlertCreate, AlertUpdate
from ..services.market import get_or_create_symbol

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


def _get_alert_or_404(alert_id: int, user: User, db: Session) -> Alert:
    a = db.query(Alert).filter(Alert.id == alert_id, Alert.user_id == user.id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Alert not found")
    return a


def _alert_dict(a: Alert) -> dict:
    return {
        "id": a.id,
        "ticker": a.symbol.ticker,
        "name": a.symbol.name,
        "kind": a.kind,
        "threshold": a.threshold,
        "direction": a.direction,
        "is_enabled": a.is_enabled,
        "last_triggered_at": a.last_triggered_at.isoformat() if a.last_triggered_at else None,
        "created_at": a.created_at.isoformat(),
    }


@router.get("")
def list_alerts(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    alerts = db.query(Alert).filter(Alert.user_id == user.id).order_by(Alert.created_at.desc()).all()
    return [_alert_dict(a) for a in alerts]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_alert(
    body: AlertCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    sym = get_or_create_symbol(body.ticker.upper(), db)
    a = Alert(
        user_id=user.id,
        symbol_id=sym.id,
        kind=body.kind,
        threshold=body.threshold,
        direction=body.direction,
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    return _alert_dict(a)


@router.put("/{alert_id}")
def update_alert(
    alert_id: int,
    body: AlertUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    a = _get_alert_or_404(alert_id, user, db)
    if body.is_enabled is not None:
        a.is_enabled = body.is_enabled
    if body.threshold is not None:
        a.threshold = body.threshold
    if body.direction is not None:
        if body.direction not in ("above", "below"):
            raise HTTPException(status_code=400, detail="direction must be 'above' or 'below'")
        a.direction = body.direction
    db.commit()
    return _alert_dict(a)


@router.delete("/{alert_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_alert(
    alert_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    a = _get_alert_or_404(alert_id, user, db)
    db.delete(a)
    db.commit()


@router.get("/events")
def list_events(
    limit: int = Query(50, le=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    events = (
        db.query(AlertEvent)
        .join(Alert)
        .filter(Alert.user_id == user.id)
        .order_by(AlertEvent.ts.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": e.id,
            "alert_id": e.alert_id,
            "ticker": e.alert.symbol.ticker,
            "ts": e.ts.isoformat(),
            "message": e.message,
            "payload": e.payload_json,
        }
        for e in events
    ]
