"""
Market data service — Stooq CSV.
Maintains a module-level httpx.Client so connections persist.
Falls back to stale DB cache when the remote is unavailable.
"""
import logging
import math
import re
import time
import threading
from datetime import datetime, timedelta
from typing import Optional

import httpx
import yfinance as yf
from sqlalchemy.orm import Session

from ..config import settings
from ..models import FetchLog, History, Quote, Symbol
from .cache import log_fetch

logger = logging.getLogger(__name__)

# ── Persistent HTTP session ───────────────────────────────────────────────────

_SESSION: Optional[httpx.Client] = None
_SESSION_LOCK = threading.Lock()

_STOOQ_BASE = "https://stooq.com/q/d/l/"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# ISIN pattern: 2 letters + 10 alphanumeric chars (total 12)
_ISIN_RE = re.compile(r'^[A-Z]{2}[A-Z0-9]{9}[0-9]$')

# Exchange suffixes to try when the plain .us lookup fails (in priority order)
_EXCHANGE_SUFFIXES = [".us", ".uk", ".de", ".nl", ".fr", ".it", ".pl", ".jp", ".au", ".hk", ".sw", ".ch"]

# Yahoo Finance / Bloomberg exchange suffix → Stooq suffix
_YF_TO_STOOQ: dict[str, str] = {
    ".MI": ".it",   # Borsa Italiana
    ".PA": ".fr",   # Euronext Paris
    ".AS": ".nl",   # Euronext Amsterdam
    ".BR": ".be",   # Euronext Brussels
    ".LS": ".pt",   # Euronext Lisbon
    ".VI": ".at",   # Vienna
    ".ST": ".se",   # OMX Stockholm
    ".CO": ".dk",   # OMX Copenhagen
    ".OL": ".no",   # Oslo
    ".HE": ".fi",   # OMX Helsinki
    ".L":  ".uk",   # London
    ".AX": ".au",   # ASX
    ".T":  ".jp",   # Tokyo
    ".HK": ".hk",   # Hong Kong
    ".SW": ".sw",   # SIX Swiss
    ".MC": ".es",   # BME Madrid
}

# Stooq suffix → Yahoo Finance suffix (reverse of _YF_TO_STOOQ, for fallback)
_STOOQ_TO_YF_SUFFIX: dict[str, str] = {
    ".it": ".MI", ".fr": ".PA", ".nl": ".AS", ".be": ".BR",
    ".pt": ".LS", ".at": ".VI", ".se": ".ST", ".dk": ".CO",
    ".no": ".OL", ".fi": ".HE", ".uk": ".L",  ".au": ".AX",
    ".jp": ".T",  ".hk": ".HK", ".sw": ".SW", ".es": ".MC",
    ".de": ".DE", ".us": "",    # US: strip suffix for yfinance
}

# Stooq index → Yahoo Finance index ticker
_STOOQ_INDEX_TO_YF: dict[str, str] = {
    "^spx": "^GSPC", "^ndx": "^NDX",  "^dji": "^DJI",
    "^dax": "^GDAXI","^ukx": "^FTSE", "^cac": "^FCHI",
    "^aex": "^AEX",  "^smi": "^SSMI", "^nkx": "^N225",
    "^hsi": "^HSI",  "^ibex": "^IBEX","^mib": "FTSEMIB.MI",
}

# Index ticker mapping (canonical → Stooq lowercase)
_INDEX_MAP: dict[str, str] = {
    # Yahoo Finance style → Stooq
    "^GSPC": "^spx", "^IXIC": "^ndx", "^GDAXI": "^dax",
    "^FTSE": "^ukx", "FTSEMIB.MI": "^mib",
    # Stooq style (case variants)
    "^SPX": "^spx", "^NDX": "^ndx", "^DJI": "^dji",
    "^DAX": "^dax", "^UKX": "^ukx", "^CAC": "^cac",
    "^IBEX": "^ibex", "^MIB": "^mib", "^AEX": "^aex",
    "^SMI": "^smi", "^N225": "^nkx", "^HSI": "^hsi",
}


def _get_session() -> httpx.Client:
    global _SESSION
    if _SESSION is None:
        _SESSION = httpx.Client(
            headers=_HEADERS,
            follow_redirects=True,
            timeout=15.0,
        )
    return _SESSION


