# syntax=docker/dockerfile:1
# Obraz produkcyjny: backend FastAPI serwuje API + zbudowany frontend (same-origin).
# Układ katalogów odwzorowuje repo, bo backend serwuje statyki z ../frontend/dist.

# ── Etap 1: build frontendu (Vite) ────────────────────────────────────────────
FROM node:20-alpine AS frontend
WORKDIR /build/frontend
# Najpierw manifesty (lepsze cache warstw zależności).
COPY frontend/package*.json ./
RUN npm ci
# Reszta źródeł frontu i build → /build/frontend/dist
COPY frontend/ ./
RUN npm run build

# ── Etap 2: runtime backendu ──────────────────────────────────────────────────
FROM python:3.11-slim AS runtime
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    APP_ENV=production
WORKDIR /app/backend

# Zależności Pythona (psycopg2-binary/bcrypt/cryptography mają koła — bez kompilatora).
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Kod backendu.
COPY backend/ ./
# Zbudowany frontend tam, gdzie backend go szuka (BASE_DIR/../frontend/dist).
COPY --from=frontend /build/frontend/dist /app/frontend/dist

# Nieuprzywilejowany użytkownik (bezpieczeństwo).
RUN useradd -m -u 10001 grafik && chown -R grafik:grafik /app
USER grafik

EXPOSE 8000
# init_db() na starcie aplikacji wykonuje migracje Alembic (upgrade head) automatycznie.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
