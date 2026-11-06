from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from config.settings import settings

# pool_recycle stops MySQL's idle timeout from killing pooled connections.
engine = create_engine(settings.database_url, pool_pre_ping=True, pool_recycle=3600)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def init_db():
    """Create any missing tables."""
    import models.metrics  # noqa: F401  (registers the tables on Base)

    Base.metadata.create_all(bind=engine)


def get_db():
    """FastAPI dependency that provides a session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
