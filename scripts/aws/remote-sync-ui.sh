#!/usr/bin/env bash
# On EC2: sync UI from S3 staging prefix to Nginx docroot (run via ssh-ec2.sh or locally on instance).

set -euo pipefail

APP_BUCKET_NAME="${APP_BUCKET_NAME:?APP_BUCKET_NAME is required}"
UI_S3_PREFIX="${UI_S3_PREFIX:-ui}"
DOCROOT="${DOCROOT:-/var/www/narwal}"

WEB_USER=www-data
if ! getent passwd www-data >/dev/null 2>&1; then
  WEB_USER=nginx
fi

sudo mkdir -p "${DOCROOT}"
sudo aws s3 sync "s3://${APP_BUCKET_NAME}/${UI_S3_PREFIX}/" "${DOCROOT}/" --delete
# sync skips same-size files; index.html keeps its size when only asset hashes change.
sudo aws s3 cp "s3://${APP_BUCKET_NAME}/${UI_S3_PREFIX}/index.html" "${DOCROOT}/index.html"
sudo chown -R "${WEB_USER}:${WEB_USER}" "${DOCROOT}"
sudo systemctl reload nginx

echo "UI synced from s3://${APP_BUCKET_NAME}/${UI_S3_PREFIX}/ to ${DOCROOT}"
