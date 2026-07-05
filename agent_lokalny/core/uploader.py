"""Wysyłka do chmury Lokalo: token agenta w X-RCP-Token, timeouty, czytelne błędy."""

import requests


class Uploader:
    def __init__(self, url_bazy: str, token: str, timeout: int = 25):
        self.url_bazy = url_bazy.rstrip("/")
        self.naglowki = {"X-RCP-Token": token}
        self.timeout = timeout

    def wyslij(self, sciezka: str, payload: dict) -> dict:
        r = requests.post(f"{self.url_bazy}{sciezka}", json=payload,
                          headers=self.naglowki, timeout=self.timeout)
        r.raise_for_status()
        return r.json() if r.content else {}
