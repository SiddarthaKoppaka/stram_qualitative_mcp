#!/bin/bash
# Host setup for the service. Review it, then run it yourself:
#   sudo bash setup_host.sh NEWS_ROOT IMAGE_TAR demo JWKS_FILE      loopback demonstration (M5)
#   sudo bash setup_host.sh NEWS_ROOT IMAGE_TAR staging AUTH_FILE   Keycloak staging (M6)
# NEWS_ROOT holds parquet/ and bodies/. The raw archive beside them is never mounted.
# AUTH_FILE holds the settings in staging.env.example. Running it again is safe, and switches mode:
# an existing user, secret or volume is kept. IMAGE names the image inside IMAGE_TAR; to deploy
# another release, such as a rollback, run it as: sudo env IMAGE=localhost/...:TAG bash setup_host.sh ...
set -euo pipefail

SERVICE_USER=stram-qual
VIEW=/srv/stram-qual/news
PORT=8801
IMAGE=${IMAGE:-localhost/stram-qualitative-mcp:m7}

[ "$(id -u)" -eq 0 ] || { echo "Run with sudo." >&2; exit 1; }
[ $# -eq 4 ] && { [ "$3" = demo ] || [ "$3" = staging ]; } \
  || { echo "Usage: sudo bash $0 NEWS_ROOT IMAGE_TAR demo JWKS_FILE|staging AUTH_FILE" >&2; exit 1; }
NEWS_ROOT=$1
IMAGE_TAR=$2
MODE=$3
MODE_FILE=$4
[ -d "$NEWS_ROOT/parquet" ] && [ -d "$NEWS_ROOT/bodies" ] || { echo "NEWS_ROOT lacks parquet/ or bodies/." >&2; exit 1; }
[ -s "$IMAGE_TAR" ] && [ -s "$MODE_FILE" ] || { echo "IMAGE_TAR or $MODE_FILE is missing." >&2; exit 1; }

if [ "$MODE" = staging ]; then
  setting() {
    local value
    value=$(sed -n "s/^$1=//p" "$MODE_FILE" | tail -n 1)
    [[ "$value" =~ ^$2$ ]] || { echo "$1 in $MODE_FILE is missing or invalid." >&2; exit 1; }
    printf '%s' "$value"
  }
  PUBLIC_HOST=$(setting STRAM_QUAL_PUBLIC_HOST '[a-z0-9.-]+')
  PUBLIC_PORT=$(setting STRAM_QUAL_PUBLIC_PORT '[0-9]{2,5}')
  HOST_IPV4=$(setting STRAM_QUAL_HOST_IPV4 '[0-9]{1,3}(\.[0-9]{1,3}){3}')
  ISSUER_URL=$(setting STRAM_QUAL_ISSUER_URL 'https://[A-Za-z0-9.:-]+/realms/[A-Za-z0-9_-]+')
  TENANT_ID=$(setting STRAM_QUAL_TENANT_ID '[A-Za-z0-9_.:-]+')
  NETLOC=$PUBLIC_HOST
  [ "$PUBLIC_PORT" = 443 ] || NETLOC="$PUBLIC_HOST:$PUBLIC_PORT"
fi

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
  # A mounted view is read-only, so only prepare the folder before its first mount.
  mountpoint -q "$where" || install -d -o root -g root -m 0755 "$where"
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

if [ "$MODE" = staging ]; then
  echo "== Keycloak check from inside a container"
  # Fails before anything is restarted if the container cannot trust the issuer or its metadata drifted.
  as_service podman run --rm -i --pull=never --read-only --cap-drop=all --security-opt=no-new-privileges \
    --add-host "$PUBLIC_HOST:$HOST_IPV4" --entrypoint /opt/venv/bin/python "$IMAGE" - "$ISSUER_URL" <<'PY'
import json, ssl, sys, urllib.request
issuer = sys.argv[1]
url = issuer + "/.well-known/openid-configuration"
with urllib.request.urlopen(url, timeout=10, context=ssl.create_default_context()) as response:
    value = json.load(response)
if value.get("issuer") != issuer or value.get("jwks_uri") != issuer + "/protocol/openid-connect/certs":
    raise SystemExit("Keycloak issuer or JWKS address does not match.")
print("Keycloak reachable from the container, with a trusted certificate.")
PY
fi

echo "== service definitions"
CONFIG="$SERVICE_HOME/.config"
QUADLET="$CONFIG/containers/systemd"
install -d -o "$SERVICE_USER" -g "$SERVICE_USER" -m 0700 "$CONFIG" "$CONFIG/containers" "$QUADLET" "$CONFIG/stram-qual"

if [ "$MODE" = demo ]; then
  install -d -o "$SERVICE_USER" -g "$SERVICE_USER" -m 0755 "$CONFIG/stram-qual/jwks"
  install -o "$SERVICE_USER" -g "$SERVICE_USER" -m 0644 "$MODE_FILE" "$CONFIG/stram-qual/jwks/jwks.json"
  AUTH_SETTINGS="STRAM_QUAL_MCP_ISSUER_URL=http://127.0.0.1:$PORT/issuer
STRAM_QUAL_MCP_RESOURCE_URL=http://127.0.0.1:$PORT/mcp
STRAM_QUAL_MCP_JWKS_URL=http://127.0.0.1:8001/jwks.json
STRAM_QUAL_MCP_TENANT_ID=stram
STRAM_QUAL_MCP_ALLOWED_HOSTS=127.0.0.1:$PORT
STRAM_QUAL_MCP_ALLOW_INSECURE_HTTP=1"
  POD_EXTRA=
  MCP_UNIT_EXTRA="After=stram-qual-jwks.service
Requires=stram-qual-jwks.service"
else
  AUTH_SETTINGS="STRAM_QUAL_MCP_ISSUER_URL=$ISSUER_URL
STRAM_QUAL_MCP_RESOURCE_URL=https://$NETLOC/mcp
STRAM_QUAL_MCP_JWKS_URL=$ISSUER_URL/protocol/openid-connect/certs
STRAM_QUAL_MCP_TENANT_ID=$TENANT_ID
STRAM_QUAL_MCP_ALLOWED_HOSTS=$NETLOC"
  # The tailnet name must reach this host's own Tailscale address from inside the pod.
  POD_EXTRA="AddHost=$PUBLIC_HOST:$HOST_IPV4"
  MCP_UNIT_EXTRA=
fi

cat > "$CONFIG/stram-qual/service.env" <<EOF
STRAM_QUAL_MCP_PARQUET_ROOT=/news/parquet
STRAM_QUAL_MCP_AUDIT_DB=/audit/audit.sqlite3
STRAM_QUAL_MCP_AUDIT_KEY_FILE=/run/secrets/audit-key
$AUTH_SETTINGS
STRAM_QUAL_MCP_IMAGE_DIGEST=$(as_service podman image inspect "$IMAGE" --format '{{.Digest}}')
EOF
chown "$SERVICE_USER:$SERVICE_USER" "$CONFIG/stram-qual/service.env"
chmod 0600 "$CONFIG/stram-qual/service.env"

cat > "$QUADLET/stram-qual.pod" <<EOF
[Pod]
PodName=stram-qual
PublishPort=127.0.0.1:$PORT:8000
$POD_EXTRA
EOF

# The demonstration key server runs only in demo mode.
rm -f "$QUADLET/stram-qual-jwks.container"
[ "$MODE" = demo ] && cat > "$QUADLET/stram-qual-jwks.container" <<EOF
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
$MCP_UNIT_EXTRA

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
MemoryMax=5G

[Install]
WantedBy=default.target
EOF
chown "$SERVICE_USER:$SERVICE_USER" "$QUADLET"/stram-qual*

echo "== start"
as_service systemctl --user daemon-reload
# Stopping a container takes the pod down with it, so stop everything and start from the pod.
# After a switch to staging the key server's unit is gone, so stop it only if it still runs.
if as_service systemctl --user is-active --quiet stram-qual-jwks.service; then
  as_service systemctl --user stop stram-qual-jwks.service
fi
as_service systemctl --user stop stram-qual-mcp.service stram-qual-pod.service
as_service systemctl --user start stram-qual-pod.service
if [ "$MODE" = demo ]; then
  as_service systemctl --user start stram-qual-jwks.service
fi
as_service systemctl --user start stram-qual-mcp.service
sleep 5
as_service systemctl --user --no-pager --lines=0 status stram-qual-mcp.service | sed -n 1,4p
echo "Setup finished in $MODE mode. Only 127.0.0.1:$PORT is published."
if [ "$MODE" = staging ]; then
  echo "To reach it from the tailnet: sudo tailscale serve --bg --https=$PUBLIC_PORT http://127.0.0.1:$PORT"
fi