def _to_yf_ticker(stooq_t: str) -> str:
    """Convert a Stooq-format ticker to Yahoo Finance format."""
    low = stooq_t.lower()
    if low in _STOOQ_INDEX_TO_YF:
        return _STOOQ_INDEX_TO_YF[low]
    if low.startswith("^"):
        return stooq_t.upper()
    for stooq_sfx, yf_sfx in _STOOQ_TO_YF_SUFFIX.items():
        if low.endswith(stooq_sfx):
            base = stooq_t[: -len(stooq_sfx)].upper()
            return base + yf_sfx
    return stooq_t.upper()


def _yfinance_bars(yf_ticker: str, since: Optional[datetime] = None) -> list[dict]:
    """Fetch OHLCV bars from yfinance. Returns same format as _stooq_fetch."""
    yt = yf.Ticker(yf_ticker)
    if since:
        hist = yt.history(start=since.strftime("%Y-%m-%d"), interval="1d", auto_adjust=True)
    else:
        hist = yt.history(period="10d", interval="1d", auto_adjust=True)
    if hist.empty:
        raise ValueError(f"Nessun dato yfinance per '{yf_ticker}'")
    bars = []
    for dt, row in hist.iterrows():
        close = row.get("Close")
        if close is None or (isinstance(close, float) and math.isnan(close)):
            continue
        def _safe_float(v):
            try:
                f = float(v)
                return None if math.isnan(f) else f
            except (TypeError, ValueError):
                return None
        bars.append({
            "ts":     dt.to_pydatetime().replace(tzinfo=None),
            "open":   _safe_float(row.get("Open")),
            "high":   _safe_float(row.get("High")),
            "low":    _safe_float(row.get("Low")),
            "close":  float(close),
            "volume": int(float(row["Volume"])) if _safe_float(row.get("Volume")) else None,
        })
    if not bars:
        raise ValueError(f"Nessuna barra valida da yfinance per '{yf_ticker}'")
    return bars


def _stooq_ticker(ticker: str) -> str:
    """Convert a canonical ticker to Stooq format (fast path, no network)."""
    mapped = _INDEX_MAP.get(ticker) or _INDEX_MAP.get(ticker.upper())
    if mapped:
        return mapped
    # Map Yahoo Finance / Bloomberg exchange suffixes to Stooq
    upper = ticker.upper()
    for yf_suffix, stooq_suffix in _YF_TO_STOOQ.items():
        if upper.endswith(yf_suffix):
            base = ticker[: -len(yf_suffix)]
            return base.lower() + stooq_suffix
    # Already has Stooq-style extension or is an index
    if "." in ticker or ticker.startswith("^"):
        return ticker.lower()
    # Plain stock ticker: assume US
    return f"{ticker.lower()}.us"


def _resolve_stooq_ticker(ticker: str, exchange_hint: Optional[str],
                          since: Optional[datetime],
                          interval: str = "d") -> tuple[str, list[dict]]:
    """
    Try to fetch data for `ticker`, using `exchange_hint` first if known.
    Falls back through _EXCHANGE_SUFFIXES until data is found.
    Returns (stooq_ticker, bars).
    Raises ValueError if nothing works.
    """
    # Indices and tickers with explicit exchange suffix: single attempt
    if ticker.startswith("^") or ticker in _INDEX_MAP or ticker.upper() in _INDEX_MAP or "." in ticker:
        stooq_t = _stooq_ticker(ticker)
        return stooq_t, _stooq_fetch(stooq_t, since=since, interval=interval)

    base = ticker.lower()

    # If we already know which exchange worked, try it first
    if exchange_hint and exchange_hint.startswith("."):
        stooq_t = base + exchange_hint
        try:
            return stooq_t, _stooq_fetch(stooq_t, since=since, interval=interval)
        except ValueError:
            pass

    # Try all exchange suffixes in order
    for suffix in _EXCHANGE_SUFFIXES:
        stooq_t = base + suffix
        try:
            bars = _stooq_fetch(stooq_t, since=since, interval=interval)
            return stooq_t, bars
        except ValueError:
            continue

    raise ValueError(
        f"No data found for '{ticker}' on any exchange. "
        f"Try specifying the exchange, e.g. '{ticker}.UK' or '{ticker}.DE'."
    )


