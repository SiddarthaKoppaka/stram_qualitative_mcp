#!/bin/sh
# Build the service image with Podman and save it for the service user.
#   sh deploy/build_image.sh STRAM_DATA_CHECKOUT [OUTPUT_TAR]
# STRAM_DATA_CHECKOUT is any clone holding the pinned commit. Needs uv, Podman and Git.
# A 503 from snapshot.debian.org is usually temporary: wait a minute and run it again.
set -eu

[ $# -ge 1 ] || { echo "Usage: sh $0 STRAM_DATA_CHECKOUT [OUTPUT_TAR]" >&2; exit 1; }
SOURCE=$1
OUTPUT=${2:-/tmp/stram-qualitative-mcp.tar}
IMAGE=localhost/stram-qualitative-mcp:m5

sh tools/prepare_container_dependency.sh "$SOURCE"
podman build --pull=missing --build-arg VCS_REF="$(git rev-parse HEAD)" -t "$IMAGE" .
podman run --rm --read-only --network none --cap-drop ALL --security-opt no-new-privileges \
  --tmpfs /tmp:rw,noexec,nosuid,nodev,size=64m "$IMAGE" worker-network-probe
rm -f "$OUTPUT"
podman save -o "$OUTPUT" "$IMAGE"
chmod 644 "$OUTPUT"
echo "Saved $OUTPUT"
