#!/bin/sh
# Review, then run as the account that owns the News services (no sudo):
#   sh install_compaction_timer.sh PIPELINE_CHECKOUT
# Compaction needs the Parquet sink stopped, so the job stops it and always restarts it.
# Kafka holds new items meanwhile. Old Parquet files stay until someone removes them.
set -eu

[ $# -eq 1 ] || { echo "Usage: sh $0 PIPELINE_CHECKOUT" >&2; exit 1; }
CHECKOUT=$1
[ -x "$CHECKOUT/.venv/bin/stram-news-compact" ] || { echo "stram-news-compact is missing." >&2; exit 1; }
UNITS="$HOME/.config/systemd/user"

cat > "$UNITS/stram-news-compact.service" <<EOF
[Unit]
Description=Stram news Parquet compaction
Conflicts=stram-news-parquet-sink.service
After=stram-news-parquet-sink.service

[Service]
Type=oneshot
WorkingDirectory=$CHECKOUT
EnvironmentFile=$CHECKOUT/.env
ExecStart=$CHECKOUT/.venv/bin/stram-news-compact
ExecStopPost=/usr/bin/systemctl --user start --no-block stram-news-parquet-sink.service
Nice=10
IOSchedulingClass=idle
NoNewPrivileges=true
PrivateTmp=true
EOF

cat > "$UNITS/stram-news-compact.timer" <<EOF
[Unit]
Description=Compact news Parquet every Sunday

[Timer]
OnCalendar=Sun 07:23
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now stram-news-compact.timer
systemctl --user list-timers stram-news-compact.timer --no-legend --all
