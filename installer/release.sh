#!/bin/sh
# Build DBee Setup for every platform into DEST (default installer/dist):
#   DBee Setup.exe                         Windows amd64
#   DBee-Setup-<ver>-macos-<arch>.zip      a DBee Setup.app (arm64, amd64); unsigned for now
#   dbee-setup-<ver>-linux-<arch>.tar.gz   the binary (amd64, arm64)
#   SHA256SUMS
# The version is VERSION, else `git describe`. Each binary carries DBee's package
# (stage.sh) and needs nothing else on the machine.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
dest=${1:-$here/dist}
ver=${VERSION:-$(git -C "$here" describe --tags --always --dirty)}
mkdir -p "$dest"
dest=$(cd "$dest" && pwd)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
sh "$here/stage.sh"
build() { (cd "$here" && CGO_ENABLED=0 GOOS=$1 GOARCH=$2 go build -trimpath -ldflags "-s -w -X main.Version=$ver" -o "$3" .); }

build windows amd64 "$dest/DBee Setup.exe"
for a in amd64 arm64; do
    mkdir -p "$tmp/linux-$a"
    build linux "$a" "$tmp/linux-$a/dbee-setup"
    tar czf "$dest/dbee-setup-$ver-linux-$a.tar.gz" -C "$tmp/linux-$a" dbee-setup
done
for a in arm64 amd64; do
    app="$tmp/mac-$a/DBee Setup.app/Contents"
    mkdir -p "$app/MacOS"
    build darwin "$a" "$app/MacOS/dbee-setup"
    cat > "$app/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleName</key><string>DBee Setup</string>
<key>CFBundleIdentifier</key><string>com.dbee.setup</string>
<key>CFBundleExecutable</key><string>dbee-setup</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>CFBundleShortVersionString</key><string>$ver</string>
<key>LSMinimumSystemVersion</key><string>12.0</string>
</dict></plist>
PLIST
    rm -f "$dest/DBee-Setup-$ver-macos-$a.zip"
    (cd "$tmp/mac-$a" && zip -qry "$dest/DBee-Setup-$ver-macos-$a.zip" "DBee Setup.app")
done
(cd "$dest" && sha256sum "DBee Setup.exe" *"-$ver-"* > SHA256SUMS)
echo "DBee Setup $ver in $dest:"
(cd "$dest" && ls -l "DBee Setup.exe" *"-$ver-"* SHA256SUMS | awk '{print "  " $5 "\t" substr($0, index($0, $9))}')
