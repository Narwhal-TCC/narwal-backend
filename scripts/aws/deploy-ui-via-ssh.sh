#!/usr/bin/env bash
# GitHub Actions / local: sync UI from S3 on EC2 over SSH (after frontend uploads to s3://bucket/ui/).

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
EC2_HOST="${EC2_HOST:?EC2_HOST is required}"
APP_BUCKET_NAME="${APP_BUCKET_NAME:?APP_BUCKET_NAME is required}"
UI_S3_PREFIX="${UI_S3_PREFIX:-ui}"
EC2_SSH_USER="${EC2_SSH_USER:-ubuntu}"

if [[ -z "${EC2_SSH_PRIVATE_KEY:-}" && -z "${EC2_SSH_KEY_FILE:-}" ]]; then
  echo "Set EC2_SSH_PRIVATE_KEY or EC2_SSH_KEY_FILE" >&2
  exit 1
fi

KEY_FILE="${EC2_SSH_KEY_FILE:-}"
TMP_KEY=""
if [[ -z "${KEY_FILE}" ]]; then
  TMP_KEY="$(mktemp)"
  printf '%s\n' "${EC2_SSH_PRIVATE_KEY}" > "${TMP_KEY}"
  chmod 600 "${TMP_KEY}"
  KEY_FILE="${TMP_KEY}"
fi
cleanup() { [[ -n "${TMP_KEY}" ]] && rm -f "${TMP_KEY}"; }
trap cleanup EXIT

mkdir -p "${HOME}/.ssh"
ssh-keyscan -H "${EC2_HOST}" >> "${HOME}/.ssh/known_hosts" 2>/dev/null || true

SCP=(scp -i "${KEY_FILE}" -o StrictHostKeyChecking=accept-new)
SSH=(ssh -i "${KEY_FILE}" -o StrictHostKeyChecking=accept-new "${EC2_SSH_USER}@${EC2_HOST}")

"${SCP[@]}" "${ROOT}/scripts/aws/remote-sync-ui.sh" "${EC2_SSH_USER}@${EC2_HOST}:/tmp/narwal-remote-sync-ui.sh"
"${SSH[@]}" "APP_BUCKET_NAME=${APP_BUCKET_NAME} UI_S3_PREFIX=${UI_S3_PREFIX} bash /tmp/narwal-remote-sync-ui.sh"

echo "UI sync over SSH finished on ${EC2_HOST}"
