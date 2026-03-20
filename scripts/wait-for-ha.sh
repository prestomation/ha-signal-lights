#!/usr/bin/env bash
set -euo pipefail
MAX_ATTEMPTS=${1:-60}
echo "Waiting for Home Assistant (up to $((MAX_ATTEMPTS * 2))s)..."
for i in $(seq 1 "$MAX_ATTEMPTS"); do
  code=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8123/api/ 2>/dev/null || true)
  if [ "$code" = "200" ] || [ "$code" = "401" ]; then
    echo "Home Assistant is responding (HTTP $code, attempt $i)"
    exit 0
  fi
  echo "Attempt $i/$MAX_ATTEMPTS - HTTP $code - waiting..."
  sleep 2
done
echo "Home Assistant failed to start within $((MAX_ATTEMPTS * 2))s"
docker compose -f tests/integration/docker-compose.yml logs 2>/dev/null || true
exit 1
