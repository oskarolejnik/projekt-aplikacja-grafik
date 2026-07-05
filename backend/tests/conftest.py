"""Konfiguracja pytest: izolowana baza testowa + klient HTTP + uwierzytelnianie.

Strategia:
  • Backend używa importów absolutnych (`import models`), więc dorzucamy katalog
    `backend/` do sys.path.
  • Przed importem aplikacji ustawiamy DATABASE_URL na SQLite, żeby start aplikacji
    nie próbował łączyć się z Postgresem.
  • Tworzymy JEDEN współdzielony silnik SQLite in-memory (StaticPool) i podpinamy go
    wszędzie: do aplikacji (database.engine/SessionLocal), do zależności get_db
    (dependency_overrides) oraz do fabryk (factories.Session).
  • Schemat jest odtwarzany przed każdym testem (pełna izolacja).
  • Powiadomienia push są mockowane (zero ruchu sieciowego/VAPID).
"""

import os
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

# Musi być ustawione PRZED importem `database`/`main` (czytają env przy imporcie).
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("TOKEN_TTL_MINUTES", "720")
# WYMUSZAMY (override, nie setdefault): testy ingestu hardkodują nagłówek
# X-RCP-Token="test-rcp-token", więc token w środowisku (np. RCP_INGEST_TOKEN ustawiony
# w CI) NIE MOŻE go nadpisywać — inaczej ingest jest odrzucany i testy padają tylko w CI.
os.environ["RCP_INGEST_TOKEN"] = "test-rcp-token"
os.environ["DATABASE_URL"] = "sqlite://"

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

import database  # noqa: E402
import models  # noqa: E402

# Jeden współdzielony silnik in-memory na cały proces testowy.
engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

# Podmiana globalnego silnika/sesji aplikacji (init_db, ewentualne SessionLocal()).
database.engine = engine
database.SessionLocal = TestSessionLocal

import main  # noqa: E402  (po podmianie silnika)
import factories  # noqa: E402
from auth import create_access_token  # noqa: E402
from database import get_db  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

# Fabryki korzystają z tego samego silnika (osobna sesja, ta sama baza).
factories.Session.configure(bind=engine)


def _override_get_db():
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


main.app.dependency_overrides[get_db] = _override_get_db


# ─────────────────────────────────────────────────────────────────────────────
# Cykl życia danych
# ─────────────────────────────────────────────────────────────────────────────
@pytest.fixture(autouse=True)
def _reset_schema():
    """Czysta baza przed każdym testem."""
    models.Base.metadata.drop_all(bind=engine)
    models.Base.metadata.create_all(bind=engine)
    yield
    factories.Session.remove()


@pytest.fixture(autouse=True)
def _mock_push(monkeypatch):
    """Publikacja grafiku wysyła push — w testach zwracamy 0 (bez sieci)."""
    monkeypatch.setattr(main, "wyslij_push", lambda *a, **k: 0)


@pytest.fixture(autouse=True)
def _reset_ratelimit():
    """Limiter logowania trzyma stan w pamięci procesu — zeruj przed każdym testem (izolacja)."""
    import ratelimit
    ratelimit.reset()
    yield


@pytest.fixture(autouse=True)
def _bez_provisioningu(monkeypatch):
    """Hermetyzacja: deweloperski backend/.env (load_dotenv) może mieć PROVISIONING_ENABLED=1 —
    testy zakładają default WYŁĄCZONY; testy floty włączają flagę jawnie u siebie."""
    monkeypatch.delenv("PROVISIONING_ENABLED", raising=False)


@pytest.fixture(autouse=True)
def _otwarta_rejestracja(_reset_schema):
    """Produkcyjny default to rejestracja TYLKO z zaproszenia (rejestracja_otwarta=False).
    Duża część istniejących testów zakłada konta przez POST /api/auth/register — włączamy
    flagę w konfiguracji testowej bazy (PO utworzeniu schematu — stąd zależność).
    Testy zaproszeń wyłączają ją jawnie u siebie."""
    from deps import get_lokal_config
    s = TestSessionLocal()
    try:
        cfg = get_lokal_config(s)
        cfg.rejestracja_otwarta = True
        s.commit()
    finally:
        s.close()
    yield


@pytest.fixture
def db():
    """Bezpośrednia sesja do asercji na bazie (ta sama baza co aplikacja)."""
    s = TestSessionLocal()
    try:
        yield s
    finally:
        s.close()


# ─────────────────────────────────────────────────────────────────────────────
# HTTP + uwierzytelnianie
# ─────────────────────────────────────────────────────────────────────────────
@pytest.fixture
def client():
    """Klient bez tokenu (np. do testów logowania i ochrony tras)."""
    with TestClient(main.app) as c:
        yield c


def auth_header(user):
    return {"Authorization": f"Bearer {create_access_token(user)}"}


@pytest.fixture
def admin():
    """Konto administratora (rola=admin, bez powiązanego pracownika)."""
    return factories.UserFactory(login="admin_test", rola="admin", pracownik=None)


@pytest.fixture
def admin_client(client, admin):
    client.headers.update(auth_header(admin))
    return client


@pytest.fixture
def make_employee_client(client):
    """Fabryka klientów pracownika: make_employee_client(pracownik) -> (client, user)."""

    def _make(pracownik, login=None):
        user = factories.UserFactory(
            login=login or f"prac{pracownik.id}",
            rola="employee",
            pracownik=pracownik,
        )
        c = TestClient(main.app)
        c.headers.update(auth_header(user))
        return c, user

    return _make


@pytest.fixture
def company():
    """Gotowa „firma": stanowiska + 15+ pracowników z profilami i kwalifikacjami."""
    return factories.build_company()
