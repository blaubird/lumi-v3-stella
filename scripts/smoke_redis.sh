#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-http://localhost:8000}"

response=$(curl -fsSL "$BASE_URL/healthz") || {
  echo "Failed to reach $BASE_URL/healthz" >&2
  exit 1
}

redis_status=$(python - <<'PY'
import json
import sys

try:
    payload = json.loads(sys.stdin.read())
except json.JSONDecodeError:
    print("invalid", end="")
    sys.exit(0)
print(payload.get("redis"), end="")
PY
<<<"$response")

if [[ "$redis_status" != "True" && "$redis_status" != "true" && "$redis_status" != "1" ]]; then
  echo "Redis unhealthy: $response" >&2
  exit 1
fi

echo "$response"
