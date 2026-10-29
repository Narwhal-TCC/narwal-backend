#!/usr/bin/env bash
# On EC2: sync UI from S3 staging prefix to Nginx docroot (run via ssh-ec2.sh or locally on instance).

set -euo pipefail

APP_BUCKET_NAME="${APP_BUCKET_NAME:?APP_BUCKET_NAME is required}"
UI_S3_PREFIX="${UI_S3_PREFIX:-ui}"
DOCROOT="${DOCROOT:-/var/www/narwal}"

sudo mkdir -p "${DOCROOT}"
sudo aws s3 sync "s3://${APP_BUCKET_NAME}/${UI_S3_PREFIX}/" "${DOCROOT}/" --delete
sudo chown -R nginx:nginx "${DOCROOT}"
sudo systemctl reload nginx

echo "UI synced from s3://${APP_BUCKET_NAME}/${UI_S3_PREFIX}/ to ${DOCROOT}"
