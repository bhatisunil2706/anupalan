#!/bin/bash
# First start of a Codespace: write .env with this Codespace's public address and freshly generated secrets.
set -e
cd "$(dirname "$0")/.."
if [ -f .env ]; then
  echo ".env already exists; leaving it unchanged."
  exit 0
fi
URL="http://localhost:3000"
SECURE=false
if [ -n "$CODESPACE_NAME" ]; then
  URL="https://${CODESPACE_NAME}-3000.${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN:-app.github.dev}"
  SECURE=true
fi
rand() { openssl rand -base64 "$1" | tr '+/' '-_' | tr -d '\n'; }
cat > .env <<ENV
# Written by .devcontainer/setup.sh for this Codespace. Demo use only.
ENVIRONMENT=development
WEB_PORT=3000
PUBLIC_URL=$URL
COOKIE_SECURE=$SECURE
POSTGRES_PASSWORD=$(rand 24)
RUNTIME_DB_PASSWORD=$(rand 24)
SECRET_KEY=$(rand 48)
ENCRYPTION_KEY=$(rand 32)
LOG_FORMAT=plain
ENV
chmod 600 .env
echo "Wrote .env for $URL"
