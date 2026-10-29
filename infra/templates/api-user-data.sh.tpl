#!/bin/bash
set -euo pipefail
exec > /var/log/narwal-user-data.log 2>&1

export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y docker.io nginx awscli curl xfsprogs

systemctl enable --now docker
usermod -aG docker ubuntu || true

mkdir -p /var/www/narwal
chown -R www-data:www-data /var/www/narwal

if [[ -d /etc/nginx/sites-available ]]; then
  cat > /etc/nginx/sites-available/narwal.conf <<'NGINX_EOF'
${nginx_conf}
NGINX_EOF
  rm -f /etc/nginx/sites-enabled/default
  ln -sf /etc/nginx/sites-available/narwal.conf /etc/nginx/sites-enabled/narwal.conf
else
  cat > /etc/nginx/conf.d/narwal.conf <<'NGINX_EOF'
${nginx_conf}
NGINX_EOF
fi

cat > /var/www/narwal/index.html <<'HTML_EOF'
<!doctype html><html><head><title>Narwal</title></head><body><p>Narwal UI not deployed yet.</p></body></html>
HTML_EOF
chown www-data:www-data /var/www/narwal/index.html

nginx -t
systemctl enable --now nginx

cat > /tmp/narwal-mount-data.sh <<'MOUNT_EOF'
${mount_data_script}
MOUNT_EOF
chmod +x /tmp/narwal-mount-data.sh
bash /tmp/narwal-mount-data.sh /data

export AWS_REGION="${aws_region}"
export ECR_REPOSITORY_URL="${ecr_repository_url}"
export IMAGE_TAG="latest"
export NARWAL_ENV_FILE="/etc/narwal/env"

ECR_REGISTRY="$${ECR_REPOSITORY_URL%%/*}"
aws ecr get-login-password --region "$${AWS_REGION}" | docker login --username AWS --password-stdin "$${ECR_REGISTRY}"

IMAGE="$${ECR_REPOSITORY_URL}:$${IMAGE_TAG}"
docker pull "$${IMAGE}" || true

if docker ps -a --format '{{.Names}}' | grep -qx narwal-api; then
  docker stop narwal-api || true
  docker rm narwal-api || true
fi

ENV_ARGS=()
if [[ -f "$${NARWAL_ENV_FILE}" ]]; then
  ENV_ARGS=(--env-file "$${NARWAL_ENV_FILE}")
fi

docker run -d --name narwal-api --restart unless-stopped \
  -p 127.0.0.1:8080:8080 \
  -v /data:/data \
  "$${ENV_ARGS[@]}" \
  "$${IMAGE}" || echo "Container start deferred until $${NARWAL_ENV_FILE} exists"
