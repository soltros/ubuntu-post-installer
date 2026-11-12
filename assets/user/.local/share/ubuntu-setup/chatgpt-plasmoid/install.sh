#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ID="org.kde.plasma.chatgpt"

# Install icon to user hicolor theme so widget explorer & panel find it
ICON_DIR="${HOME}/.local/share/icons/hicolor/scalable/apps"
mkdir -p "${ICON_DIR}"
cp "${SCRIPT_DIR}/contents/icons/chatgpt.svg" "${ICON_DIR}/chatgpt.svg"

# Install or upgrade the Plasma 6 applet package
if kpackagetool6 --type Plasma/Applet --show "${PLUGIN_ID}" >/dev/null 2>&1; then
    echo "Upgrading existing ${PLUGIN_ID} plasmoid..."
    kpackagetool6 --type Plasma/Applet --upgrade "${SCRIPT_DIR}"
else
    echo "Installing ${PLUGIN_ID} plasmoid..."
    kpackagetool6 --type Plasma/Applet --install "${SCRIPT_DIR}"
fi

echo "Successfully installed ${PLUGIN_ID}!"
