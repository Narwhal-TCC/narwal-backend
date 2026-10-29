#!/usr/bin/env bash
# Install/start Nginx edge (UI + /api/* proxy). Idempotent — used in user-data and SSH deploy.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DOCROOT="/var/www/narwal"
NGINX_SITE="/etc/nginx/sites-available/narwal.conf"
NGINX_ENABLED="/etc/nginx/sites-enabled/narwal.conf"
NGINX_DROPIN="/etc/nginx/conf.d/narwal.conf"

web_user() {
  if getent passwd www-data >/dev/null 2>&1; then
    echo www-data
  else
    echo nginx
  fi
}

install_packages() {
  if command -v apt-get >/dev/null 2>&1; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -y
    apt-get install -y nginx awscli curl
    return
  fi
  if command -v dnf >/dev/null 2>&1; then
    dnf install -y nginx aws-cli curl
    return
  fi
  echo "Unsupported OS for ensure-nginx-edge.sh" >&2
  exit 1
}

if ! command -v nginx >/dev/null 2>&1; then
  install_packages
fi

mkdir -p "${DOCROOT}"
OWNER="$(web_user)"
chown -R "${OWNER}:${OWNER}" "${DOCROOT}"

if [[ ! -f "${DOCROOT}/index.html" ]]; then
  cat > "${DOCROOT}/index.html" <<'HTML'
<!doctype html><html><head><title>Narwal</title></head><body><p>Narwal UI not deployed yet.</p></body></html>
HTML
  chown "${OWNER}:${OWNER}" "${DOCROOT}/index.html"
fi

install -m 644 "${SCRIPT_DIR}/narwal-nginx.conf" "${NGINX_DROPIN}"

if [[ -d /etc/nginx/sites-available ]]; then
  install -m 644 "${SCRIPT_DIR}/narwal-nginx.conf" "${NGINX_SITE}"
  rm -f /etc/nginx/sites-enabled/default
  ln -sf "${NGINX_SITE}" "${NGINX_ENABLED}"
fi

nginx -t
systemctl enable nginx
systemctl restart nginx

echo "Nginx edge listening on :80 (docroot ${DOCROOT}, owner ${OWNER})"
