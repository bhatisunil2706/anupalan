#!/bin/bash
# Every start of the Codespace: wait for Docker, start the app, and show how to open it.
cd "$(dirname "$0")/.."
for i in $(seq 1 30); do docker info >/dev/null 2>&1 && break; sleep 2; done
./start.sh
URL=$(grep -E '^PUBLIC_URL=' .env | cut -d= -f2)
if [ -n "$CODESPACE_NAME" ] && [ -n "$DEMO_PASSWORD" ]; then
  # A demo password of your own is set, so it's safe to let people without a GitHub login open the link.
  gh codespace ports visibility 3000:public -c "$CODESPACE_NAME" >/dev/null 2>&1 \
    && echo "Port 3000 is public: anyone with the link can open the sign-in page." \
    || echo "Couldn't make port 3000 public automatically; use the Ports tab (right-click 3000 > Port Visibility > Public)."
fi
echo
echo "Open: $URL"
