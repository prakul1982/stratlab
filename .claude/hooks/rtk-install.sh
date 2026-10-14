#!/bin/sh
# SessionStart: installs rtk (https://github.com/rtk-ai/rtk), which shortens shell command output before it reaches
# Claude, into ~/.local/bin when the container doesn't have it yet. Pinned to one release: the installer and the binary
# both come from that tag, and the installer checks the binary's checksum. Never fails the session.
BIN="$HOME/.local/bin/rtk"
[ -x "$BIN" ] && exit 0
VERSION=v1.0.0
tmp=$(mktemp -d) || exit 0
if curl -fsSL --max-time 30 "https://raw.githubusercontent.com/rtk-ai/rtk/$VERSION/install.sh" -o "$tmp/install.sh"; then
  RTK_VERSION=$VERSION timeout 120 sh "$tmp/install.sh" >/dev/null 2>&1
fi
rm -rf "$tmp"
exit 0
