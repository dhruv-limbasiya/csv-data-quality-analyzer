from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from typing import Generator
from app.config import settings

# In PostgreSQL, pool_pre_ping=True helps detect stale or dropped connections
serverless_pool_options = (
    {"pool_size": 1, "max_overflow": 0, "pool_timeout": 10}
    if settings.is_production
    else {}
)
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=300,
    echo=(settings.ENVIRONMENT == "development"),
    **serverless_pool_options,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """Dependency that yields a database session and ensures it is closed after request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
