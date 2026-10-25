#!/usr/bin/env bash
# HTTPS smoke checks against the public CloudFront URL (UI + /api/* origin).
#
# Required environment:
#   CLOUDFRONT_URL  — distribution URL, e.g. https://d111111abcdef8.cloudfront.net
#
# Optional (defaults match app/bootstrap/seed.py and SEED_DEMO_* in .env.example):
#   SMOKE_USERNAME  — default demo
#   SMOKE_PASSWORD  — default demo
#
# Demo credentials come from startup seed (SEED_DEMO_USERNAME / SEED_DEMO_PASSWORD on EC2).

set -euo pipefail

if [[ -z "${CLOUDFRONT_URL:-}" ]]; then
  echo "CLOUDFRONT_URL is required (e.g. https://d123.cloudfront.net)" >&2
  exit 1
fi

BASE="${CLOUDFRONT_URL%/}"
SMOKE_USERNAME="${SMOKE_USERNAME:-demo}"
SMOKE_PASSWORD="${SMOKE_PASSWORD:-demo}"

echo "Checking ${BASE}/api/health ..."
health_code="$(curl -sS -o /tmp/narwal-smoke-health.json -w '%{http_code}' "${BASE}/api/health" || true)"
if [[ "${health_code}" != "200" ]]; then
  echo "Health check failed: HTTP ${health_code}" >&2
  cat /tmp/narwal-smoke-health.json >&2 || true
  echo "If the UI loads but /api fails, start the EC2 instance and ensure the API container is running." >&2
  exit 1
fi

echo "Checking ${BASE}/api/auth/login ..."
login_code="$(curl -sS -o /tmp/narwal-smoke-login.json -w '%{http_code}' \
  -X POST "${BASE}/api/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"username\":\"${SMOKE_USERNAME}\",\"password\":\"${SMOKE_PASSWORD}\"}" || true)"
if [[ "${login_code}" != "200" ]]; then
  echo "Login smoke failed: HTTP ${login_code}" >&2
  cat /tmp/narwal-smoke-login.json >&2 || true
  exit 1
fi

if ! grep -q '"access_token"' /tmp/narwal-smoke-login.json; then
  echo "Login response missing access_token" >&2
  cat /tmp/narwal-smoke-login.json >&2
  exit 1
fi

echo "CloudFront smoke checks passed."
