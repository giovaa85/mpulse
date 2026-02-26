from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, field_validator


# ── Auth ─────────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def pw_strength(cls, v: str) -> str:
        if len(v) < 4:
            raise ValueError("Password must be at least 4 characters")
        return v


class UserOut(BaseModel):
    id: int
    username: str
    role: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Settings ─────────────────────────────────────────────────────────────────

class SettingsOut(BaseModel):
    theme: str
    refresh_interval_sec: int
    default_currency: str

    model_config = {"from_attributes": True}


class SettingsUpdate(BaseModel):
    theme: Optional[str] = None
    refresh_interval_sec: Optional[int] = None
    default_currency: Optional[str] = None


# ── Symbols / Quotes ──────────────────────────────────────────────────────────

class SymbolOut(BaseModel):
    ticker: str
    name: Optional[str] = None
    type: Optional[str] = None
    exchange: Optional[str] = None
    currency: Optional[str] = None

    model_config = {"from_attributes": True}


class QuoteOut(BaseModel):
    ticker: str
    name: Optional[str] = None
    price: Optional[float] = None
    change_abs: Optional[float] = None
    change_pct: Optional[float] = None
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    volume: Optional[float] = None
    currency: Optional[str] = None
    ts: Optional[str] = None
    stale: bool = False
    stale_reason: Optional[str] = None
    last_ok_at: Optional[str] = None


class HistoryBar(BaseModel):
    ts: str
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    volume: Optional[float] = None


class HistoryOut(BaseModel):
    ticker: str
    period: str
    interval: str
    data: list[HistoryBar]
    stale: bool = False
    stale_reason: Optional[str] = None
    fetched_at: Optional[str] = None


# ── Watchlists ────────────────────────────────────────────────────────────────

class WatchlistCreate(BaseModel):
    name: str


class WatchlistUpdate(BaseModel):
    name: str


class WatchlistItemAdd(BaseModel):
    ticker: str


class WatchlistItemOut(BaseModel):
    ticker: str
    name: Optional[str] = None
    price: Optional[float] = None
    change_abs: Optional[float] = None
    change_pct: Optional[float] = None
    currency: Optional[str] = None
    stale: bool = False


class WatchlistOut(BaseModel):
    id: int
    name: str
    created_at: datetime
    items: list[WatchlistItemOut] = []

    model_config = {"from_attributes": True}


# ── Portfolios ────────────────────────────────────────────────────────────────

class PortfolioCreate(BaseModel):
    name: str
    base_currency: str = "EUR"


class PortfolioUpdate(BaseModel):
    name: Optional[str] = None
    base_currency: Optional[str] = None


class PortfolioOut(BaseModel):
    id: int
    name: str
    base_currency: str
    created_at: datetime

    model_config = {"from_attributes": True}


class TransactionCreate(BaseModel):
    ticker: str
    ts: str  # ISO datetime string
    side: str
    qty: float
    price: float
    fees: float = 0.0
    note: Optional[str] = None

    @field_validator("side")
    @classmethod
    def validate_side(cls, v: str) -> str:
        v = v.lower()
        if v not in ("buy", "sell"):
            raise ValueError("side must be 'buy' or 'sell'")
        return v

    @field_validator("qty", "price")
    @classmethod
    def positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("Must be positive")
        return v


class TransactionOut(BaseModel):
    id: int
    ticker: str
    ts: datetime
    side: str
    qty: float
    price: float
    fees: float
    note: Optional[str] = None

    model_config = {"from_attributes": True}


class HoldingOut(BaseModel):
    ticker: str
    name: Optional[str] = None
    qty: float
    avg_cost: float
    total_cost: float
    current_price: Optional[float] = None
    current_value: Optional[float] = None
    unrealized_pnl: Optional[float] = None
    unrealized_pnl_pct: Optional[float] = None
    currency: Optional[str] = None


class PerformanceOut(BaseModel):
    equity_curve: list[dict]
    metrics: dict[str, Any]


# ── Alerts ────────────────────────────────────────────────────────────────────

class AlertCreate(BaseModel):
    ticker: str
    kind: str
    threshold: float
    direction: str

    @field_validator("kind")
    @classmethod
    def validate_kind(cls, v: str) -> str:
        if v not in ("price", "change_pct", "drawdown"):
            raise ValueError("kind must be 'price', 'change_pct', or 'drawdown'")
        return v

    @field_validator("direction")
    @classmethod
    def validate_direction(cls, v: str) -> str:
        if v not in ("above", "below"):
            raise ValueError("direction must be 'above' or 'below'")
        return v


class AlertUpdate(BaseModel):
    is_enabled: Optional[bool] = None
    threshold: Optional[float] = None
    direction: Optional[str] = None


class AlertOut(BaseModel):
    id: int
    ticker: str
    kind: str
    threshold: float
    direction: str
    is_enabled: bool
    last_triggered_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AlertEventOut(BaseModel):
    id: int
    alert_id: int
    ts: datetime
    message: Optional[str] = None
    payload_json: Optional[str] = None

    model_config = {"from_attributes": True}


# ── Markets ───────────────────────────────────────────────────────────────────

class IndexQuote(BaseModel):
    ticker: str
    name: str
    price: Optional[float] = None
    change_abs: Optional[float] = None
    change_pct: Optional[float] = None
    currency: Optional[str] = None
    stale: bool = False


class CryptoItem(BaseModel):
    id: str
    name: str
    symbol: str
    price_usd: float
    change_24h_pct: Optional[float] = None
    market_cap: Optional[float] = None
    volume_24h: Optional[float] = None
    image: Optional[str] = None
    stale: bool = False
