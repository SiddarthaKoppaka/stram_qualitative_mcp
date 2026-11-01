#!/bin/sh
set -eu

expected_commit=947e49b2cd054e280918274e27e6940d7327e17f
source_path=${1:-../stram_data}
archive_path=$(mktemp -d)
trap 'rm -rf "$archive_path"' EXIT

git -C "$source_path" cat-file -e "$expected_commit^{commit}"
git -C "$source_path" archive "$expected_commit" | tar -x -C "$archive_path"
install -d -m 0755 vendor
uv build --wheel --out-dir vendor "$archive_path"
test -f vendor/stram_data-1.6.0-py3-none-any.whl
sha256sum vendor/stram_data-1.6.0-py3-none-any.whl
