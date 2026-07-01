"""Punkt wejścia SPAKOWANEGO backendu (PyInstaller) — uruchamia serwer FastAPI/uvicorn tak,
aby aplikacja desktopowa (Electron) nie wymagała Pythona na komputerze klienta.

Konfigurację (DATABASE_URL, SECRET_KEY, FRONTEND_DIST, port) podaje powłoka desktopowa przez
zmienne środowiskowe. Schemat bazy buduje/aktualizuje init_db() w zdarzeniu startup (Alembic
upgrade head, z migracjami dołączonymi do bundla — patrz grafik-backend.spec).
"""

import argparse
import os


def main():
    parser = argparse.ArgumentParser(description="Grafik Pracy — serwer backendu (desktop)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=int(os.environ.get("GRAFIK_PORT", "8799")))
    args, _ = parser.parse_known_args()

    os.environ.setdefault("APP_ENV", "desktop")
    import uvicorn
    from main import app   # import: walidacja sekretów; startup event: init_db()
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
