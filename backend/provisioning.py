"""Samoobsługowy provisioning instancji (feedback: „wszystko zautomatyzowane,
bez ingerencji operatora"). Instancja-matka na żądanie z publicznego kreatora:

  1. provisionuje nową instancję skryptem new_client.py (świeże sekrety, własna
     baza SQLite w instances/<slug>/, --init --bez-admina → zero kont),
  2. uruchamia ją jako osobny proces uvicorn na wolnym porcie (współdzieli
     zbudowany frontend przez FRONTEND_DIST),
  3. czeka na /api/health i oddaje URL — klient trafia na ŚWIEŻĄ instancję,
     gdzie kreator (onboarding) zakłada mu konto właściciela.

Rejestr floty: instances/registry.json (slug, nazwa, port, pid, url, e-mail).
Bezpieczeństwo: całość za bramką PROVISIONING_ENABLED=1 (świadoma decyzja
operatora), dzienny limit per IP + twardy limit wielkości floty.

Model docelowy (produkcja): ten sam interfejs, driver dockerowy zamiast
subprocess + subdomeny za reverse proxy. Lokalne porty = tryb dev/desktop.
"""

from __future__ import annotations

import json
import logging
import os
import re
import socket
import subprocess
import sys
import time
import unicodedata
import urllib.request
from pathlib import Path

from deps import utcnow_naive
from new_client import waliduj_slug

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parent
INSTANCES_DIR = BACKEND_DIR / "instances"
REGISTRY = INSTANCES_DIR / "registry.json"
FRONTEND_DIST = (BACKEND_DIR.parent / "frontend" / "dist").resolve()

PORT_OD, PORT_DO = 8100, 8199
HEALTH_TIMEOUT_S = 25
LIMIT_FLOTY = int(os.getenv("PROVISIONING_MAX_INSTANCJI", "20"))


def wlaczony() -> bool:
    """Provisioning wymaga świadomej zgody operatora (env na instancji-matce)."""
    return os.getenv("PROVISIONING_ENABLED", "").strip().lower() in ("1", "true", "tak")


# ── Rejestr floty ─────────────────────────────────────────────────────────────

def wczytaj_rejestr() -> list[dict]:
    if not REGISTRY.exists():
        return []
    try:
        return json.loads(REGISTRY.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("Uszkodzony registry.json — traktuję jak pusty.")
        return []


def zapisz_rejestr(rejestr: list[dict]) -> None:
    INSTANCES_DIR.mkdir(parents=True, exist_ok=True)
    REGISTRY.write_text(json.dumps(rejestr, ensure_ascii=False, indent=2), encoding="utf-8")


def _pid_zyje(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        if os.name == "nt":
            wynik = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                capture_output=True, text=True, timeout=10)
            return str(pid) in wynik.stdout
        os.kill(pid, 0)
        return True
    except (OSError, subprocess.SubprocessError):
        return False


# ── Slug i port ───────────────────────────────────────────────────────────────

def slug_z_nazwy(nazwa: str, zajete: set[str]) -> str:
    """Slug z nazwy lokalu (ascii, myślniki) + przyrostek liczbowy przy kolizji."""
    # NFKD nie rozkłada polskiego ł/Ł (litera bez dekompozycji) — transliterujemy jawnie.
    s = (nazwa or "").replace("ł", "l").replace("Ł", "L")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:32] or "lokal"
    if len(s) < 3:
        s = f"{s}-lokal"[:32].strip("-")
    baza, i = s, 1
    while s in zajete:
        i += 1
        s = f"{baza[:28]}-{i}"
    return waliduj_slug(s)