def _period_start(period: str) -> Optional[datetime]:
    """Return start datetime for the given period, or None for max."""
    now = datetime.utcnow()
    deltas = {
        "1d":  timedelta(days=5),
        "5d":  timedelta(days=10),
        "1mo": timedelta(days=35),
        "3mo": timedelta(days=100),
        "6mo": timedelta(days=190),
        "1y":  timedelta(days=370),
        "2y":  timedelta(days=740),
        "5y":  timedelta(days=1835),
        "10y": timedelta(days=3660),
    }
    if period == "max":
        return None
    if period == "ytd":
        return datetime(now.year, 1, 1)
    return now - deltas.get(period, timedelta(days=370))


def _stooq_interval(interval: str) -> str:
    """Map YF-style interval to Stooq interval code (d/w/m)."""
    if interval == "1wk":
        return "w"
    if interval in ("1mo", "3mo"):
        return "m"
    return "d"  # intraday not supported by Stooq; use daily


def _stooq_fetch(stooq_ticker: str, since: Optional[datetime] = None,
                 interval: str = "d") -> list[dict]:
    """
    Fetch full CSV history from Stooq and return bar dicts sorted by date.
    Optionally filters to bars on or after `since`.
    Raises ValueError if no data is available.
    Note: date-range params are NOT passed to Stooq (they cause server errors);
    all filtering is done client-side.
    """
    with _SESSION_LOCK:
        sess = _get_session()
        params: dict = {"s": stooq_ticker, "i": interval}
        resp = sess.get(_STOOQ_BASE, params=params, timeout=15)
        resp.raise_for_status()
        text = resp.text.strip()

    if "Exceeded the daily hits limit" in text:
        raise ValueError("Stooq daily request limit reached. Try again tomorrow or use cached data.")
    if not text or "No data" in text:
        raise ValueError(f"No data for {stooq_ticker}")

    lines = text.splitlines()
    if len(lines) < 2:
        raise ValueError(f"Insufficient data for {stooq_ticker}")

    bars = []
    for line in lines[1:]:
        parts = line.split(",")
        if len(parts) < 5:
            continue
        try:
            dt = datetime.strptime(parts[0].strip(), "%Y-%m-%d")
            if since and dt < since:
                continue
            close_s = parts[4].strip()
            if not close_s:
                continue
            close = float(close_s)
            if math.isnan(close):
                continue
            vol_s = parts[5].strip() if len(parts) > 5 else ""
            bars.append({
                "ts":     dt,
                "open":   float(parts[1].strip()) if parts[1].strip() else None,
                "high":   float(parts[2].strip()) if parts[2].strip() else None,
                "low":    float(parts[3].strip()) if parts[3].strip() else None,
                "close":  close,
                "volume": int(float(vol_s)) if vol_s else None,
            })
        except (ValueError, IndexError):
            continue

    if not bars:
        raise ValueError(f"No valid bars parsed for {stooq_ticker}")
    return bars


# ── Helpers ───────────────────────────────────────────────────────────────────

def _valid(v) -> bool:
    return v is not None and not (isinstance(v, float) and math.isnan(v))


def _safe(v, default=None):
    return v if _valid(v) else default


