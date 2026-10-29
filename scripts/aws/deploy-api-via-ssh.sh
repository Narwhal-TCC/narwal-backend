#!/usr/bin/env bash
# GitHub Actions / local: push bootstrap script and restart API on EC2 over SSH.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
EC2_HOST="${EC2_HOST:?EC2_HOST is required}"
ECR_REPOSITORY_URL="${ECR_REPOSITORY_URL:?ECR_REPOSITORY_URL is required}"
IMAGE_TAG="${IMAGE_TAG:?IMAGE_TAG is required}"
AWS_REGION="${AWS_REGION:-us-east-1}"
APP_BUCKET_NAME="${APP_BUCKET_NAME:-}"

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

SSH=(ssh -i "${KEY_FILE}" -o StrictHostKeyChecking=accept-new "ec2-user@${EC2_HOST}")
SCP=(scp -i "${KEY_FILE}" -o StrictHostKeyChecking=accept-new)

"${SCP[@]}" "${ROOT}/scripts/aws/ec2-api-bootstrap.sh" "ec2-user@${EC2_HOST}:/tmp/narwal-ec2-api-bootstrap.sh"

REMOTE="export AWS_REGION=${AWS_REGION} ECR_REPOSITORY_URL=${ECR_REPOSITORY_URL} IMAGE_TAG=${IMAGE_TAG}"
if [[ -n "${APP_BUCKET_NAME}" ]]; then
  REMOTE="${REMOTE} APP_BUCKET_NAME=${APP_BUCKET_NAME}"
fi
"${SSH[@]}" "${REMOTE}; bash /tmp/narwal-ec2-api-bootstrap.sh"

echo "API deploy over SSH finished on ${EC2_HOST}"
