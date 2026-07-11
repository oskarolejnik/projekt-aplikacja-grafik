"""CLI jednorazowej rekonsyliacji rezerwacji Google/iCal z tabelą ``terminy``.

Przykłady (koniec zakresu jest wyłączny)::

    python reconcile_rezerwacje.py --source google --start 2026-07-01 \
      --end 2026-10-01 --cutover-date 2026-07-15 \
      --coverage-through 2026-10-01 --report report.json
    python reconcile_rezerwacje.py --source ical --ics export.ics \
      --start 2026-07-01 --end 2026-10-01 --cutover-date 2026-07-15 \
      --coverage-through 2026-10-01 --apply

Dry-run jest trybem domyślnym. Narzędzie nie ujawnia treści wydarzeń ani PII w
raporcie i nie uruchamia endpointów, pushy, SMS-ów ani e-maili.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import date, datetime, time
from pathlib import Path
from typing import Callable, Sequence

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().with_name(".env"), override=False)

from rezerwacje_import import (
    UTC,
    WARSAW,
    NormalizedExternalBatch,
    failed_source_batch,
    normalize_google_events,
    normalize_ical_payload,
    reconcile_reservations,
)


def _boundary(value: str) -> datetime:
    raw = value.strip()
    try:
        if len(raw) == 10:
            return datetime.combine(date.fromisoformat(raw), time.min, tzinfo=WARSAW)
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("oczekiwano daty lub ISO datetime") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=WARSAW)
    return parsed.astimezone(WARSAW)


def _cutover_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("oczekiwano daty YYYY-MM-DD") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Jednorazowa, domyślnie tylko odczytowa rekonsyliacja rezerwacji.",
    )
    parser.add_argument("--source", required=True, choices=("google", "ical"))
    parser.add_argument("--start", required=True, type=_boundary, help="początek zakresu (włącznie)")
    parser.add_argument("--end", required=True, type=_boundary, help="koniec zakresu (wyłącznie)")
    parser.add_argument("--cutover-date", required=True, type=_cutover_date)
    parser.add_argument(
        "--coverage-through",
        required=True,
        type=_boundary,
        help="jawny horyzont kompletności źródła; musi być późniejszy od uruchomienia",
    )
    parser.add_argument("--apply", action="store_true", help="dodaj wyłącznie czyste braki")
    parser.add_argument("--ics", type=Path, help="plik .ics; wymagany dla source=ical")
    parser.add_argument("--report", type=Path, help="opcjonalna ścieżka raportu JSON")
    return parser


def _google_batch(start: datetime, end: datetime) -> NormalizedExternalBatch:
    calendar_id = os.environ.get("GOOGLE_CALENDAR_ID", "").strip()
    if not calendar_id:
        raise RuntimeError("google_calendar_not_configured")
    # Lazy import: dry-run iCal ani import modułu CLI nie wymagają bibliotek Google.
    from rezerwacje import _pobierz_wydarzenia

    events = _pobierz_wydarzenia(start.isoformat(), end.isoformat())
    return normalize_google_events(
        events,
        calendar_id=calendar_id,
        range_start=start,
        range_end=end,
    )


def _ical_batch(path: Path, start: datetime, end: datetime) -> NormalizedExternalBatch:
    payload = path.read_text(encoding="utf-8-sig")
    return normalize_ical_payload(payload, range_start=start, range_end=end)


def _write_report(report: dict, path: Path | None) -> None:
    serialized = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if path is None:
        print(serialized)
        return
    path.write_text(serialized + "\n", encoding="utf-8")


def _cli_error_report(args, error_code: str) -> dict:
    """Stały raport błędu; nie kopiuje komunikatów wyjątków ani parametrów SQL."""

    return {
        "schema_version": 1,
        "cutover_date": args.cutover_date.isoformat(),
        "range": {
            "start": args.start.isoformat(),
            "end": args.end.isoformat(),
            "end_exclusive": True,
        },
        "coverage": {
            "through": args.coverage_through.isoformat(),
            "sufficient": False,
        },
        "source": {"type": args.source, "status": "error"},
        "apply": {
            "requested": bool(args.apply),
            "inserted": 0,
            "status": "error",
            "error_code": error_code,
        },
        "safe_to_cutover": False,
    }


def run(
    argv: Sequence[str] | None = None,
    *,
    session_factory: Callable | None = None,
) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.end.astimezone(UTC) <= args.start.astimezone(UTC):
        parser.error("--end musi być późniejsze niż --start")
    if args.source == "ical" and args.ics is None:
        parser.error("--ics jest wymagane dla --source ical")
    if args.source == "google" and args.ics is not None:
        parser.error("--ics jest dozwolone tylko dla --source ical")
    if args.apply:
        from szyfrowanie import aktywne

        if not aktywne():
            _write_report(_cli_error_report(args, "encryption_key_required"), args.report)
            return 2

    try:
        batch = (
            _google_batch(args.start, args.end)
            if args.source == "google"
            else _ical_batch(args.ics, args.start, args.end)
        )
    except Exception as exc:  # raport zawiera tylko nazwę klasy wyjątku, bez komunikatu/PII
        batch = failed_source_batch(args.source, exc)

    if session_factory is None:
        from database import SessionLocal

        session_factory = SessionLocal
    try:
        db = session_factory()
    except Exception:
        _write_report(_cli_error_report(args, "database_unavailable"), args.report)
        return 2
    try:
        try:
            report = reconcile_reservations(
                db,
                batch=batch,
                range_start=args.start,
                range_end=args.end,
                cutover_date=args.cutover_date,
                coverage_through=args.coverage_through,
                apply=args.apply,
            )
        except Exception:
            try:
                db.rollback()
            except Exception:
                pass
            report = _cli_error_report(args, "reconciliation_failed")
    finally:
        try:
            db.close()
        except Exception:
            pass
    _write_report(report, args.report)
    return (
        0
        if batch.source_status == "ok" and report.get("apply", {}).get("status") == "ok"
        else 2
    )


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
