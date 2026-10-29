#!/usr/bin/env bash
# Mount the attached EBS data volume at /data (Ubuntu Nitro: /dev/nvme*n1; Xen: /dev/xvdf).
# Safe to re-run; uses UUID in fstab when formatting a new volume.

set -euo pipefail

MOUNT_POINT="${1:-/data}"
FSTAB_MARKER="narwal-data-ebs"

if mountpoint -q "${MOUNT_POINT}"; then
  exit 0
fi

find_data_device() {
  local candidate
  for candidate in /dev/nvme1n1 /dev/xvdf /dev/sdf; do
    if [[ -b "${candidate}" ]]; then
      readlink -f "${candidate}"
      return 0
    fi
  done
  return 1
}

DATA_DEV=""
for _ in $(seq 1 90); do
  if DATA_DEV="$(find_data_device)"; then
    break
  fi
  sleep 2
done

if [[ -z "${DATA_DEV}" ]]; then
  echo "Data EBS device not found after waiting; skip mount (SQLite may be unavailable)." >&2
  exit 0
fi

if ! blkid "${DATA_DEV}" >/dev/null 2>&1; then
  mkfs -t xfs "${DATA_DEV}"
fi

UUID="$(blkid -s UUID -o value "${DATA_DEV}")"
mkdir -p "${MOUNT_POINT}"

if ! grep -q "${FSTAB_MARKER}" /etc/fstab 2>/dev/null; then
  echo "UUID=${UUID} ${MOUNT_POINT} xfs defaults,nofail 0 2 # ${FSTAB_MARKER}" >> /etc/fstab
fi

mount -a
chown 1001:1001 "${MOUNT_POINT}"
chmod 750 "${MOUNT_POINT}"

echo "Mounted ${DATA_DEV} (UUID=${UUID}) at ${MOUNT_POINT}"
