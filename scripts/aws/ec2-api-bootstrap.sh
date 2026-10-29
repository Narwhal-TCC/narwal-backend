#!/usr/bin/env bash
# Bootstrap Narwal API on EC2: Nginx edge + Docker + ECR pull + container on port 8080.
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

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# User-data runs as root; GitHub Actions deploy SSHs as ubuntu (not in docker group by default).
run_docker() {
  if [[ "$(id -u)" -eq 0 ]] || docker info >/dev/null 2>&1; then
    docker "$@"
  else
    sudo docker "$@"
  fi
}

deploy_user() {
  if getent passwd ubuntu >/dev/null 2>&1; then
    echo ubuntu
  else
    echo ec2-user
  fi
}

AWS_REGION="${AWS_REGION:-us-east-1}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
NARWAL_ENV_FILE="${NARWAL_ENV_FILE:-/etc/narwal/env}"
CONTAINER_NAME="${CONTAINER_NAME:-narwal-api}"
SSH_USER="$(deploy_user)"

if [[ -f "${SCRIPT_DIR}/ensure-nginx-edge.sh" ]]; then
  if [[ "$(id -u)" -eq 0 ]]; then
    bash "${SCRIPT_DIR}/ensure-nginx-edge.sh"
  else
    sudo bash "${SCRIPT_DIR}/ensure-nginx-edge.sh"
  fi
fi

if [[ -f "${SCRIPT_DIR}/mount-data-volume.sh" ]]; then
  if [[ "$(id -u)" -eq 0 ]]; then
    bash "${SCRIPT_DIR}/mount-data-volume.sh" /data
  else
    sudo bash "${SCRIPT_DIR}/mount-data-volume.sh" /data
  fi
fi

if [[ -n "${APP_BUCKET_NAME:-}" ]]; then
  sudo mkdir -p "$(dirname "${NARWAL_ENV_FILE}")"
  if sudo aws s3 cp "s3://${APP_BUCKET_NAME}/config/narwal.env" "${NARWAL_ENV_FILE}" 2>/dev/null; then
    if getent group docker >/dev/null 2>&1; then
      sudo chown root:docker "${NARWAL_ENV_FILE}"
      sudo chmod 640 "${NARWAL_ENV_FILE}"
    else
      sudo chown root:"${SSH_USER}" "${NARWAL_ENV_FILE}"
      sudo chmod 600 "${NARWAL_ENV_FILE}"
    fi
  fi
fi

if [[ -z "${ECR_REPOSITORY_URL:-}" ]]; then
  echo "ECR_REPOSITORY_URL is required" >&2
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "Installing Docker..."
  if command -v apt-get >/dev/null 2>&1; then
    export DEBIAN_FRONTEND=noninteractive
    sudo apt-get update -y
    sudo apt-get install -y docker.io
  else
    sudo dnf install -y docker
  fi
  sudo systemctl enable --now docker
  sudo usermod -aG docker "${SSH_USER}" 2>/dev/null || true
fi

ECR_REGISTRY="${ECR_REPOSITORY_URL%%/*}"
aws ecr get-login-password --region "${AWS_REGION}" \
  | run_docker login --username AWS --password-stdin "${ECR_REGISTRY}"

IMAGE="${ECR_REPOSITORY_URL}:${IMAGE_TAG}"

run_docker pull "${IMAGE}"

if run_docker ps -a --format '{{.Names}}' | grep -qx "${CONTAINER_NAME}"; then
  run_docker stop "${CONTAINER_NAME}" >/dev/null 2>&1 || true
  run_docker rm "${CONTAINER_NAME}" >/dev/null 2>&1 || true
fi

ENV_FILE_ARGS=()
if [[ -f "${NARWAL_ENV_FILE}" ]]; then
  ENV_FILE_ARGS=(--env-file "${NARWAL_ENV_FILE}")
else
  echo "Warning: ${NARWAL_ENV_FILE} not found; container may lack app config" >&2
fi

run_docker run -d \
  --name "${CONTAINER_NAME}" \
  --restart unless-stopped \
  -p 127.0.0.1:8080:8080 \
  -v /data:/data \
  "${ENV_FILE_ARGS[@]}" \
  "${IMAGE}"

if ! curl -sf --max-time 5 http://127.0.0.1/ >/dev/null; then
  echo "Nginx is not responding on http://127.0.0.1/" >&2
  sudo systemctl status nginx --no-pager || true
  exit 1
fi

echo "Started ${CONTAINER_NAME} from ${IMAGE}; Nginx edge OK on :80"
