#!/bin/sh
# Daily encrypted backups of the database and evidence store (evidence files are already encrypted per company).
# Restore: gpg --decrypt db-*.sql.gz.gpg | gunzip | psql ...   (see docs/operations.md)
set -eu
apk add --no-cache gnupg >/dev/null 2>&1 || true
umask 077
printf '%s' "$BACKUP_PASSPHRASE" > /tmp/backup.pass   # keeps the passphrase out of the process list
unset BACKUP_PASSPHRASE
while true; do
  ts=$(date -u +%Y%m%dT%H%M%SZ)
  pg_dump --format=plain --no-owner | gzip | gpg --batch --yes --symmetric --cipher-algo AES256 \
    --passphrase-file /tmp/backup.pass -o "/backups/db-$ts.sql.gz.gpg"
  tar -C /evidence -czf - . | gpg --batch --yes --symmetric --cipher-algo AES256 \
    --passphrase-file /tmp/backup.pass -o "/backups/evidence-$ts.tar.gz.gpg"
  find /backups -name '*.gpg' -mtime +"${BACKUP_KEEP_DAYS:-30}" -delete
  echo "backup $ts done"
  sleep 86400
done
