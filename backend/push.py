"""Wysyłka powiadomień Web Push (VAPID + pywebpush).

Konfiguracja przez zmienne środowiskowe (.env):
  VAPID_PUBLIC_KEY   - klucz publiczny (base64url) — używany też przez przeglądarkę
  VAPID_PRIVATE_KEY  - ścieżka do pliku PEM z kluczem prywatnym (lub sam klucz)
  VAPID_SUBJECT      - mailto:... kontakt administratora
Klucze generuje skrypt: python generate_vapid.py
"""

import os
import json
import logging

from dotenv import load_dotenv

load_dotenv()

import models

logger = logging.getLogger(__name__)

VAPID_PUBLIC_KEY = os.environ.get("VAPID_PUBLIC_KEY", "")
VAPID_PRIVATE_KEY = os.environ.get("VAPID_PRIVATE_KEY", "")
VAPID_SUBJECT = os.environ.get("VAPID_SUBJECT", "mailto:admin@example.com")


def push_skonfigurowany() -> bool:
    return bool(VAPID_PUBLIC_KEY and VAPID_PRIVATE_KEY)


def _wyslij_do_subskrypcji(db, subskrypcje, tytul: str, tresc: str, url: str) -> int:
    """Wysyła payload do podanej listy subskrypcji. Kasuje wygasłe (404/410)."""
    if not push_skonfigurowany():
        logger.info("Web Push pominięty — brak kluczy VAPID (VAPID_PUBLIC_KEY/VAPID_PRIVATE_KEY).")
        return 0
    try:
        from pywebpush import webpush, WebPushException
    except ImportError:
        logger.warning("Brak biblioteki pywebpush — pomijam wysyłkę Web Push.")
        return 0

    payload = json.dumps({"title": tytul, "body": tresc, "url": url})
    wyslano = 0
    for sub in list(subskrypcje):
        try:
            webpush(
                subscription_info={
                    "endpoint": sub.endpoint,
                    "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
                },
                data=payload,
                vapid_private_key=VAPID_PRIVATE_KEY,
                vapid_claims={"sub": VAPID_SUBJECT},
            )
            wyslano += 1
        except WebPushException as e:
            code = getattr(getattr(e, "response", None), "status_code", None)
            if code in (404, 410):
                db.delete(sub)  # subskrypcja wygasła — usuwamy
        except Exception as e:  # noqa: BLE001
            logger.warning("Błąd wysyłki Web Push: %s", e)
    db.commit()
    return wyslano


def wyslij_push(db, tytul: str, tresc: str, url: str = "/") -> int:
    """Powiadomienie do WSZYSTKICH subskrypcji (np. publikacja grafiku)."""
    return _wyslij_do_subskrypcji(db, db.query(models.PushSubscription).all(), tytul, tresc, url)


def wyslij_push_do_pracownika(db, pracownik_id: int, tytul: str, tresc: str, url: str = "/") -> int:
    """Powiadomienie tylko do urządzeń konkretnego pracownika (po jego koncie User)."""
    if not pracownik_id:
        return 0
    user = db.query(models.User).filter(models.User.pracownik_id == pracownik_id).first()
    if not user:
        return 0
    subs = db.query(models.PushSubscription).filter(models.PushSubscription.user_id == user.id).all()
    return _wyslij_do_subskrypcji(db, subs, tytul, tresc, url)


def wyslij_push_do_adminow(db, tytul: str, tresc: str, url: str = "/") -> int:
    """Powiadomienie do urządzeń wszystkich administratorów (np. nowe zamówienie sprzątaczki)."""
    ids = [u.id for u in db.query(models.User).filter(models.User.rola == "admin").all()]
    if not ids:
        return 0
    subs = db.query(models.PushSubscription).filter(models.PushSubscription.user_id.in_(ids)).all()
    return _wyslij_do_subskrypcji(db, subs, tytul, tresc, url)