def _dt_str(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


def _quote_from_bars(bars: list[dict], ticker: str, name: str = None) -> dict:
    """Extract quote data from the last two bars."""
    latest = bars[-1]
    prev = bars[-2] if len(bars) >= 2 else None
    price = latest["close"]
    prev_close = prev["close"] if prev else None
    chg = (price - prev_close) if (price and prev_close) else None
    chgp = (chg / prev_close * 100) if (chg is not None and prev_close) else None
    return {
        "price": price, "change_abs": chg, "change_pct": chgp,
        "open": latest.get("open"), "high": latest.get("high"),
        "low": latest.get("low"), "volume": latest.get("volume"),
        "name": name or ticker, "currency": None, "exchange": None,
        "type": "index" if ticker.startswith("^") else "stock",
    }


# ── Symbol management ─────────────────────────────────────────────────────────

def get_or_create_symbol(ticker: str, db: Session, type_hint: str = "stock") -> Symbol:
    ticker = ticker.upper()

    if _ISIN_RE.match(ticker):
        raise ValueError(
            f"'{ticker}' looks like an ISIN. Please use the ticker symbol instead "
            f"(e.g. 'IWDA', 'IWDA.UK', 'SPY')."
        )

    sym = db.query(Symbol).filter(Symbol.ticker == ticker).first()
    if sym:
        return sym

    name = settings.INDEX_NAMES.get(ticker, ticker)
    sym_type = "index" if ticker.startswith("^") else type_hint

    sym = Symbol(
        ticker=ticker, name=name, type=sym_type,
        exchange=None, currency="USD",
        last_seen_at=datetime.utcnow(),
    )
    db.add(sym)
    db.commit()
    db.refresh(sym)
    return sym


def search_symbols(q: str, db: Session, limit: int = 10) -> list[dict]:
    q = q.upper().strip()
    if not q:
        return []
    results = (
        db.query(Symbol)
        .filter((Symbol.ticker.like(f"{q}%")) | (Symbol.name.ilike(f"%{q}%")))
        .limit(limit)
        .all()
    )
    return [{"ticker": s.ticker, "name": s.name, "type": s.type, "currency": s.currency}
            for s in results]


# ── Quote ─────────────────────────────────────────────────────────────────────

def get_quote(ticker: str, db: Session, force_refresh: bool = False) -> dict:
    sym = get_or_create_symbol(ticker, db)
    cache_key = f"quote:{sym.ticker}"
    now = datetime.utcnow()

    existing: Optional[Quote] = db.get(Quote, sym.id)

    if not force_refresh and existing and existing.price is not None:
        if (now - existing.ts).total_seconds() < settings.QUOTE_TTL:
            log_fetch(db, cache_key, "cache", cache_hit=True)
            return _quote_to_dict(existing, sym)

    t0 = time.perf_counter()
    since = datetime.utcnow() - timedelta(days=10)
    bars = None
    source = "stooq"
    stooq_exc_msg = None

    # ── Try Stooq first ───────────────────────────────────────────────────────
    try:
        stooq_t, bars = _resolve_stooq_ticker(sym.ticker, sym.exchange, since)
        resolved_suffix = stooq_t[len(sym.ticker.lower()):]
    except Exception as exc:
        stooq_exc_msg = str(exc)
        logger.debug("Stooq failed for %s: %s — trying yfinance", ticker, exc)

    # ── yfinance fallback ─────────────────────────────────────────────────────
    if bars is None:
        try:
            stooq_t = _stooq_ticker(sym.ticker)
            yf_t = _to_yf_ticker(stooq_t)
            bars = _yfinance_bars(yf_t, since)
            resolved_suffix = stooq_t[len(sym.ticker.lower()):]
            source = "yfinance"
            logger.info("yfinance OK for %s (as %s)", ticker, yf_t)
        except Exception as yf_exc:
            # Both sources failed
            ms = int((time.perf_counter() - t0) * 1000)
            err = f"Stooq: {stooq_exc_msg}; yfinance: {yf_exc}"
            log_fetch(db, cache_key, "stooq+yf", cache_hit=False, duration_ms=ms, ok=False, error=err)
            logger.warning("All sources failed for %s", ticker)
            if existing and existing.price is not None:
                return _quote_to_dict(existing, sym, stale=True, stale_reason=stooq_exc_msg or str(yf_exc))
            return {"ticker": sym.ticker, "name": sym.name, "stale": True,
                    "stale_reason": stooq_exc_msg or str(yf_exc)}

    # ── Save to DB ────────────────────────────────────────────────────────────
    try:
        p = _quote_from_bars(bars, sym.ticker, sym.name)
        sym.last_seen_at = now
        if resolved_suffix and sym.exchange != resolved_suffix:
            sym.exchange = resolved_suffix

        qdata = {k: p[k] for k in ("price", "change_abs", "change_pct", "open", "high", "low", "volume")}
        if existing:
            for k, v in qdata.items():
                setattr(existing, k, v)
            existing.ts = now
            existing.stale = False
            existing.source = source
        else:
            existing = Quote(symbol_id=sym.id, ts=now, source=source, stale=False, **qdata)
            db.add(existing)
        db.commit()

        ms = int((time.perf_counter() - t0) * 1000)
        log_fetch(db, cache_key, source, cache_hit=False, duration_ms=ms, ok=True)
        return _quote_to_dict(existing, sym)
    except Exception as exc:
        ms = int((time.perf_counter() - t0) * 1000)
        log_fetch(db, cache_key, source, cache_hit=False, duration_ms=ms, ok=False, error=str(exc))
        logger.warning("Quote save failed %s: %s", ticker, exc)
        if existing and existing.price is not None:
            return _quote_to_dict(existing, sym, stale=True, stale_reason=str(exc))
        return {"ticker": sym.ticker, "name": sym.name, "stale": True, "stale_reason": str(exc)}


def _quote_to_dict(q: Quote, sym: Symbol, stale: bool = False, stale_reason: str = None) -> dict:
    return {
        "ticker": sym.ticker, "name": sym.name,
        "price": q.price, "change_abs": q.change_abs, "change_pct": q.change_pct,
        "open": q.open, "high": q.high, "low": q.low, "volume": q.volume,
        "currency": sym.currency, "ts": _dt_str(q.ts),
        "stale": stale or q.stale, "stale_reason": stale_reason,
    }


# ── History ───────────────────────────────────────────────────────────────────

def get_history(ticker: str, db: Session, period: str = "1y", interval: str = "1d",
                force_refresh: bool = False) -> dict:
    period   = period   if period   in settings.ALLOWED_PERIODS   else "1y"
    interval = interval if interval in settings.ALLOWED_INTERVALS else "1d"

    sym = get_or_create_symbol(ticker, db)
    cache_key = f"history:{sym.ticker}:{period}:{interval}"

    last_ok = (
        db.query(FetchLog)
        .filter(FetchLog.key == cache_key, FetchLog.ok == True, FetchLog.cache_hit == False)
        .order_by(FetchLog.fetched_at.desc())
        .first()
    )
    now = datetime.utcnow()
    cached_bars = (
        db.query(History)
        .filter(History.symbol_id == sym.id, History.period == period, History.interval == interval)
        .order_by(History.ts)
        .all()
    )

    if not force_refresh and last_ok and cached_bars:
        if (now - last_ok.fetched_at).total_seconds() < settings.HISTORY_TTL:
            log_fetch(db, cache_key, "cache", cache_hit=True)
            return _hist_dict(sym.ticker, period, interval, cached_bars, last_ok.fetched_at)

    t0 = time.perf_counter()
    since = _period_start(period)
    bars_raw = None
    source = "stooq"
    stooq_exc_msg = None

    # ── Try Stooq ─────────────────────────────────────────────────────────────
    try:
        stooq_int = _stooq_interval(interval)
        stooq_t, bars_raw = _resolve_stooq_ticker(sym.ticker, sym.exchange, since, stooq_int)
        new_suffix = stooq_t[len(sym.ticker.lower()):]
        if sym.exchange != new_suffix:
            sym.exchange = new_suffix
            db.commit()
        if not bars_raw:
            raise ValueError("Empty history")
    except Exception as exc:
        stooq_exc_msg = str(exc)
        logger.debug("Stooq history failed for %s: %s — trying yfinance", ticker, exc)

    # ── yfinance fallback ─────────────────────────────────────────────────────
    if bars_raw is None:
        try:
            stooq_t = _stooq_ticker(sym.ticker)
            yf_t = _to_yf_ticker(stooq_t)
            bars_raw = _yfinance_bars(yf_t, since)
            source = "yfinance"
            logger.info("yfinance history OK for %s (as %s)", ticker, yf_t)
        except Exception as yf_exc:
            ms = int((time.perf_counter() - t0) * 1000)
            err = f"Stooq: {stooq_exc_msg}; yfinance: {yf_exc}"
            log_fetch(db, cache_key, "stooq+yf", cache_hit=False, duration_ms=ms, ok=False, error=err)
            logger.warning("History all sources failed %s", ticker)
            if cached_bars:
                return _hist_dict(sym.ticker, period, interval, cached_bars,
                                  last_ok.fetched_at if last_ok else None,
                                  stale=True, stale_reason=stooq_exc_msg)
            return {"ticker": sym.ticker, "period": period, "interval": interval,
                    "data": [], "stale": True, "stale_reason": stooq_exc_msg or str(yf_exc)}

    # ── Save to DB ────────────────────────────────────────────────────────────
    try:
        db.query(History).filter(
            History.symbol_id == sym.id,
            History.period == period, History.interval == interval,
        ).delete()
        db.bulk_save_objects([
            History(symbol_id=sym.id, period=period, interval=interval,
                    ts=b["ts"], open=b["open"], high=b["high"],
                    low=b["low"], close=b["close"], volume=b["volume"],
                    source=source)
            for b in bars_raw
        ])
        db.commit()

        ms = int((time.perf_counter() - t0) * 1000)
        log_fetch(db, cache_key, source, cache_hit=False, duration_ms=ms, ok=True)

        saved = (
            db.query(History)
            .filter(History.symbol_id == sym.id, History.period == period, History.interval == interval)
            .order_by(History.ts).all()
        )
        return _hist_dict(sym.ticker, period, interval, saved, now)
    except Exception as exc:
        ms = int((time.perf_counter() - t0) * 1000)
        log_fetch(db, cache_key, source, cache_hit=False, duration_ms=ms, ok=False, error=str(exc))
        logger.warning("History save failed %s: %s", ticker, exc)
        if cached_bars:
            return _hist_dict(sym.ticker, period, interval, cached_bars,
                              last_ok.fetched_at if last_ok else None,
                              stale=True, stale_reason=str(exc))
        return {"ticker": sym.ticker, "period": period, "interval": interval,
                "data": [], "stale": True, "stale_reason": str(exc)}


def _hist_dict(ticker, period, interval, bars, fetched_at, stale=False, stale_reason=None) -> dict:
    return {
        "ticker": ticker, "period": period, "interval": interval,
        "data": [
            {"ts": b.ts.isoformat(), "open": b.open, "high": b.high,
             "low": b.low, "close": b.close, "volume": b.volume}
            for b in bars
        ],
        "stale": stale, "stale_reason": stale_reason,
        "fetched_at": fetched_at.isoformat() if fetched_at else None,
    }


# ── Period returns (from DB cache only, no network calls) ─────────────────────

def _period_return_from_history(ticker: str, days_ago: int, current_price, db: Session):
    """Return % change over `days_ago` using cached history bars. Returns None if no data."""
    if not current_price:
        return None
    sym = db.query(Symbol).filter(Symbol.ticker == ticker.upper()).first()
    if not sym:
        return None
    target_date = datetime.utcnow() - timedelta(days=days_ago)
    bar = (
        db.query(History)
        .filter(History.symbol_id == sym.id, History.ts <= target_date)
        .order_by(History.ts.desc())
        .first()
    )
    if bar and bar.close:
        return round((current_price - bar.close) / bar.close * 100, 2)
    return None


# ── Markets overview ──────────────────────────────────────────────────────────

def get_markets_overview(db: Session) -> list[dict]:
    results = []
    for ticker in settings.INDICES:
        q = get_quote(ticker, db)
        q["name"] = settings.INDEX_NAMES.get(ticker, q.get("name", ticker))
        price = q.get("price")
        q["return_1m"] = _period_return_from_history(ticker, 30, price, db)
        q["return_1y"] = _period_return_from_history(ticker, 365, price, db)
        results.append(q)
        time.sleep(0.2)  # gentle rate limiting between indices
    return results


def get_top_stocks_overview(db: Session) -> list[dict]:
    results = []
    for ticker in settings.TOP_STOCKS:
        q = get_quote(ticker, db)
        q["name"] = settings.TOP_STOCK_NAMES.get(ticker, q.get("name", ticker))
        price = q.get("price")
        q["return_1m"] = _period_return_from_history(ticker, 30, price, db)
        q["return_1y"] = _period_return_from_history(ticker, 365, price, db)
        results.append(q)
        time.sleep(0.2)
    return results


def get_watchlist_quotes(user_id: int, db: Session) -> list[dict]:
    from ..models import Watchlist
    wl = db.query(Watchlist).filter(Watchlist.user_id == user_id).first()
    if not wl:
        return []
    quotes = []
    for item in wl.items:
        quotes.append(get_quote(item.symbol.ticker, db))
        time.sleep(0.15)
    return quotes
