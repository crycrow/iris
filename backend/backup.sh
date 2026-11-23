#!/bin/sh

set -eu
mkdir -p /backups
while true; do
  stamp=$(date -u +%Y%m%dT%H%M%SZ)
  pg_dump -Fc -f "/backups/$stamp.dump.tmp"
  mv "/backups/$stamp.dump.tmp" "/backups/$stamp.dump"
  ls -1t /backups/*.dump | tail -n +$((BACKUP_KEEP + 1)) | while IFS= read -r file; do rm -- "$file"; done
  sleep 86400
done
