#!/bin/sh
set -eu

expected_commit=a53ef2a8d32d073a3cace47ae51f82d70c0aa7a3
source_path=${1:-../stram_data}
archive_path=$(mktemp -d)
trap 'rm -rf "$archive_path"' EXIT

git -C "$source_path" cat-file -e "$expected_commit^{commit}"
git -C "$source_path" archive "$expected_commit" | tar -x -C "$archive_path"
install -d -m 0755 vendor
uv build --wheel --out-dir vendor "$archive_path"
test -f vendor/stram_data-1.16.0-py3-none-any.whl
sha256sum vendor/stram_data-1.16.0-py3-none-any.whl
