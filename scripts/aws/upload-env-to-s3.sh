#!/usr/bin/env bash
# Upload a local env file to S3 for EC2 to pull on deploy (not committed).
#
# Usage:
#   ./scripts/aws/upload-env-to-s3.sh path/to/.env.aws.local
#   (uses S3_BUCKET= from the file if APP_BUCKET_NAME is unset)
#
#   APP_BUCKET_NAME=narwal-bucket-20261025 ./scripts/aws/upload-env-to-s3.sh .env.aws.local
#   Git Bash on Windows does not see PowerShell $env:APP_BUCKET_NAME — prefix on the command or rely on S3_BUCKET in the file.
#
# Object key: s3://${APP_BUCKET_NAME}/config/narwal.env
# Backend deploy workflow can pull this to /etc/narwal/env via SSM (see deploy-aws.yml).

set -euo pipefail

ENV_FILE="${1:-}"

if [[ -z "${ENV_FILE}" || ! -f "${ENV_FILE}" ]]; then
  echo "Usage: $0 <env-file>" >&2
  echo "Optional: APP_BUCKET_NAME or APP_S3_BUCKET (else S3_BUCKET= in the env file)." >&2
  exit 1
fi

APP_BUCKET_NAME="${APP_BUCKET_NAME:-${APP_S3_BUCKET:-}}"
if [[ -z "${APP_BUCKET_NAME}" ]]; then
  APP_BUCKET_NAME="$(
    grep -E '^[[:space:]]*S3_BUCKET=' "${ENV_FILE}" | head -1 | cut -d= -f2- | tr -d '\r' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//;s/^["'\''"]//;s/["'\''"]$//'
  )"
fi
if [[ -z "${APP_BUCKET_NAME}" ]]; then
  echo "APP_BUCKET_NAME (or APP_S3_BUCKET, or S3_BUCKET= in ${ENV_FILE}) is required." >&2
  exit 1
fi

DEST="s3://${APP_BUCKET_NAME}/config/narwal.env"
echo "Uploading ${ENV_FILE} → ${DEST} (SSE-S3) ..."
aws s3 cp "${ENV_FILE}" "${DEST}" --sse AES256
echo "Done. Re-run backend deploy (or workflow_dispatch deploy_only) to sync onto EC2."
