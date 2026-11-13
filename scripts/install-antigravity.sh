#!/usr/bin/env bash
# Official user-level Antigravity CLI installer, run as the desktop account.
set -euo pipefail
if [[ "$EUID" -eq 0 ]]; then
    echo 'Run the Antigravity installer as your desktop user, not root.' >&2
    exit 1
fi
export PATH="$HOME/.local/bin:$PATH"
curl -fsSL https://antigravity.google/cli/install.sh | bash
if [[ ! -x "$HOME/.local/bin/agy" ]]; then
    echo 'Antigravity installer completed but ~/.local/bin/agy is missing.' >&2
    exit 1
fi
printf 'Antigravity CLI installed for %s: %s/.local/bin/agy\n' "$(id -un)" "$HOME"
