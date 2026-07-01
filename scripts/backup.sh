#!/bin/sh
# Kopia zapasowa bazy PostgreSQL instancji (pg_dump) + retencja.
# POSIX sh — działa pod bash, dash i busybox (alpine). Wymaga: pg_dump, gzip, find, date, sed.
#
# Zmienne środowiskowe:
#   DATABASE_URL   postgresql://user:haslo@host:5432/baza   (akceptuje też wariant +psycopg2)
#   BACKUP_DIR     katalog na kopie (domyślnie ./backups)
#   RETENCJA_DNI   usuwaj kopie starsze niż tyle dni (domyślnie 14)
#
# Przykłady:
#   DATABASE_URL="postgresql://grafik:haslo@localhost:5432/grafik" ./scripts/backup.sh
#   docker compose -f docker-compose.prod.yml --profile backup run --rm backup
set -eu

DATABASE_URL="${DATABASE_URL:-}"
BACKUP_DIR="${BACKUP_DIR:-./backups}"
RETENCJA_DNI="${RETENCJA_DNI:-14}"

[ -n "$DATABASE_URL" ] || { echo "Blad: ustaw DATABASE_URL (postgresql://...)." >&2; exit 1; }

# SQLAlchemy używa 'postgresql+psycopg2://', a pg_dump wymaga 'postgresql://'.
URI=$(printf '%s' "$DATABASE_URL" | sed 's/+psycopg2//')

case "$URI" in
  postgresql://*|postgres://*) ;;
  *) echo "Blad: backup obsluguje tylko PostgreSQL (DATABASE_URL=$DATABASE_URL)." >&2; exit 1 ;;
esac

mkdir -p "$BACKUP_DIR"
STAMP=$(date -u +%Y%m%d-%H%M%S)
TMP="$BACKUP_DIR/.grafik-$STAMP.sql"
PLIK="$BACKUP_DIR/grafik-$STAMP.sql.gz"

echo "Backup -> $PLIK"
# Dump do pliku tymczasowego (set -e wychwyci błąd pg_dump), potem kompresja — bez zależności od pipefail.
pg_dump --format=plain --no-owner --no-privileges "$URI" > "$TMP"
gzip -9 < "$TMP" > "$PLIK"
rm -f "$TMP"
echo "OK: $(du -h "$PLIK" | cut -f1)"

# Retencja: usuń kopie starsze niż RETENCJA_DNI dni.
find "$BACKUP_DIR" -name 'grafik-*.sql.gz' -type f -mtime "+$RETENCJA_DNI" -print -delete || true
echo "Retencja: kopie starsze niz $RETENCJA_DNI dni usuniete."
