#!/bin/bash
# Daily online backup of the audit journal, run as root by stram-qual-audit-backup.timer.
#   bash audit_backup.sh [OUTBOX_USER]
# The service keeps running: SQLite's backup API copies a consistent snapshot, and the copy is then
# verified on its own against the key. Backups, checkpoints and the key go to BACKUP_DIR (root only)
# and are kept for KEEP_DAYS. The latest set is also placed in OUTBOX for OUTBOX_USER to copy off the
# host. Prints the checkpoint, never the key.
set -euo pipefail

SERVICE_USER=stram-qual
BACKUP_DIR=/var/backups/stram-qual
OUTBOX=/var/backups/stram-qual-outbox
KEEP_DAYS=30
OUTBOX_USER=${1:-}

[ "$(id -u)" -eq 0 ] || { echo "Run as root." >&2; exit 1; }
SERVICE_UID=$(id -u "$SERVICE_USER")
SERVICE_HOME=$(getent passwd "$SERVICE_USER" | cut -d: -f6)
QUADLET="$SERVICE_HOME/.config/containers/systemd/stram-qual-mcp.container"
# Use the image the service runs, so the backup's reader always matches the journal's writer.
IMAGE=$(sed -n 's/^Image=//p' "$QUADLET")
STAMP=$(date -u +%Y%m%dT%H%M%SZ)

as_service() {
  (cd / && runuser -u "$SERVICE_USER" -- env XDG_RUNTIME_DIR="/run/user/$SERVICE_UID" "$@")
}

STAGE=$(runuser -u "$SERVICE_USER" -- mktemp -d "$SERVICE_HOME/.audit-backup.XXXXXX")
trap 'rm -rf "$STAGE"' EXIT
as_service podman unshare chown 10001:10001 "$STAGE"
CHECKPOINT=$(as_service podman run --rm --read-only --network none \
  --volume stram-qual-audit:/audit --volume "$STAGE:/backup" \
  --secret stram-qual-audit-key,type=mount,target=audit-key,uid=10001,gid=10001,mode=0400 \
  --entrypoint /opt/venv/bin/python "$IMAGE" \
  -m stram_qualitative_mcp.audit backup --db /audit/audit.sqlite3 \
  --key-file /run/secrets/audit-key --output /backup/audit.sqlite3)

install -d -o root -g root -m 0700 "$BACKUP_DIR"
install -o root -g root -m 0400 "$STAGE/audit.sqlite3" "$BACKUP_DIR/audit-$STAMP.sqlite3"
printf '%s\n' "$CHECKPOINT" > "$BACKUP_DIR/checkpoint-$STAMP.json"
chmod 0400 "$BACKUP_DIR/checkpoint-$STAMP.json"
# One copy of the key is enough while it is unchanged; a rotated key gets its own dated file.
KEY_FILE="$BACKUP_DIR/audit-key"
NEW_KEY="$STAGE/audit-key"
as_service podman secret inspect --showsecret --format '{{.SecretData}}' stram-qual-audit-key > "$NEW_KEY"
if [ -f "$KEY_FILE" ] && ! cmp -s "$KEY_FILE" "$NEW_KEY"; then
  mv "$KEY_FILE" "$BACKUP_DIR/audit-key-replaced-$STAMP"
fi
[ -f "$KEY_FILE" ] || install -o root -g root -m 0400 "$NEW_KEY" "$KEY_FILE"

find "$BACKUP_DIR" -maxdepth 1 -type f \
  \( -name 'audit-2*' -o -name 'checkpoint-2*' -o -name 'audit-key-2*' \) \
  -mtime +"$KEEP_DAYS" -delete

if [ -n "$OUTBOX_USER" ]; then
  install -d -o "$OUTBOX_USER" -g "$OUTBOX_USER" -m 0700 "$OUTBOX"
  find "$OUTBOX" -mindepth 1 -maxdepth 1 -type f -delete
  for name in "audit-$STAMP.sqlite3" "checkpoint-$STAMP.json" audit-key; do
    install -o "$OUTBOX_USER" -g "$OUTBOX_USER" -m 0400 "$BACKUP_DIR/$name" "$OUTBOX/$name"
  done
fi
echo "audit backup $STAMP verified: $CHECKPOINT"
