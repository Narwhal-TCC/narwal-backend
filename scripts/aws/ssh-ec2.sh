#!/usr/bin/env bash
# Run a command on the Narwal API EC2 host over SSH (Learner Lab — SSM often blocked).
#
# Required:
#   EC2_HOST              — Elastic IP (terraform output api_public_ip)
#   EC2_SSH_PRIVATE_KEY   — PEM private key (GitHub secret or path in EC2_SSH_KEY_FILE)
#
# Optional:
#   EC2_SSH_USER          — default ec2-user
#   EC2_SSH_KEY_FILE      — if set, read key from this path instead of EC2_SSH_PRIVATE_KEY

set -euo pipefail

EC2_SSH_USER="${EC2_SSH_USER:-ec2-user}"

if [[ -z "${EC2_HOST:-}" ]]; then
  echo "EC2_HOST is required" >&2
  exit 1
fi

KEY_FILE="${EC2_SSH_KEY_FILE:-}"
if [[ -z "${KEY_FILE}" ]]; then
  if [[ -z "${EC2_SSH_PRIVATE_KEY:-}" ]]; then
    echo "Set EC2_SSH_PRIVATE_KEY or EC2_SSH_KEY_FILE" >&2
    exit 1
  fi
  KEY_FILE="$(mktemp)"
  trap 'rm -f "${KEY_FILE}"' EXIT
  printf '%s\n' "${EC2_SSH_PRIVATE_KEY}" > "${KEY_FILE}"
  chmod 600 "${KEY_FILE}"
fi

mkdir -p "${HOME}/.ssh"
ssh-keyscan -H "${EC2_HOST}" >> "${HOME}/.ssh/known_hosts" 2>/dev/null || true

exec ssh -i "${KEY_FILE}" -o StrictHostKeyChecking=accept-new \
  "${EC2_SSH_USER}@${EC2_HOST}" "$@"
