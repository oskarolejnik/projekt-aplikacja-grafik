"""Konfiguracja połączenia z SQLite."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Base

DATABASE_URL = "sqlite:///./scheduler.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},  # wymagane dla SQLite + FastAPI
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """Generator sesji — używany jako FastAPI Dependency."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Tworzy tabele jeśli nie istnieją."""
    Base.metadata.create_all(bind=engine)
