#!/bin/bash
# Build and start the app with the latest code, upgrade the database, load demo data once, then open the browser.
set -e
cd "$(dirname "$0")"
if ! docker info >/dev/null 2>&1; then
  echo "Docker isn't running. Open Docker Desktop, wait for it to start, then run ./start.sh again."
  exit 1
fi
PORT=$(grep -E '^WEB_PORT=' .env 2>/dev/null | cut -d= -f2); PORT=${PORT:-3000}
echo "Building..."
docker compose build
echo "Upgrading the database..."
docker compose run --rm migrate
echo "Starting..."
docker compose up -d
echo "Loading demo companies (skipped if already there)..."
# Set DEMO_PASSWORD to use your own password for new demo logins.
DEMO_PASSWORD=${DEMO_PASSWORD:-Demo-Pramaanly-2026!}
docker compose run --rm migrate python -m app.cli seed-demo --password "$DEMO_PASSWORD" 2>/dev/null | head -1 \
  || echo "Demo data already present."
for i in $(seq 1 30); do
  curl -sf "http://localhost:$PORT/login" >/dev/null && break
  sleep 2
done
echo
echo "Ready: http://localhost:$PORT"
if [ "$DEMO_PASSWORD" = "Demo-Pramaanly-2026!" ]; then
  echo "Sign in: priya@paisasetu.example / Demo-Pramaanly-2026!"
else
  echo "Sign in: priya@paisasetu.example with your DEMO_PASSWORD"
fi
open "http://localhost:$PORT" 2>/dev/null || true
