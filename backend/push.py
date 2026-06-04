"""Wysyłka powiadomień Web Push (VAPID + pywebpush).

Konfiguracja przez zmienne środowiskowe (.env):
  VAPID_PUBLIC_KEY   - klucz publiczny (base64url) — używany też przez przeglądarkę
  VAPID_PRIVATE_KEY  - ścieżka do pliku PEM z kluczem prywatnym (lub sam klucz)
  VAPID_SUBJECT      - mailto:... kontakt administratora
Klucze generuje skrypt: python generate_vapid.py
"""

import os
import json

from dotenv import load_dotenv

load_dotenv()

import models

VAPID_PUBLIC_KEY = os.environ.get("VAPID_PUBLIC_KEY", "")
VAPID_PRIVATE_KEY = os.environ.get("VAPID_PRIVATE_KEY", "")
VAPID_SUBJECT = os.environ.get("VAPID_SUBJECT", "mailto:admin@example.com")


def push_skonfigurowany() -> bool:
    return bool(VAPID_PUBLIC_KEY and VAPID_PRIVATE_KEY)


def wyslij_push(db, tytul: str, tresc: str, url: str = "/") -> int:
    """Wysyła powiadomienie do wszystkich zapisanych subskrypcji.
    Wygasłe subskrypcje (404/410) kasuje. Zwraca liczbę wysłanych.
    Import pywebpush jest leniwy, by brak biblioteki nie psuł całej aplikacji."""
    if not push_skonfigurowany():
        print("[PUSH] Pominięto — brak kluczy VAPID (ustaw VAPID_PUBLIC_KEY/VAPID_PRIVATE_KEY).")
        return 0
    try:
        from pywebpush import webpush, WebPushException
    except ImportError:
        print("[PUSH] Brak biblioteki pywebpush — pomijam wysyłkę.")
        return 0

    payload = json.dumps({"title": tytul, "body": tresc, "url": url})
    wyslano = 0
    for sub in list(db.query(models.PushSubscription).all()):
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
            print("[PUSH] błąd wysyłki:", e)
    db.commit()
    return wyslano
