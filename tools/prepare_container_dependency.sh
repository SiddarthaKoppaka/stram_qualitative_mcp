#!/bin/sh
set -eu

expected_commit=71a797d131bfad2e01aa8b390e8b0d5ba7e5d3e8
source_path=${1:-../stram_data}
archive_path=$(mktemp -d)
trap 'rm -rf "$archive_path"' EXIT

git -C "$source_path" cat-file -e "$expected_commit^{commit}"
git -C "$source_path" archive "$expected_commit" | tar -x -C "$archive_path"
install -d -m 0755 vendor
uv build --wheel --out-dir vendor "$archive_path"
test -f vendor/stram_data-1.12.0-py3-none-any.whl
sha256sum vendor/stram_data-1.12.0-py3-none-any.whl
