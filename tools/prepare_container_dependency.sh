#!/bin/sh
set -eu

expected_commit=4e9fe241a239fd488e5a356fd064ac7a209b0c9e
source_path=${1:-../stram_data}
archive_path=$(mktemp -d)
trap 'rm -rf "$archive_path"' EXIT

git -C "$source_path" cat-file -e "$expected_commit^{commit}"
git -C "$source_path" archive "$expected_commit" | tar -x -C "$archive_path"
install -d -m 0755 vendor
uv build --wheel --out-dir vendor "$archive_path"
test -f vendor/stram_data-1.4.1-py3-none-any.whl
sha256sum vendor/stram_data-1.4.1-py3-none-any.whl
