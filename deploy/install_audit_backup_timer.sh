#!/bin/bash
# Install the daily audit backup timer. Review it, then run it yourself:
#   sudo bash install_audit_backup_timer.sh OUTBOX_USER
# OUTBOX_USER is the account that copies the latest backup off the host. Runs one backup at once to
# prove it works. Running it again replaces the script and units.
set -euo pipefail

[ "$(id -u)" -eq 0 ] || { echo "Run with sudo." >&2; exit 1; }
[ $# -eq 1 ] && id "$1" >/dev/null 2>&1 || { echo "Usage: sudo bash $0 OUTBOX_USER" >&2; exit 1; }
OUTBOX_USER=$1
HERE=$(cd "$(dirname "$0")" && pwd)

# A copy outside the repository, so pulling a new commit cannot change what root runs.
install -o root -g root -m 0755 "$HERE/audit_backup.sh" /usr/local/sbin/stram-qual-audit-backup

cat > /etc/systemd/system/stram-qual-audit-backup.service <<EOF
[Unit]
Description=Stram Qualitative MCP audit backup

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/stram-qual-audit-backup $OUTBOX_USER
EOF

cat > /etc/systemd/system/stram-qual-audit-backup.timer <<'EOF'
[Unit]
Description=Daily Stram Qualitative MCP audit backup

[Timer]
OnCalendar=*-*-* 04:45:00
RandomizedDelaySec=10m
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now stram-qual-audit-backup.timer
systemctl start stram-qual-audit-backup.service
journalctl -u stram-qual-audit-backup.service -n 3 --no-pager -o cat
systemctl list-timers stram-qual-audit-backup.timer --no-pager | sed -n 1,2p
