#!/bin/sh
# One-time EC2 / Linux host setup for SQLite on a persistent mount.
# The API container runs as uid 1001 (appuser). Run as root on the instance.
set -e

DATA_DIR="${1:-/data}"

mkdir -p "$DATA_DIR"
chown 1001:1001 "$DATA_DIR"
chmod 750 "$DATA_DIR"

printf 'Prepared %s for SQLITE_PATH=%s/narwal.db (owner uid 1001)\n' "$DATA_DIR" "$DATA_DIR"
