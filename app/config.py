from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    SECRET_KEY: str = "changeme-marketpulse-secret-key-2024"
    SESSION_COOKIE_NAME: str = "mp_session"
    SESSION_MAX_AGE: int = 86400 * 7  # 7 days

    DATABASE_URL: str = f"sqlite:///{BASE_DIR}/mpulse.db"

    LOG_LEVEL: str = "INFO"

    # Cache TTLs (seconds)
    QUOTE_TTL: int = 60
    HISTORY_TTL: int = 900       # 15 minutes
    SYMBOL_METADATA_TTL: int = 604800  # 7 days
    CRYPTO_TTL: int = 60

    # Market data — Stooq tickers
    INDICES: list = ["^SPX", "^NDX", "^DAX", "^UKX", "^CAC"]
    INDEX_NAMES: dict = {
        "^SPX": "S&P 500",
        "^NDX": "NASDAQ-100",
        "^DAX": "DAX",
        "^UKX": "FTSE 100",
        "^CAC": "CAC 40",
    }

    # Rate limiting for login (per IP)
    LOGIN_MAX_ATTEMPTS: int = 5
    LOGIN_WINDOW_SECS: int = 300  # 5 minutes

    # WebSocket broadcast interval
    BROADCAST_INTERVAL: int = 30

    # Allowed history params
    ALLOWED_PERIODS: set = {"1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "ytd", "max"}
    ALLOWED_INTERVALS: set = {"1m", "2m", "5m", "15m", "30m", "60m", "90m", "1h", "1d", "5d", "1wk", "1mo", "3mo"}


settings = Settings()
