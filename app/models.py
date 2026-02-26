from datetime import datetime

from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey,
    Index, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import relationship

from .db import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), default="user", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    settings = relationship("UserSettings", back_populates="user", uselist=False, cascade="all, delete-orphan")
    watchlists = relationship("Watchlist", back_populates="user", cascade="all, delete-orphan")
    portfolios = relationship("Portfolio", back_populates="user", cascade="all, delete-orphan")
    alerts = relationship("Alert", back_populates="user", cascade="all, delete-orphan")


class UserSettings(Base):
    __tablename__ = "settings"

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    theme = Column(String(20), default="dark")
    refresh_interval_sec = Column(Integer, default=60)
    default_currency = Column(String(10), default="EUR")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="settings")


class Symbol(Base):
    __tablename__ = "symbols"

    id = Column(Integer, primary_key=True)
    ticker = Column(String(20), unique=True, nullable=False, index=True)
    type = Column(String(20))
    name = Column(String(200))
    exchange = Column(String(50))
    currency = Column(String(10))
    last_seen_at = Column(DateTime)

    quotes = relationship("Quote", back_populates="symbol", cascade="all, delete-orphan")
    histories = relationship("History", back_populates="symbol", cascade="all, delete-orphan")


class Quote(Base):
    __tablename__ = "quotes"

    symbol_id = Column(Integer, ForeignKey("symbols.id", ondelete="CASCADE"), primary_key=True)
    ts = Column(DateTime, nullable=False)
    price = Column(Float)
    change_abs = Column(Float)
    change_pct = Column(Float)
    open = Column(Float)
    high = Column(Float)
    low = Column(Float)
    volume = Column(Float)
    source = Column(String(50), default="yfinance")
    stale = Column(Boolean, default=False)

    symbol = relationship("Symbol", back_populates="quotes")


class History(Base):
    __tablename__ = "history"

    id = Column(Integer, primary_key=True)
    symbol_id = Column(Integer, ForeignKey("symbols.id", ondelete="CASCADE"), nullable=False)
    period = Column(String(20), nullable=False)
    interval = Column(String(20), nullable=False)
    ts = Column(DateTime, nullable=False)
    open = Column(Float)
    high = Column(Float)
    low = Column(Float)
    close = Column(Float)
    volume = Column(Float)
    source = Column(String(50), default="yfinance")

    symbol = relationship("Symbol", back_populates="histories")

    __table_args__ = (
        Index("ix_history_sym_period_interval", "symbol_id", "period", "interval"),
    )


class Watchlist(Base):
    __tablename__ = "watchlists"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(100), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="watchlists")
    items = relationship("WatchlistItem", back_populates="watchlist", cascade="all, delete-orphan")


class WatchlistItem(Base):
    __tablename__ = "watchlist_items"

    id = Column(Integer, primary_key=True)
    watchlist_id = Column(Integer, ForeignKey("watchlists.id", ondelete="CASCADE"), nullable=False)
    symbol_id = Column(Integer, ForeignKey("symbols.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    watchlist = relationship("Watchlist", back_populates="items")
    symbol = relationship("Symbol")

    __table_args__ = (
        UniqueConstraint("watchlist_id", "symbol_id", name="uq_watchlist_symbol"),
    )


class Portfolio(Base):
    __tablename__ = "portfolios"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(100), nullable=False)
    base_currency = Column(String(10), default="EUR")
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="portfolios")
    transactions = relationship("Transaction", back_populates="portfolio", cascade="all, delete-orphan")


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True)
    portfolio_id = Column(Integer, ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False)
    symbol_id = Column(Integer, ForeignKey("symbols.id", ondelete="CASCADE"), nullable=False)
    ts = Column(DateTime, nullable=False)
    side = Column(String(10), nullable=False)  # buy | sell
    qty = Column(Float, nullable=False)
    price = Column(Float, nullable=False)
    fees = Column(Float, default=0.0)
    note = Column(Text)

    portfolio = relationship("Portfolio", back_populates="transactions")
    symbol = relationship("Symbol")


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    symbol_id = Column(Integer, ForeignKey("symbols.id", ondelete="CASCADE"), nullable=False)
    kind = Column(String(20), nullable=False)  # price | change_pct | drawdown
    threshold = Column(Float, nullable=False)
    direction = Column(String(10), nullable=False)  # above | below
    is_enabled = Column(Boolean, default=True)
    last_triggered_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="alerts")
    symbol = relationship("Symbol")
    events = relationship("AlertEvent", back_populates="alert", cascade="all, delete-orphan")


class AlertEvent(Base):
    __tablename__ = "alert_events"

    id = Column(Integer, primary_key=True)
    alert_id = Column(Integer, ForeignKey("alerts.id", ondelete="CASCADE"), nullable=False)
    ts = Column(DateTime, default=datetime.utcnow)
    message = Column(Text)
    payload_json = Column(Text)

    alert = relationship("Alert", back_populates="events")


class FetchLog(Base):
    __tablename__ = "fetch_log"

    id = Column(Integer, primary_key=True)
    key = Column(String(200), index=True)
    source = Column(String(50))
    fetched_at = Column(DateTime, default=datetime.utcnow)
    cache_hit = Column(Boolean, default=False)
    duration_ms = Column(Integer)
    ok = Column(Boolean, default=True)
    error = Column(Text)
