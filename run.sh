#!/usr/bin/env bash
# Kubuntu 26.10 workstation setup; run from a complete checkout.
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
command -v python3 >/dev/null || { echo 'Python 3 is required (included with Kubuntu).' >&2; exit 1; }
exec python3 "$SCRIPT_DIR/scripts/install.py" "$@"
