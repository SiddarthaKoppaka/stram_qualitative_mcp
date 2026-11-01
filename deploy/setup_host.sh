#!/bin/bash
# One-time host setup for the loopback demonstration (M5). Review it, then run it yourself:
#   sudo bash setup_host.sh NEWS_ROOT IMAGE_TAR JWKS_FILE
# NEWS_ROOT holds parquet/ and bodies/. The raw archive beside them is never mounted.
# Re-running is safe: an existing user, secret or volume is kept.
set -euo pipefail

SERVICE_USER=stram-qual
VIEW=/srv/stram-qual/news
PORT=8801
IMAGE=localhost/stram-qualitative-mcp:m5

[ "$(id -u)" -eq 0 ] || { echo "Run with sudo." >&2; exit 1; }
[ $# -eq 3 ] || { echo "Usage: sudo bash $0 NEWS_ROOT IMAGE_TAR JWKS_FILE" >&2; exit 1; }
NEWS_ROOT=$1
IMAGE_TAR=$2
JWKS_FILE=$3
[ -d "$NEWS_ROOT/parquet" ] && [ -d "$NEWS_ROOT/bodies" ] || { echo "NEWS_ROOT lacks parquet/ or bodies/." >&2; exit 1; }
[ -s "$IMAGE_TAR" ] && [ -s "$JWKS_FILE" ] || { echo "IMAGE_TAR or JWKS_FILE is missing." >&2; exit 1; }

echo "== service user"
if ! id "$SERVICE_USER" >/dev/null 2>&1; then
  useradd --create-home --shell /usr/bin/nologin "$SERVICE_USER"
fi
grep -q "^$SERVICE_USER:" /etc/subuid && grep -q "^$SERVICE_USER:" /etc/subgid \
  || { echo "$SERVICE_USER has no subordinate ID range." >&2; exit 1; }
loginctl enable-linger "$SERVICE_USER"
SERVICE_UID=$(id -u "$SERVICE_USER")
SERVICE_HOME=$(getent passwd "$SERVICE_USER" | cut -d: -f6)
for _ in $(seq 1 20); do [ -d "/run/user/$SERVICE_UID" ] && break; sleep 0.5; done

as_service() {
  (cd / && runuser -u "$SERVICE_USER" -- env XDG_RUNTIME_DIR="/run/user/$SERVICE_UID" "$@")
}

echo "== read-only lake view"
for name in parquet bodies; do
  where="$VIEW/$name"
  install -d -o root -g root -m 0755 "$where"
  unit=$(systemd-escape --path --suffix=mount "$where")
  cat > "/etc/systemd/system/$unit" <<EOF
[Unit]
Description=Stram Qualitative MCP read-only $name

[Mount]
What=$NEWS_ROOT/$name
Where=$where
Type=none
Options=bind,ro,nosuid,nodev,noexec

[Install]
WantedBy=multi-user.target
EOF
  systemctl daemon-reload
  systemctl enable --now "$unit"
  findmnt -M "$where" -n -o OPTIONS | grep -Eq '(^|,)ro(,|$)' \
    || { echo "$where is not read-only." >&2; exit 1; }
done

echo "== image, audit volume and key"
as_service podman load --quiet --input "$IMAGE_TAR"
as_service podman volume exists stram-qual-audit || as_service podman volume create stram-qual-audit
AUDIT_DIR=$(as_service podman volume inspect stram-qual-audit --format '{{.Mountpoint}}')
as_service podman unshare chown 10001:10001 "$AUDIT_DIR"
if ! as_service podman secret exists stram-qual-audit-key; then
  openssl rand -base64 48 | as_service podman secret create stram-qual-audit-key -
fi

echo "== service definitions"
CONFIG="$SERVICE_HOME/.config"
QUADLET="$CONFIG/containers/systemd"
install -d -o "$SERVICE_USER" -g "$SERVICE_USER" -m 0700 "$CONFIG" "$CONFIG/containers" "$QUADLET" "$CONFIG/stram-qual"
install -d -o "$SERVICE_USER" -g "$SERVICE_USER" -m 0755 "$CONFIG/stram-qual/jwks"
install -o "$SERVICE_USER" -g "$SERVICE_USER" -m 0644 "$JWKS_FILE" "$CONFIG/stram-qual/jwks/jwks.json"

cat > "$CONFIG/stram-qual/service.env" <<EOF
STRAM_QUAL_MCP_PARQUET_ROOT=/news/parquet
STRAM_QUAL_MCP_AUDIT_DB=/audit/audit.sqlite3
STRAM_QUAL_MCP_AUDIT_KEY_FILE=/run/secrets/audit-key
STRAM_QUAL_MCP_ISSUER_URL=http://127.0.0.1:$PORT/issuer
STRAM_QUAL_MCP_RESOURCE_URL=http://127.0.0.1:$PORT/mcp
STRAM_QUAL_MCP_JWKS_URL=http://127.0.0.1:8001/jwks.json
STRAM_QUAL_MCP_TENANT_ID=stram
STRAM_QUAL_MCP_ALLOWED_HOSTS=127.0.0.1:$PORT
STRAM_QUAL_MCP_ALLOW_INSECURE_HTTP=1
STRAM_QUAL_MCP_IMAGE_DIGEST=$(as_service podman image inspect "$IMAGE" --format '{{.Digest}}')
EOF
chown "$SERVICE_USER:$SERVICE_USER" "$CONFIG/stram-qual/service.env"
chmod 0600 "$CONFIG/stram-qual/service.env"

cat > "$QUADLET/stram-qual.pod" <<EOF
[Pod]
PodName=stram-qual
PublishPort=127.0.0.1:$PORT:8000
EOF

cat > "$QUADLET/stram-qual-jwks.container" <<EOF
[Unit]
Description=Stram Qualitative MCP demonstration signing keys (public only)

[Container]
Image=$IMAGE
Pod=stram-qual.pod
ReadOnly=true
DropCapability=all
NoNewPrivileges=true
Volume=$CONFIG/stram-qual/jwks:/jwks:ro
Entrypoint=/opt/venv/bin/python
Exec=-m http.server 8001 --bind 127.0.0.1 --directory /jwks

[Service]
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=default.target
EOF

cat > "$QUADLET/stram-qual-mcp.container" <<EOF
[Unit]
Description=Stram Qualitative MCP
After=stram-qual-jwks.service
Requires=stram-qual-jwks.service

[Container]
Image=$IMAGE
Pod=stram-qual.pod
ReadOnly=true
DropCapability=all
NoNewPrivileges=true
EnvironmentFile=$CONFIG/stram-qual/service.env
Volume=$VIEW/parquet:/news/parquet:ro
Volume=$VIEW/bodies:/news/bodies:ro
Volume=stram-qual-audit:/audit:rw,nosuid,nodev,noexec
Secret=stram-qual-audit-key,type=mount,target=audit-key,uid=10001,gid=10001,mode=0400
Tmpfs=/tmp:rw,noexec,nosuid,nodev,size=2g

[Service]
Restart=on-failure
RestartSec=5s
TimeoutStartSec=120
MemoryMax=4G

[Install]
WantedBy=default.target
EOF
chown "$SERVICE_USER:$SERVICE_USER" "$QUADLET"/stram-qual*

echo "== start"
as_service systemctl --user daemon-reload
as_service systemctl --user restart stram-qual-jwks.service stram-qual-mcp.service
sleep 5
as_service systemctl --user --no-pager --lines=0 status stram-qual-mcp.service | sed -n 1,4p
echo "Setup finished. Only 127.0.0.1:$PORT is published."
