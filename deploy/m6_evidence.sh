#!/bin/bash
# M6 evidence on the host. Review it, then run it yourself:
#   sudo bash m6_evidence.sh NEWS_ROOT [BACKUP_DIR]
# Checks that the lake cannot be written, that the query worker runs under seccomp and recovers from a
# crash, and backs up, verifies and restores the audit journal into a scratch volume. The service is
# stopped for under a minute for the backup. Nothing else changes. Each check prints PASS or FAIL.
set -uo pipefail

SERVICE_USER=stram-qual
VIEW=/srv/stram-qual/news
PORT=8801
IMAGE=localhost/stram-qualitative-mcp:m5
CONTAINER=systemd-stram-qual-mcp
PROBE=.m6-write-probe

[ "$(id -u)" -eq 0 ] || { echo "Run with sudo." >&2; exit 1; }
[ $# -ge 1 ] || { echo "Usage: sudo bash $0 NEWS_ROOT [BACKUP_DIR]" >&2; exit 1; }
NEWS_ROOT=$1
BACKUP_DIR=${2:-/var/backups/stram-qual}
SERVICE_UID=$(id -u "$SERVICE_USER")
SERVICE_HOME=$(getent passwd "$SERVICE_USER" | cut -d: -f6)
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
FAILED=0

as_service() {
  (cd / && runuser -u "$SERVICE_USER" -- env XDG_RUNTIME_DIR="/run/user/$SERVICE_UID" "$@")
}
pass() { echo "PASS $(date -u +%H:%M:%SZ) $*"; }
fail() { echo "FAIL $(date -u +%H:%M:%SZ) $*"; FAILED=$((FAILED + 1)); }
ready() {
  for _ in $(seq 1 60); do
    curl -s -m 2 "http://127.0.0.1:$PORT/health/ready" | grep -q '"ready"' && return 0
    sleep 1
  done
  return 1
}
worker_pid() {
  as_service podman top "$CONTAINER" hpid,args 2>/dev/null | awk '/multiprocessing/ {print $1; exit}'
}

echo "== lake writes are refused"
for target in "$VIEW/parquet" "$VIEW/bodies" "$NEWS_ROOT/parquet" "$NEWS_ROOT/bodies"; do
  if runuser -u "$SERVICE_USER" -- touch "$target/$PROBE" 2>/dev/null; then
    rm -f "$target/$PROBE"
    fail "service user could write $target"
  else
    pass "service user cannot write $target"
  fi
done
for target in /news/parquet /news/bodies /; do
  if as_service podman exec "$CONTAINER" /opt/venv/bin/python -c \
    "open('${target%/}/$PROBE', 'w')" 2>/dev/null; then
    fail "container could write $target"
  else
    pass "container cannot write $target"
  fi
done

echo "== query worker sandbox"
WORKER=$(worker_pid)
if [ -n "$WORKER" ] && grep -q '^Seccomp:[[:space:]]*2' "/proc/$WORKER/status" \
  && grep -q '^NoNewPrivs:[[:space:]]*1' "/proc/$WORKER/status"; then
  pass "worker runs with a seccomp filter and no new privileges ($(grep -E '^Seccomp_filters' "/proc/$WORKER/status" | tr -s '\t ' ' '))"
else
  fail "worker seccomp or no-new-privileges not found"
fi

echo "== worker crash recovery"
if [ -n "$WORKER" ]; then
  kill -9 "$WORKER"
  sleep 3
  NEW_WORKER=$(worker_pid)
  if [ -n "$NEW_WORKER" ] && [ "$NEW_WORKER" != "$WORKER" ] && ready; then
    pass "worker restarted after being killed, and the service is ready"
  else
    fail "worker did not recover"
  fi
fi

echo "== audit backup, verification and restore drill"
install -d -o root -g root -m 0700 "$BACKUP_DIR"
STAGE=$(runuser -u "$SERVICE_USER" -- mktemp -d "$SERVICE_HOME/.m6-audit.XXXXXX")
verify() {
  as_service podman run --rm --read-only --network none --volume "$1:/audit" \
    --secret stram-qual-audit-key,type=mount,target=audit-key,uid=10001,gid=10001,mode=0400 \
    --entrypoint /opt/venv/bin/python "$IMAGE" \
    -m stram_qualitative_mcp.audit verify --db /audit/audit.sqlite3 --key-file /run/secrets/audit-key
}
as_service systemctl --user stop stram-qual-mcp.service stram-qual-pod.service
if [ "$(as_service systemctl --user show stram-qual-mcp.service -p Result --value)" = success ]; then
  pass "service shut down cleanly"
else
  fail "service shutdown was not clean"
fi
LIVE=$(verify stram-qual-audit) && pass "live journal verifies: $LIVE" || fail "live journal does not verify"
as_service podman volume export stram-qual-audit --output "$STAGE/audit.tar"
as_service podman secret inspect --showsecret --format '{{.SecretData}}' stram-qual-audit-key \
  > "$BACKUP_DIR/audit-key-$STAMP"
as_service systemctl --user start stram-qual-pod.service
as_service systemctl --user start stram-qual-mcp.service
DRILL=stram-qual-audit-drill-$STAMP
as_service podman volume create "$DRILL" >/dev/null
as_service podman volume import "$DRILL" "$STAGE/audit.tar"
RESTORED=$(verify "$DRILL")
if [ -n "$LIVE" ] && [ "$RESTORED" = "$LIVE" ]; then
  pass "restored copy verifies and matches the live journal"
else
  fail "restored copy does not match: $RESTORED"
fi
as_service podman volume rm "$DRILL" >/dev/null
mv "$STAGE/audit.tar" "$BACKUP_DIR/audit-$STAMP.tar"
rmdir "$STAGE"
printf '%s\n' "$LIVE" > "$BACKUP_DIR/checkpoint-$STAMP.json"
chown root:root "$BACKUP_DIR"/*
chmod 0600 "$BACKUP_DIR"/*
echo "     backup, key and checkpoint are in $BACKUP_DIR (root only)"

if ready; then pass "service is ready again"; else fail "service did not become ready"; fi
echo "     image $(as_service podman image inspect "$IMAGE" --format '{{.Id}}')"
echo "$FAILED failed"
