#!/bin/sh
# PreToolUse (Bash): lets rtk rewrite the command into its shorter-output form. Without rtk installed this prints
# nothing, so the command runs unchanged.
BIN="$HOME/.local/bin/rtk"
[ -x "$BIN" ] && exec "$BIN" hook claude
exit 0