def _port_wolny(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        return sock.connect_ex(("127.0.0.1", port)) != 0


def przydziel_port(rejestr: list[dict]) -> int:
    zajete = {w.get("port") for w in rejestr}
    for port in range(PORT_OD, PORT_DO + 1):
        if port not in zajete and _port_wolny(port):
            return port
    raise RuntimeError("Brak wolnych portów w puli floty.")


# ── Cykl życia instancji ──────────────────────────────────────────────────────

def _env_instancji(katalog: Path, port: int) -> dict:
    """Środowisko procesu instancji: jej .env + współdzielony frontend."""
    env = dict(os.environ)
    # Wyczyść zmienne matki, które nadpisałyby konfigurację instancji:
    for k in ("DATABASE_URL", "SECRET_KEY", "RCP_INGEST_TOKEN", "CORS_ORIGINS", "PROVISIONING_ENABLED"):
        env.pop(k, None)
    for linia in (katalog / ".env").read_text(encoding="utf-8").splitlines():
        linia = linia.strip()
        if linia and not linia.startswith("#") and "=" in linia:
            k, _, v = linia.partition("=")
            env[k.strip()] = v.strip()
    env["FRONTEND_DIST"] = str(FRONTEND_DIST)
    env["PORT"] = str(port)
    return env


def uruchom_instancje(slug: str, port: int) -> int:
    """Startuje proces uvicorn instancji; zwraca PID. Log w instances/<slug>/uvicorn.log."""
    katalog = INSTANCES_DIR / slug
    log = open(katalog / "uvicorn.log", "ab")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=str(BACKEND_DIR),
        env=_env_instancji(katalog, port),
        stdout=log, stderr=subprocess.STDOUT,
        creationflags=subprocess.DETACHED_PROCESS if os.name == "nt" else 0,  # przeżywa restart matki
    )
    return proc.pid


def _czekaj_na_health(port: int, timeout_s: int = HEALTH_TIMEOUT_S) -> bool:
    koniec = time.monotonic() + timeout_s
    url = f"http://127.0.0.1:{port}/api/health"
    while time.monotonic() < koniec:
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                if r.status == 200:
                    return True
        except OSError:
            pass
        time.sleep(0.5)
    return False


def utworz_instancje(nazwa: str, email: str | None = None, host: str = "127.0.0.1",
                     tier: str | None = None, admin_email: str | None = None,
                     admin_haslo_hash: str | None = None, konfiguracja: dict | None = None,
                     trial: bool = False, karta_token: str | None = None,
                     karta_ostatnie4: str | None = None) -> dict:
    """Pełny tor samoobsługi: provisioning → start → health → wpis w rejestrze.
    Zwraca wpis rejestru (z URL). Podnosi RuntimeError z czytelnym komunikatem.

    Gdy podano `admin_email` + `admin_haslo_hash` (tor z checkoutu): instancja powstaje OD RAZU
    z kontem właściciela i aktywną, opłaconą subskrypcją — właściciel trafia na `?login` i loguje
    się e-mailem. Bez nich — stary tor `--bez-admina` (kreator zakłada konto w instancji, `?start`).
    Hasło NIGDY nie idzie w argv (widoczne w tasklist) — przekazujemy bcrypt przez env podprocesu."""
    rejestr = wczytaj_rejestr()
    if len(rejestr) >= LIMIT_FLOTY:
        raise RuntimeError("Osiągnięto limit liczby instancji — skontaktuj się z operatorem.")

    slug = slug_z_nazwy(nazwa, {w["slug"] for w in rejestr})
    port = przydziel_port(rejestr)
    z_adminem = bool(admin_email and admin_haslo_hash)

    # 1) Provisioning (osobny proces — new_client sam ustawia środowisko init bazy).
    polecenie = [sys.executable, str(BACKEND_DIR / "new_client.py"), slug,
                 "--nazwa", nazwa or slug, "--init"]
    env = None
    if z_adminem:
        polecenie += ["--email", admin_email]
        env = {**os.environ, "LOKALO_ADMIN_HASLO_HASH": admin_haslo_hash}  # hash poza argv
        if trial:
            polecenie += ["--trial"]   # 14 dni pełnego dostępu; po trialu auto-obciążenie planu
            # Token metody płatności poza argv (jak hash) — instancja obciąży ją po 14 dniach.
            if karta_token:
                env["LOKALO_KARTA_TOKEN"] = karta_token
            if karta_ostatnie4:
                env["LOKALO_KARTA_OSTATNIE4"] = karta_ostatnie4
        if konfiguracja:
            env["LOKALO_CONFIG_JSON"] = json.dumps(konfiguracja)  # typ+moduły z kreatora
    else:
        polecenie += ["--bez-admina"]
    if tier:
        polecenie += ["--tier", tier]   # pakiet z cennika od razu w subskrypcji instancji
    wynik = subprocess.run(polecenie, cwd=str(BACKEND_DIR), capture_output=True, text=True,
                           timeout=180, env=env)
    if wynik.returncode != 0:
        logger.error("Provisioning %s nie powiódł się: %s", slug, wynik.stderr[-800:])
        raise RuntimeError("Nie udało się przygotować instancji — spróbuj ponownie.")

    # 2) Start + health.
    pid = uruchom_instancje(slug, port)
    if not _czekaj_na_health(port):
        logger.error("Instancja %s (port %s, pid %s) nie odpowiedziała na health.", slug, port, pid)
        raise RuntimeError("Instancja nie wystartowała w oczekiwanym czasie — spróbuj ponownie.")

    wpis = {
        "slug": slug,
        "nazwa": nazwa or slug,
        "email": (admin_email or email or "").strip() or None,
        "tier": tier,
        "port": port,
        "pid": pid,
        "url": f"http://{host}:{port}/?{'login' if z_adminem else 'start'}",
        "utworzono_at": utcnow_naive().isoformat(),
    }
    rejestr.append(wpis)
    zapisz_rejestr(rejestr)
    logger.info("Flota: nowa instancja %s na porcie %s (pid %s).", slug, port, pid)
    return wpis


