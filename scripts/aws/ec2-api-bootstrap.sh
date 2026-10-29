#!/usr/bin/env bash
# Bootstrap Narwal API on EC2: Docker + ECR pull + container on port 8080.
#
# Required environment (no secret values committed — set on instance or /etc/narwal/env):
#   AWS_REGION          — e.g. us-east-1
#   ECR_REPOSITORY_URL  — full repo URL from Terraform output ecr_repository_url
#   IMAGE_TAG           — optional, default latest
#   NARWAL_ENV_FILE     — optional, default /etc/narwal/env
#   CONTAINER_NAME      — optional, default narwal-api
#
# Uses the instance IAM profile for ECR login (no hardcoded AWS keys).

set -euo pipefail

AWS_REGION="${AWS_REGION:-us-east-1}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
NARWAL_ENV_FILE="${NARWAL_ENV_FILE:-/etc/narwal/env}"
CONTAINER_NAME="${CONTAINER_NAME:-narwal-api}"

if [[ -n "${APP_BUCKET_NAME:-}" ]]; then
  sudo mkdir -p "$(dirname "${NARWAL_ENV_FILE}")"
  if sudo aws s3 cp "s3://${APP_BUCKET_NAME}/config/narwal.env" "${NARWAL_ENV_FILE}" 2>/dev/null; then
    sudo chmod 600 "${NARWAL_ENV_FILE}"
  fi
fi

if [[ -z "${ECR_REPOSITORY_URL:-}" ]]; then
  echo "ECR_REPOSITORY_URL is required" >&2
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "Installing Docker..."
  dnf install -y docker
  systemctl enable --now docker
fi

ECR_REGISTRY="${ECR_REPOSITORY_URL%%/*}"
aws ecr get-login-password --region "${AWS_REGION}" \
  | docker login --username AWS --password-stdin "${ECR_REGISTRY}"

IMAGE="${ECR_REPOSITORY_URL}:${IMAGE_TAG}"

docker pull "${IMAGE}"

if docker ps -a --format '{{.Names}}' | grep -qx "${CONTAINER_NAME}"; then
  docker stop "${CONTAINER_NAME}" >/dev/null 2>&1 || true
  docker rm "${CONTAINER_NAME}" >/dev/null 2>&1 || true
fi

ENV_FILE_ARGS=()
if [[ -f "${NARWAL_ENV_FILE}" ]]; then
  ENV_FILE_ARGS=(--env-file "${NARWAL_ENV_FILE}")
else
  echo "Warning: ${NARWAL_ENV_FILE} not found; container may lack app config" >&2
fi

docker run -d \
  --name "${CONTAINER_NAME}" \
  --restart unless-stopped \
  -p 127.0.0.1:8080:8080 \
  -v /data:/data \
  "${ENV_FILE_ARGS[@]}" \
  "${IMAGE}"

echo "Started ${CONTAINER_NAME} from ${IMAGE}"
