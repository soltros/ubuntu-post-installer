#!/usr/bin/env bash
set -euo pipefail

PLUGIN_ID="org.kde.plasma.chatgpt"

JS_SCRIPT='
var pIds = panelIds;
var added = false;
var alreadyPresent = false;

for (var i = 0; i < pIds.length; ++i) {
    var p = panelById(pIds[i]);
    var wIds = p.widgetIds;
    for (var j = 0; j < wIds.length; ++j) {
        var w = p.widgetById(wIds[j]);
        if (w.type === "org.kde.plasma.chatgpt") {
            alreadyPresent = true;
            break;
        }
    }
}

if (!alreadyPresent && pIds.length > 0) {
    var targetPanel = panelById(pIds[0]);
    targetPanel.addWidget("org.kde.plasma.chatgpt");
    added = true;
}
print(alreadyPresent ? "already_present" : (added ? "added" : "no_panel"));
'

qdbus org.kde.plasmashell /PlasmaShell org.kde.PlasmaShell.evaluateScript "${JS_SCRIPT}"