def status_floty() -> list[dict]:
    """Rejestr + stan życia procesów (zalążek panelu floty)."""
    out = []
    for w in wczytaj_rejestr():
        out.append({**w, "dziala": _pid_zyje(w.get("pid")) and not _port_wolny(w["port"])})
    return out


def _fleet_token() -> str:
    return os.getenv("FLEET_TOKEN", "")


def puls_instancji(port: int, token: str, timeout_s: float = 1.5) -> dict | None:
    """Pobiera podsumowanie żywej instancji (subskrypcja/użytkownicy) przez /api/instancja/puls.
    Zwraca dict albo None (instancja nie odpowiada / brak tokenu). Best-effort."""
    if not token:
        return None
    req = urllib.request.Request(f"http://127.0.0.1:{port}/api/instancja/puls",
                                headers={"X-Fleet-Token": token})
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as r:
            if r.status == 200:
                return json.loads(r.read().decode("utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    return None


def flota_z_pulsem() -> dict:
    """Panel operatora: instancje floty + ŻYWY stan subskrypcji (odpytanie dzieci równolegle).
    Gdy FLEET_TOKEN nieustawiony — sam rejestr + zdrowie procesu (bez subskrypcji)."""
    from concurrent.futures import ThreadPoolExecutor

    instancje = status_floty()
    token = _fleet_token()
    if token and instancje:
        with ThreadPoolExecutor(max_workers=min(8, len(instancje))) as ex:
            pulsy = list(ex.map(lambda w: puls_instancji(w["port"], token), instancje))
        for w, p in zip(instancje, pulsy):
            w["puls"] = p   # None gdy instancja nie odpowiedziała

    # Podsumowanie: liczniki wg pakietu i statusu (tylko z żywych pulsów; fallback = tier z rejestru).
    wg_pakietu, wg_statusu = {}, {}
    aktywne = 0
    for w in instancje:
        p = w.get("puls") or {}
        tier = p.get("tier") or w.get("tier") or "—"
        wg_pakietu[tier] = wg_pakietu.get(tier, 0) + 1
        if p:
            wg_statusu[p.get("status", "—")] = wg_statusu.get(p.get("status", "—"), 0) + 1
            if p.get("aktywna"):
                aktywne += 1
    return {
        "enabled": wlaczony(),
        "puls_dostepny": bool(token),
        "limit": LIMIT_FLOTY,
        "podsumowanie": {"instancji": len(instancje), "aktywnych": aktywne,
                         "wg_pakietu": wg_pakietu, "wg_statusu": wg_statusu},
        "instancje": instancje,
    }


def wskrzes_flote() -> int:
    """Best-effort przy starcie matki: podnosi instancje z rejestru, których proces nie żyje.
    Zwraca liczbę wskrzeszonych. Wołane ze startup hooka, gdy provisioning włączony."""
    ile = 0
    rejestr = wczytaj_rejestr()
    for w in rejestr:
        try:
            if _pid_zyje(w.get("pid")) or not _port_wolny(w["port"]):
                continue   # żyje albo port zajęty (już działa pod innym pid)
            w["pid"] = uruchom_instancje(w["slug"], w["port"])
            ile += 1
        except OSError as e:
            logger.warning("Nie wskrzeszono instancji %s: %s", w.get("slug"), e)
    if ile:
        zapisz_rejestr(rejestr)
        logger.info("Flota: wskrzeszono %s instancji.", ile)
    return ile
