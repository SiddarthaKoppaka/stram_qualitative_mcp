#!/bin/sh
set -eu

expected_commit=2eaf9aef309e3be3ed6d575cbc84d7813b1ea6be
source_path=${1:-../stram_data}
archive_path=$(mktemp -d)
trap 'rm -rf "$archive_path"' EXIT

git -C "$source_path" cat-file -e "$expected_commit^{commit}"
git -C "$source_path" archive "$expected_commit" | tar -x -C "$archive_path"
install -d -m 0755 vendor
uv build --wheel --out-dir vendor "$archive_path"
test -f vendor/stram_data-1.12.0-py3-none-any.whl
sha256sum vendor/stram_data-1.12.0-py3-none-any.whl
