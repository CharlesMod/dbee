#!/bin/sh
# Copy the DBee Python package and its runtime assets into payload/, where
# go:embed can reach them. Run before `go build`.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
src=$(cd "$here/.." && pwd)
rm -rf "$here/payload/dbee" "$here/payload/assets"
mkdir -p "$here/payload/dbee" "$here/payload/assets"
cp -R "$src/dbee/." "$here/payload/dbee/"
cp -R "$src/assets/." "$here/payload/assets/"
find "$here/payload" -name __pycache__ -type d -prune -exec rm -rf {} +
find "$here/payload" -name '*.pyc' -delete
touch "$here/payload/.keep"
echo "staged $(find "$here/payload" -type f | wc -l) files into payload/"
