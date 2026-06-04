"""Generuje parę kluczy VAPID do Web Push (uruchom raz).

    python generate_vapid.py

Zapisuje klucz prywatny do pliku 'vapid_private.pem' (NIE commituj go) i wypisuje
linie do wklejenia w backend/.env. Używa biblioteki 'cryptography' (zależność pywebpush).
"""

import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def main():
    priv = ec.generate_private_key(ec.SECP256R1())

    # Klucz prywatny -> plik PEM (pywebpush przyjmuje ścieżkę do PEM).
    with open("vapid_private.pem", "wb") as f:
        f.write(
            priv.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )

    # Klucz publiczny -> nieskompresowany punkt P-256 w base64url (applicationServerKey).
    pub_raw = priv.public_key().public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint,
    )

    print("Zapisano klucz prywatny do: vapid_private.pem (NIE commituj!)\n")
    print("Wklej do backend/.env:")
    print(f"VAPID_PUBLIC_KEY={b64url(pub_raw)}")
    print("VAPID_PRIVATE_KEY=vapid_private.pem")
    print("VAPID_SUBJECT=mailto:admin@twojadomena.pl")


if __name__ == "__main__":
    main()
