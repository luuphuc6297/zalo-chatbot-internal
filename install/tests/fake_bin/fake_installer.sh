#!/bin/bash
# Fake of Anthropic's install.sh for the installer tests (16.10). support.py copies it into the fixture folder as
# install.sh with @FAKE_BIN@ replaced, and the fake curl serves it for https://claude.ai/install.sh.
# Like the real script it ends by running the downloaded binary with `install <version>`; here that binary is a
# wrapper around the fake claude, placed at ~/.local/share/claude/versions/<version>. The fake claude's `install`
# does nothing while DISABLE_UPDATES is set, exactly like Claude Code 2.1.319 (rev F1).
set -eu
ver="${1:-stable}"
dir="$HOME/.local/share/claude/versions"
mkdir -p "$dir"
printf '#!/bin/sh\nTHOMHOUSE_FAKE_CLAUDE_VERSION=%s exec "%s/claude" "$@"\n' "$ver" "@FAKE_BIN@" >"$dir/$ver"
chmod 755 "$dir/$ver"
"$dir/$ver" install "$ver"
