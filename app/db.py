import logging
from contextlib import contextmanager

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from .config import settings

logger = logging.getLogger(__name__)

engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False},
    pool_pre_ping=True,
    echo=False,
)


@event.listens_for(engine, "connect")
def _configure_sqlite(dbapi_connection, _connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA cache_size=-64000")
    cursor.close()


SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI dependency: yields a DB session and closes it after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def get_db_ctx():
    """Context-manager version for use outside FastAPI (background tasks, etc.)."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables and seed default data."""
    from . import models  # noqa: F401 – registers models with Base
    Base.metadata.create_all(bind=engine)
    _seed_users()


def _seed_users():
    from .models import User, UserSettings
    from .auth import hash_password

    with get_db_ctx() as db:
        if db.query(User).count() == 0:
            logger.info("Seeding default users …")
            for username, password, role in [
                ("admin", "admin", "admin"),
                ("demo", "demo", "user"),
            ]:
                u = User(username=username, password_hash=hash_password(password), role=role)
                db.add(u)
                db.flush()
                db.add(UserSettings(user_id=u.id))
            db.commit()
            logger.info("Default users created: admin/admin, demo/demo")
