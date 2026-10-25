#!/bin/sh
set -e

# Dev-only: Compose bind-mounts ./db; legacy root-owned containers leave root:root files.
# Production (EC2/EBS): prepare the volume once on the host — do not set FIX_DB_PERMISSIONS.
fix_db_dir_permissions() {
  db_dir="$1"
  if [ -z "$db_dir" ] || [ ! -d "$db_dir" ]; then
    return 0
  fi
  if [ "$(id -u)" != "0" ]; then
    return 0
  fi
  chown -R appuser:appgroup "$db_dir"
  chmod -R u+rwX,g+rwX "$db_dir"
}

case "${FIX_DB_PERMISSIONS:-}" in
  1|true|TRUE|yes|YES)
    if [ -n "${SQLITE_PATH:-}" ]; then
      fix_db_dir_permissions "$(dirname "$SQLITE_PATH")"
    elif [ -d /app/db ]; then
      fix_db_dir_permissions /app/db
    fi
    ;;
esac

exec gosu appuser "$@"
