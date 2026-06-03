"""Tworzenie / awansowanie konta ADMINISTRATORA bezpośrednio w bazie danych.

Zastępuje dawne automatyczne tworzenie admina z pliku .env. Uruchom na serwerze:
    ../venv/bin/python create_admin.py
albo z loginem w argumencie:
    ../venv/bin/python create_admin.py mojadmin

Hasło podaje się interaktywnie (ukryte w terminalu). Jeśli konto o danym loginie
już istnieje, zostaje awansowane do roli 'admin' i dostaje nowe hasło.
Obowiązują te same reguły loginu/hasła co przy rejestracji.
"""

import sys
import getpass

from fastapi import HTTPException

from database import SessionLocal, init_db
import models
from auth import hash_password
from validators import sprawdz_login, sprawdz_haslo


def main():
    init_db()  # upewnij się, że tabele istnieją

    login = sys.argv[1] if len(sys.argv) > 1 else input("Login administratora: ").strip()
    haslo = getpass.getpass("Hasło: ")
    if haslo != getpass.getpass("Powtórz hasło: "):
        print("Hasła nie są identyczne. Przerwano.")
        sys.exit(1)

    try:
        login = sprawdz_login(login)
        sprawdz_haslo(haslo)
    except HTTPException as e:
        print("Błąd:", e.detail)
        sys.exit(1)

    db = SessionLocal()
    try:
        u = db.query(models.User).filter(models.User.login == login).first()
        if u:
            u.rola, u.aktywny, u.haslo_hash = "admin", True, hash_password(haslo)
            db.commit()
            print(f"Zaktualizowano konto '{login}' -> rola admin.")
        else:
            db.add(models.User(login=login, haslo_hash=hash_password(haslo), rola="admin"))
            db.commit()
            print(f"Utworzono konto administratora '{login}'.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
