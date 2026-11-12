import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as QQC2
import org.kde.plasma.core as PlasmaCore
import org.kde.plasma.plasmoid
import org.kde.plasma.components as PlasmaComponents3
import org.kde.plasma.extras as PlasmaExtras
import org.kde.plasma.plasma5support as Plasma5Support
import org.kde.kirigami as Kirigami

PlasmoidItem {
    id: root

    Plasmoid.backgroundHints: PlasmaCore.Types.DefaultBackground | PlasmaCore.Types.ConfigurableBackground
    Plasmoid.title: i18n("ChatGPT Codex")
    toolTipMainText: i18n("ChatGPT / Codex CLI")
    toolTipSubText: isBusy
        ? i18n("Codex is working: %1", liveStatusText)
        : (loggedIn ? i18n("%1 • Click to open, Middle-click for New Chat", authStatusText) : i18n("Click to sign in with Codex CLI"))

    hideOnWindowDeactivate: !Plasmoid.configuration.pinned

    switchWidth: Kirigami.Units.gridUnit * 18
    switchHeight: Kirigami.Units.gridUnit * 22

    // State properties
    property bool loggedIn: true
    property string authStatusText: "Logged in using ChatGPT"
    property string activeThreadId: ""
    property string activeThreadTitle: i18n("New Codex Chat")
    property string currentCwd: Plasmoid.configuration.defaultCwd || "/home/derrik"
    property string selectedModel: Plasmoid.configuration.defaultModel || "default"
    property string selectedSandbox: Plasmoid.configuration.sandboxMode || "workspace-write"

    property bool isBusy: false
    property string liveStatusText: ""
    property string liveStreamingText: ""
    property var liveActivities: []

    property bool showHistoryDrawer: false
    property bool showAccountPanel: false

    property var availableModels: [
        "default",
        "gpt-6.1-sol",
        "gpt-6-astra",
        "gpt-6-chat-thinking",
        "gpt-6.1-terra",
        "gpt-6-sol",
        "gpt-6-luna",
        "gpt-5.6-sol",
        "gpt-5.6-terra",
        "gpt-5.6-luna",
        "gpt-5.4-mini"
    ]

    ListModel {
        id: chatModel
    }

    ListModel {
        id: threadsModel
    }

    function scriptPath() {
        const urlStr = Qt.resolvedUrl("../scripts/codex-bridge.py").toString();
        return urlStr.replace(/^file:\/\//, "");
    }

    function shQuote(s) {
        return "'" + String(s).replace(/'/g, "'\"'\"'") + "'";
    }

    function blendColors(c1, c2, ratio) {
        if (!c1) return c2 || Qt.rgba(0.1, 0.1, 0.1, 1.0);
        if (!c2) return c1;
        return Qt.rgba(
            c1.r * (1 - ratio) + c2.r * ratio,
            c1.g * (1 - ratio) + c2.g * ratio,
            c1.b * (1 - ratio) + c2.b * ratio,
            1.0
        );
    }

    // Executable runner using built-in Plasma5Support DataSource (zero external QML plugins required)
    Plasma5Support.DataSource {
        id: execEngine
        engine: "executable"
        connectedSources: []

        onNewData: (sourceName, data) => {
            const stdout = (data["stdout"] || "").trim();
            const stderr = (data["stderr"] || "").trim();
            disconnectSource(sourceName);

            if (sourceName.indexOf(" #init") !== -1) {
                handleInitOutput(stdout);
            } else if (sourceName.indexOf(" #status") !== -1) {
                handleStatusOutput(stdout);
            } else if (sourceName.indexOf(" #load-thread") !== -1) {
                handleLoadThreadOutput(stdout);
            } else if (sourceName.indexOf(" #send") !== -1) {
                handleSendFinished(stdout, stderr);
            } else if (sourceName.indexOf(" #stream-state") !== -1) {
                handleStreamPollOutput(stdout);
            } else if (sourceName.indexOf(" #auth") !== -1) {
                handleStatusOutput(stdout);
            }
        }
    }

    function runBridgeCommand(argsStr, tag) {
        const cmd = "python3 " + shQuote(scriptPath()) + " " + argsStr + " #" + tag + "_" + Date.now();
        execEngine.connectSource(cmd);
    }

    function refreshInitData() {
        runBridgeCommand("init", "init");
    }

    function handleInitOutput(stdout) {
        if (!stdout) return;
        try {
            const obj = JSON.parse(stdout);
            if (obj.auth) {
                root.loggedIn = !!obj.auth.loggedIn;
                root.authStatusText = obj.auth.statusText || (root.loggedIn ? "Logged in" : "Not logged in");
            }
            if (obj.models && obj.models.length > 0) {
                root.availableModels = obj.models;
            }
            if (obj.threads) {
                threadsModel.clear();
                for (let i = 0; i < obj.threads.length; ++i) {
                    threadsModel.append(obj.threads[i]);
                }
            }
        } catch (e) {}
    }

    function handleStatusOutput(stdout) {
        if (!stdout) return;
        try {
            const obj = JSON.parse(stdout);
            root.loggedIn = !!obj.loggedIn;
            root.authStatusText = obj.statusText || (root.loggedIn ? "Logged in" : "Not logged in");
        } catch (e) {}
    }

    function loadThread(threadId, threadTitle) {
        if (!threadId) return;
        root.activeThreadId = threadId;
        if (threadTitle) {
            root.activeThreadTitle = threadTitle;
        }
        root.showHistoryDrawer = false;
        runBridgeCommand("load-thread --thread-id " + shQuote(threadId), "load-thread");
    }

    function handleLoadThreadOutput(stdout) {
        if (!stdout) return;
        try {
            const obj = JSON.parse(stdout);
            root.activeThreadId = obj.threadId || root.activeThreadId;
            if (obj.title) {
                root.activeThreadTitle = obj.title;
            }
            if (obj.cwd) {
                root.currentCwd = obj.cwd;
            }
            chatModel.clear();
            const msgs = obj.messages || [];
            for (let i = 0; i < msgs.length; ++i) {
                chatModel.append({
                    role: msgs[i].role || "assistant",
                    text: msgs[i].text || "",
                    meta: msgs[i].meta || ""
                });
            }
            scrollToBottomSignal();
        } catch (e) {}
    }

    function startNewChat() {
        if (root.isBusy) {
            stopGeneration();
        }
        root.activeThreadId = "";
        root.activeThreadTitle = i18n("New Codex Chat");
        root.liveStreamingText = "";
        root.liveStatusText = "";
        root.liveActivities = [];
        root.showHistoryDrawer = false;
        chatModel.clear();
        focusPromptSignal();
    }

    function resumeMostRecentThread() {
        if (threadsModel.count > 0) {
            const first = threadsModel.get(0);
            loadThread(first.id, first.title);
        } else {
            refreshInitData();
        }
    }

    function sendMessage(promptText) {
        const trimmed = (promptText || "").trim();
        if (!trimmed || root.isBusy) return;

        if (root.activeThreadTitle === i18n("New Codex Chat")) {
            root.activeThreadTitle = trimmed.length > 48 ? (trimmed.slice(0, 45) + "...") : trimmed;
        }

        chatModel.append({
            role: "user",
            text: trimmed,
            meta: root.selectedModel === "default" ? "" : root.selectedModel
        });

        root.isBusy = true;
        root.liveStatusText = i18n("Starting Codex…");
        root.liveStreamingText = "";
        root.liveActivities = [];
        scrollToBottomSignal();

        let args = "send --prompt " + shQuote(trimmed)
            + " --model " + shQuote(root.selectedModel)
            + " --sandbox " + shQuote(root.selectedSandbox)
            + " --cwd " + shQuote(root.currentCwd);

        if (root.activeThreadId) {
            args += " --thread-id " + shQuote(root.activeThreadId);
        }

        streamPollTimer.start();
        runBridgeCommand(args, "send");
    }

    function handleStreamPollOutput(stdout) {
        if (!stdout || !root.isBusy) return;
        try {
            const st = JSON.parse(stdout);
            if (st.threadId && !root.activeThreadId) {
                root.activeThreadId = st.threadId;
            }
            if (st.status) {
                root.liveStatusText = st.status;
            }
            if (st.text !== undefined) {
                root.liveStreamingText = st.text;
            }
            if (st.activities) {
                root.liveActivities = st.activities;
            }
            scrollToBottomSignal();
        } catch (e) {}
    }

    function handleSendFinished(stdout, stderr) {
        streamPollTimer.stop();
        root.isBusy = false;

        let finalObj = null;
        if (stdout) {
            try {
                finalObj = JSON.parse(stdout);
            } catch (e) {}
        }

        if (finalObj) {
            if (finalObj.threadId) {
                root.activeThreadId = finalObj.threadId;
            }
            if (finalObj.activities && finalObj.activities.length > 0) {
                for (let i = 0; i < finalObj.activities.length; ++i) {
                    chatModel.append({
                        role: "tool",
                        text: finalObj.activities[i],
                        meta: ""
                    });
                }
            }
            const replyText = (finalObj.text || root.liveStreamingText || "").trim();
            if (replyText) {
                let usageMeta = "";
                if (finalObj.usage && finalObj.usage.output_tokens) {
                    usageMeta = finalObj.usage.output_tokens + " tok";
                }
                chatModel.append({
                    role: "assistant",
                    text: replyText,
                    meta: usageMeta
                });
            }
            if (finalObj.error) {
                chatModel.append({
                    role: "error",
                    text: finalObj.error,
                    meta: i18n("Error")
                });
            }
        } else if (stderr) {
            chatModel.append({
                role: "error",
                text: stderr,
                meta: i18n("Error")
            });
        }

        root.liveStreamingText = "";
        root.liveStatusText = "";
        root.liveActivities = [];
        scrollToBottomSignal();
        refreshInitData();
    }

    function stopGeneration() {
        streamPollTimer.stop();
        runBridgeCommand("stop", "stop");
        if (root.liveStreamingText) {
            chatModel.append({
                role: "assistant",
                text: root.liveStreamingText + "\n\n*(Stopped)*",
                meta: i18n("Stopped")
            });
        }
        root.isBusy = false;
        root.liveStreamingText = "";
        root.liveStatusText = "";
    }

    function openInTerminalTui() {
        let args = "open-tui --cwd " + shQuote(root.currentCwd) + " --model " + shQuote(root.selectedModel);
        if (root.activeThreadId) {
            args += " --thread-id " + shQuote(root.activeThreadId);
        }
        runBridgeCommand(args, "open-tui");
    }

    function copyToClipboard(txt) {
        if (!txt) return;
        runBridgeCommand("copy --text " + shQuote(txt), "copy");
    }

    Timer {
        id: streamPollTimer
        interval: 220
        repeat: true
        onTriggered: {
            if (root.isBusy) {
                runBridgeCommand("stream-state", "stream-state");
            }
        }
    }

    signal scrollToBottomSignal()
    signal focusPromptSignal()

    Component.onCompleted: {
        refreshInitData();
    }

    onExpandedChanged: () => {
        if (root.expanded) {
            refreshInitData();
            if (Plasmoid.configuration.focusInputOnOpen) {
                focusTimer.restart();
            }
        }
    }

    Timer {
        id: focusTimer
        interval: 120
        repeat: false
        onTriggered: root.focusPromptSignal()
    }

    Plasmoid.contextualActions: [
        PlasmaCore.Action {
            text: i18n("New Codex Chat")
            icon.name: "list-add"
            onTriggered: {
                root.expanded = true;
                root.startNewChat();
            }
        },
        PlasmaCore.Action {
            text: i18n("Resume Most Recent Session")
            icon.name: "view-history"
            onTriggered: {
                root.expanded = true;
                root.resumeMostRecentThread();
            }
        },
        PlasmaCore.Action {
            text: i18n("Open Interactive Codex TUI in Terminal")
            icon.name: "utilities-terminal"
            onTriggered: root.openInTerminalTui()
        },
        PlasmaCore.Action {
            isSeparator: true
        },
        PlasmaCore.Action {
            text: i18n("Sign In / Refresh Codex Auth")
            icon.name: "user-identity"
            onTriggered: {
                root.expanded = true;
                root.showAccountPanel = true;
            }
        }
    ]

    compactRepresentation: MouseArea {
        id: compactRoot

        Layout.minimumWidth: Kirigami.Units.iconSizes.small
        Layout.minimumHeight: Kirigami.Units.iconSizes.small

        hoverEnabled: true
        acceptedButtons: Qt.LeftButton | Qt.MiddleButton

        onClicked: (mouse) => {
            if (mouse.button === Qt.MiddleButton) {
                root.expanded = true;
                root.startNewChat();
            } else {
                root.expanded = !root.expanded;
            }
        }

        Kirigami.Icon {
            anchors.fill: parent
            anchors.margins: Math.max(2, Math.round(Math.min(parent.width, parent.height) * 0.08))
            source: Qt.resolvedUrl("../icons/chatgpt.svg")
            active: compactRoot.containsMouse || root.expanded
            isMask: true
            color: Kirigami.Theme.textColor
        }

        Rectangle {
            visible: root.isBusy || root.expanded
            width: Math.max(5, Math.round(Math.min(parent.width, parent.height) * 0.18))
            height: width
            radius: width / 2
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            anchors.margins: 2
            color: root.isBusy ? Kirigami.Theme.neutralTextColor : Kirigami.Theme.highlightColor
            border.width: 1
            border.color: Kirigami.Theme.backgroundColor
        }
    }

    fullRepresentation: PlasmaExtras.Representation {
        id: fullRoot

        Layout.minimumWidth: 380
        Layout.minimumHeight: 460
        Layout.preferredWidth: Plasmoid.configuration.popupWidth || 520
        Layout.preferredHeight: Plasmoid.configuration.popupHeight || 700

        collapseMarginsHint: true

        Connections {
            target: root
            function onScrollToBottomSignal() {
                scrollTimer.restart();
            }
            function onFocusPromptSignal() {
                promptInput.forceActiveFocus();
            }
        }

        Timer {
            id: scrollTimer
            interval: 50
            repeat: false
            onTriggered: {
                if (messagesListView.count > 0) {
                    messagesListView.positionViewAtEnd();
                }
            }
        }

        header: PlasmaExtras.PlasmoidHeading {
            ColumnLayout {
                anchors.fill: parent
                spacing: Kirigami.Units.smallSpacing

                // Top Row: Title + Quick Action Buttons
                RowLayout {
                    Layout.fillWidth: true
                    spacing: Kirigami.Units.smallSpacing

                    Kirigami.Icon {
                        source: Qt.resolvedUrl("../icons/chatgpt.svg")
                        Layout.preferredWidth: Kirigami.Units.iconSizes.smallMedium
                        Layout.preferredHeight: Kirigami.Units.iconSizes.smallMedium
                        isMask: true
                        color: Kirigami.Theme.highlightColor
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 0

                        PlasmaComponents3.Label {
                            text: root.activeThreadTitle
                            font.bold: true
                            elide: Text.ElideRight
                            Layout.fillWidth: true
                        }

                        PlasmaComponents3.Label {
                            text: root.activeThreadId
                                ? ("Thread " + root.activeThreadId.slice(0, 8) + " • " + root.authStatusText)
                                : root.authStatusText
                            font: Kirigami.Theme.smallFont
                            color: root.loggedIn ? Kirigami.Theme.positiveTextColor : Kirigami.Theme.neutralTextColor
                            elide: Text.ElideRight
                            Layout.fillWidth: true
                        }
                    }

                    PlasmaComponents3.ToolButton {
                        icon.name: "view-history"
                        checkable: true
                        checked: root.showHistoryDrawer
                        onClicked: {
                            root.showHistoryDrawer = !root.showHistoryDrawer;
                            if (root.showHistoryDrawer) {
                                root.refreshInitData();
                            }
                        }
                        PlasmaComponents3.ToolTip {
                            text: i18n("Recent Codex Sessions (%1)", threadsModel.count)
                        }
                    }

                    PlasmaComponents3.ToolButton {
                        icon.name: "list-add"
                        onClicked: root.startNewChat()
                        PlasmaComponents3.ToolTip {
                            text: i18n("New Codex Chat")
                        }
                    }

                    PlasmaComponents3.ToolButton {
                        icon.name: "utilities-terminal"
                        onClicked: root.openInTerminalTui()
                        PlasmaComponents3.ToolTip {
                            text: root.activeThreadId
                                ? i18n("Resume Current Thread in Interactive Terminal (Codex TUI)")
                                : i18n("Launch Interactive Codex TUI in Terminal")
                        }
                    }

                    PlasmaComponents3.ToolButton {
                        icon.name: "user-identity"
                        checkable: true
                        checked: root.showAccountPanel
                        onClicked: root.showAccountPanel = !root.showAccountPanel
                        PlasmaComponents3.ToolTip {
                            text: i18n("Codex Login & Workspace Settings")
                        }
                    }

                    PlasmaComponents3.ToolButton {
                        icon.name: "window-pin"
                        checkable: true
                        checked: Plasmoid.configuration.pinned
                        onToggled: Plasmoid.configuration.pinned = checked
                        PlasmaComponents3.ToolTip {
                            text: Plasmoid.configuration.pinned
                                ? i18n("Unpin Popup")
                                : i18n("Pin Popup (Keep open when clicking outside)")
                        }
                    }
                }

                // Second Row: Model Picker + Sandbox Picker
                RowLayout {
                    Layout.fillWidth: true
                    spacing: Kirigami.Units.smallSpacing

                    Kirigami.Icon {
                        source: "cpu"
                        Layout.preferredWidth: Kirigami.Units.iconSizes.small
                        Layout.preferredHeight: Kirigami.Units.iconSizes.small
                    }

                    PlasmaComponents3.ComboBox {
                        id: modelCombo
                        Layout.fillWidth: true
                        model: root.availableModels
                        currentIndex: Math.max(0, root.availableModels.indexOf(root.selectedModel))
                        onActivated: (idx) => {
                            root.selectedModel = root.availableModels[idx];
                            Plasmoid.configuration.defaultModel = root.selectedModel;
                        }
                        PlasmaComponents3.ToolTip {
                            text: i18n("Select Codex Model")
                        }
                    }

                    PlasmaComponents3.ComboBox {
                        id: sandboxCombo
                        Layout.preferredWidth: Kirigami.Units.gridUnit * 8.5
                        model: ["workspace-write", "read-only", "danger-full-access"]
                        currentIndex: Math.max(0, model.indexOf(root.selectedSandbox))
                        onActivated: (idx) => {
                            root.selectedSandbox = model[idx];
                            Plasmoid.configuration.sandboxMode = root.selectedSandbox;
                        }
                        PlasmaComponents3.ToolTip {
                            text: i18n("Codex Sandbox Policy")
                        }
                    }
                }

                // Collapsible Account & Working Directory Panel
                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: accountCol.implicitHeight + Kirigami.Units.smallSpacing * 2
                    visible: root.showAccountPanel
                    radius: Kirigami.Units.cornerRadius
                    color: root.blendColors(Kirigami.Theme.backgroundColor, Kirigami.Theme.highlightColor, 0.12)
                    border.width: 1
                    border.color: root.blendColors(Kirigami.Theme.textColor, Kirigami.Theme.backgroundColor, 0.8)

                    ColumnLayout {
                        id: accountCol
                        anchors.fill: parent
                        anchors.margins: Kirigami.Units.smallSpacing
                        spacing: Kirigami.Units.smallSpacing

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: Kirigami.Units.smallSpacing

                            Kirigami.Icon {
                                source: root.loggedIn ? "security-high" : "security-low"
                                Layout.preferredWidth: Kirigami.Units.iconSizes.smallMedium
                                Layout.preferredHeight: Kirigami.Units.iconSizes.smallMedium
                            }

                            PlasmaComponents3.Label {
                                text: root.authStatusText
                                font.bold: true
                                Layout.fillWidth: true
                                elide: Text.ElideRight
                            }

                            PlasmaComponents3.Button {
                                text: root.loggedIn ? i18n("Re-Login") : i18n("Sign In with ChatGPT")
                                icon.name: "internet-web-browser"
                                onClicked: {
                                    root.runBridgeCommand("auth --action login", "auth");
                                }
                            }

                            PlasmaComponents3.Button {
                                visible: root.loggedIn
                                text: i18n("Log Out")
                                icon.name: "system-log-out"
                                onClicked: {
                                    root.runBridgeCommand("auth --action logout", "auth");
                                }
                            }
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: Kirigami.Units.smallSpacing

                            PlasmaComponents3.Label {
                                text: i18n("Dir:")
                                font: Kirigami.Theme.smallFont
                            }

                            PlasmaComponents3.TextField {
                                id: cwdEditField
                                Layout.fillWidth: true
                                text: root.currentCwd
                                placeholderText: "/home/derrik"
                                onEditingFinished: {
                                    root.currentCwd = text.trim() || "/home/derrik";
                                    Plasmoid.configuration.defaultCwd = root.currentCwd;
                                }
                            }

                            PlasmaComponents3.Button {
                                text: "~"
                                onClicked: {
                                    root.currentCwd = "/home/derrik";
                                    cwdEditField.text = root.currentCwd;
                                }
                                PlasmaComponents3.ToolTip {
                                    text: i18n("Set to /home/derrik")
                                }
                            }

                            PlasmaComponents3.Button {
                                text: "/data"
                                onClicked: {
                                    root.currentCwd = "/data/workspace";
                                    cwdEditField.text = root.currentCwd;
                                }
                                PlasmaComponents3.ToolTip {
                                    text: i18n("Set to /data/workspace")
                                }
                            }
                        }
                    }
                }
            }
        }

        // Main Content Area
        ColumnLayout {
            anchors.fill: parent
            spacing: 0

            // Collapsible Recent Sessions Drawer
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: Math.min(fullRoot.height * 0.48, Kirigami.Units.gridUnit * 14)
                visible: root.showHistoryDrawer
                color: Kirigami.Theme.alternateBackgroundColor

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: Kirigami.Units.smallSpacing
                    spacing: Kirigami.Units.smallSpacing

                    RowLayout {
                        Layout.fillWidth: true

                        PlasmaComponents3.Label {
                            text: i18n("Recent Codex Threads (~/.codex)")
                            font.bold: true
                            Layout.fillWidth: true
                        }

                        PlasmaComponents3.ToolButton {
                            icon.name: "view-refresh"
                            onClicked: root.refreshInitData()
                            PlasmaComponents3.ToolTip {
                                text: i18n("Refresh Thread List")
                            }
                        }

                        PlasmaComponents3.ToolButton {
                            icon.name: "window-close"
                            onClicked: root.showHistoryDrawer = false
                        }
                    }

                    PlasmaComponents3.ScrollView {
                        Layout.fillWidth: true
                        Layout.fillHeight: true

                        ListView {
                            id: threadsListView
                            model: threadsModel
                            spacing: 4
                            clip: true

                            delegate: PlasmaComponents3.ItemDelegate {
                                width: threadsListView.width
                                highlighted: model.id === root.activeThreadId
                                onClicked: root.loadThread(model.id, model.title)

                                contentItem: RowLayout {
                                    spacing: Kirigami.Units.smallSpacing

                                    Kirigami.Icon {
                                        source: "dialog-messages"
                                        Layout.preferredWidth: Kirigami.Units.iconSizes.small
                                        Layout.preferredHeight: Kirigami.Units.iconSizes.small
                                    }

                                    ColumnLayout {
                                        Layout.fillWidth: true
                                        spacing: 1

                                        PlasmaComponents3.Label {
                                            text: model.title || i18n("Untitled Session")
                                            elide: Text.ElideRight
                                            Layout.fillWidth: true
                                            font.bold: model.id === root.activeThreadId
                                        }

                                        PlasmaComponents3.Label {
                                            text: (model.cwd || "~") + " • " + (model.id ? model.id.slice(0, 8) : "")
                                            font: Kirigami.Theme.smallFont
                                            color: Kirigami.Theme.disabledTextColor
                                            elide: Text.ElideRight
                                            Layout.fillWidth: true
                                        }
                                    }
                                }
                            }
                        }
                    }
                }

                Kirigami.Separator {
                    anchors.bottom: parent.bottom
                    anchors.left: parent.left
                    anchors.right: parent.right
                }
            }

            // Chat Messages Area
            Item {
                Layout.fillWidth: true
                Layout.fillHeight: true

                // Welcome Empty State when no messages are present
                ColumnLayout {
                    anchors.centerIn: parent
                    width: parent.width - Kirigami.Units.largeSpacing * 2
                    visible: chatModel.count === 0 && !root.isBusy
                    spacing: Kirigami.Units.mediumSpacing

                    Kirigami.Icon {
                        source: Qt.resolvedUrl("../icons/chatgpt.svg")
                        Layout.preferredWidth: Kirigami.Units.iconSizes.huge
                        Layout.preferredHeight: Kirigami.Units.iconSizes.huge
                        Layout.alignment: Qt.AlignHCenter
                        isMask: true
                        color: Kirigami.Theme.highlightColor
                    }

                    PlasmaComponents3.Label {
                        text: i18n("Codex CLI Taskbar Assistant")
                        font.pointSize: Kirigami.Theme.defaultFont.pointSize * 1.25
                        font.bold: true
                        horizontalAlignment: Text.AlignHCenter
                        Layout.fillWidth: true
                    }

                    PlasmaComponents3.Label {
                        text: root.loggedIn
                            ? i18n("Authenticated via %1 • Model: %2\nWorking directory: %3", root.authStatusText, root.selectedModel, root.currentCwd)
                            : i18n("Not signed in — click the Account icon above to run `codex login`.")
                        font: Kirigami.Theme.smallFont
                        color: Kirigami.Theme.disabledTextColor
                        horizontalAlignment: Text.AlignHCenter
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }

                    Flow {
                        Layout.fillWidth: true
                        Layout.alignment: Qt.AlignHCenter
                        spacing: Kirigami.Units.smallSpacing

                        Repeater {
                            model: [
                                { label: i18n("Resume Latest Thread"), action: "resume" },
                                { label: i18n("Open Full Codex TUI"), action: "tui" },
                                { label: i18n("Check System & Git Status"), prompt: "Check the current directory and summarize what project or files are here." },
                                { label: i18n("Explain Ubuntu Setup"), prompt: "Summarize my Ubuntu desktop setup." }
                            ]

                            delegate: PlasmaComponents3.Button {
                                text: modelData.label
                                icon.name: modelData.action === "resume" ? "view-history"
                                         : (modelData.action === "tui" ? "utilities-terminal" : "draw-star")
                                onClicked: {
                                    if (modelData.action === "resume") {
                                        root.resumeMostRecentThread();
                                    } else if (modelData.action === "tui") {
                                        root.openInTerminalTui();
                                    } else if (modelData.prompt) {
                                        root.sendMessage(modelData.prompt);
                                    }
                                }
                            }
                        }
                    }
                }

                PlasmaComponents3.ScrollView {
                    anchors.fill: parent
                    visible: chatModel.count > 0 || root.isBusy

                    ListView {
                        id: messagesListView
                        anchors.fill: parent
                        model: chatModel
                        spacing: Kirigami.Units.smallSpacing
                        topMargin: Kirigami.Units.smallSpacing
                        bottomMargin: Kirigami.Units.smallSpacing
                        leftMargin: Kirigami.Units.smallSpacing
                        rightMargin: Kirigami.Units.smallSpacing
                        clip: true

                        delegate: Item {
                            width: messagesListView.width - messagesListView.leftMargin - messagesListView.rightMargin
                            implicitHeight: msgBubble.implicitHeight

                            readonly property bool isUser: model.role === "user"
                            readonly property bool isTool: model.role === "tool"
                            readonly property bool isError: model.role === "error"

                            Rectangle {
                                id: msgBubble
                                width: isTool
                                    ? parent.width
                                    : Math.min(parent.width * 0.92, Math.max(Kirigami.Units.gridUnit * 10, parent.width * (isUser ? 0.84 : 0.94)))
                                anchors.right: isUser ? parent.right : undefined
                                anchors.left: !isUser ? parent.left : undefined
                                implicitHeight: bubbleCol.implicitHeight + Kirigami.Units.smallSpacing * 2
                                radius: Kirigami.Units.cornerRadius
                                color: isError
                                    ? root.blendColors(Kirigami.Theme.backgroundColor, Kirigami.Theme.negativeTextColor, 0.20)
                                    : (isUser
                                        ? root.blendColors(Kirigami.Theme.backgroundColor, Kirigami.Theme.highlightColor, 0.24)
                                        : (isTool
                                            ? root.blendColors(Kirigami.Theme.backgroundColor, Kirigami.Theme.textColor, 0.05)
                                            : Kirigami.Theme.alternateBackgroundColor))
                                border.width: 1
                                border.color: isUser
                                    ? root.blendColors(Kirigami.Theme.highlightColor, Kirigami.Theme.backgroundColor, 0.5)
                                    : root.blendColors(Kirigami.Theme.textColor, Kirigami.Theme.backgroundColor, 0.86)

                                ColumnLayout {
                                    id: bubbleCol
                                    anchors.fill: parent
                                    anchors.margins: Kirigami.Units.smallSpacing
                                    spacing: 4

                                    RowLayout {
                                        Layout.fillWidth: true
                                        visible: !isTool
                                        spacing: Kirigami.Units.smallSpacing

                                        PlasmaComponents3.Label {
                                            text: isUser ? i18n("You") : (isError ? i18n("Error") : i18n("Codex"))
                                            font.bold: true
                                            font.pointSize: Kirigami.Theme.smallFont.pointSize
                                            color: isUser ? Kirigami.Theme.highlightColor : Kirigami.Theme.disabledTextColor
                                        }

                                        PlasmaComponents3.Label {
                                            text: model.meta || ""
                                            visible: (model.meta || "").length > 0
                                            font: Kirigami.Theme.smallFont
                                            color: Kirigami.Theme.disabledTextColor
                                        }

                                        Item { Layout.fillWidth: true }

                                        PlasmaComponents3.ToolButton {
                                            icon.name: "edit-copy"
                                            Layout.preferredWidth: Kirigami.Units.iconSizes.small + 4
                                            Layout.preferredHeight: Kirigami.Units.iconSizes.small + 4
                                            onClicked: root.copyToClipboard(model.text)
                                            PlasmaComponents3.ToolTip {
                                                text: i18n("Copy message to clipboard")
                                            }
                                        }
                                    }

                                    TextEdit {
                                        Layout.fillWidth: true
                                        readOnly: true
                                        selectByMouse: true
                                        wrapMode: TextEdit.Wrap
                                        textFormat: isTool ? TextEdit.MarkdownText : TextEdit.MarkdownText
                                        text: model.text || ""
                                        color: Kirigami.Theme.textColor
                                        selectedTextColor: Kirigami.Theme.highlightedTextColor
                                        selectionColor: Kirigami.Theme.highlightColor
                                        font: isTool ? Kirigami.Theme.fixedFont : Kirigami.Theme.defaultFont
                                        onLinkActivated: (link) => Qt.openUrlExternally(link)
                                    }
                                }
                            }
                        }

                        // Live Streaming Footer inside ListView while Codex is working
                        footer: Item {
                            width: messagesListView.width - messagesListView.leftMargin - messagesListView.rightMargin
                            height: root.isBusy ? (streamCard.implicitHeight + Kirigami.Units.smallSpacing) : 0
                            visible: root.isBusy

                            Rectangle {
                                id: streamCard
                                width: parent.width * 0.94
                                implicitHeight: streamCol.implicitHeight + Kirigami.Units.smallSpacing * 2
                                radius: Kirigami.Units.cornerRadius
                                color: Kirigami.Theme.alternateBackgroundColor
                                border.width: 1
                                border.color: Kirigami.Theme.highlightColor

                                ColumnLayout {
                                    id: streamCol
                                    anchors.fill: parent
                                    anchors.margins: Kirigami.Units.smallSpacing
                                    spacing: Kirigami.Units.smallSpacing

                                    RowLayout {
                                        Layout.fillWidth: true
                                        spacing: Kirigami.Units.smallSpacing

                                        PlasmaComponents3.BusyIndicator {
                                            running: root.isBusy
                                            Layout.preferredWidth: Kirigami.Units.iconSizes.smallMedium
                                            Layout.preferredHeight: Kirigami.Units.iconSizes.smallMedium
                                        }

                                        PlasmaComponents3.Label {
                                            text: root.liveStatusText || i18n("Working…")
                                            font.bold: true
                                            color: Kirigami.Theme.highlightColor
                                            elide: Text.ElideRight
                                            Layout.fillWidth: true
                                        }

                                        PlasmaComponents3.Button {
                                            text: i18n("Stop")
                                            icon.name: "process-stop"
                                            onClicked: root.stopGeneration()
                                        }
                                    }

                                    PlasmaComponents3.Label {
                                        visible: root.liveActivities && root.liveActivities.length > 0
                                        text: root.liveActivities ? root.liveActivities.join("\n") : ""
                                        font: Kirigami.Theme.smallFont
                                        color: Kirigami.Theme.disabledTextColor
                                        wrapMode: Text.WordWrap
                                        Layout.fillWidth: true
                                    }

                                    TextEdit {
                                        visible: root.liveStreamingText.length > 0
                                        Layout.fillWidth: true
                                        readOnly: true
                                        selectByMouse: true
                                        wrapMode: TextEdit.Wrap
                                        textFormat: TextEdit.MarkdownText
                                        text: root.liveStreamingText
                                        color: Kirigami.Theme.textColor
                                        font: Kirigami.Theme.defaultFont
                                    }
                                }
                            }
                        }
                    }
                }
            }

            Kirigami.Separator {
                Layout.fillWidth: true
            }

            // Bottom Composer Input Bar
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: composerRow.implicitHeight + Kirigami.Units.smallSpacing * 2
                color: Kirigami.Theme.backgroundColor

                RowLayout {
                    id: composerRow
                    anchors.fill: parent
                    anchors.margins: Kirigami.Units.smallSpacing
                    spacing: Kirigami.Units.smallSpacing

                    PlasmaComponents3.ScrollView {
                        Layout.fillWidth: true
                        Layout.maximumHeight: Kirigami.Units.gridUnit * 6
                        Layout.preferredHeight: Math.max(
                            Kirigami.Units.gridUnit * 2.3,
                            Math.min(Kirigami.Units.gridUnit * 6, promptInput.contentHeight + Kirigami.Units.smallSpacing * 2)
                        )

                        PlasmaComponents3.TextArea {
                            id: promptInput
                            placeholderText: root.activeThreadId
                                ? i18n("Ask Codex a follow-up… (Enter to send, Shift+Enter for newline)")
                                : i18n("Ask Codex anything… (Enter to send, Shift+Enter for newline)")
                            wrapMode: TextEdit.Wrap

                            Keys.onReturnPressed: (event) => {
                                if (event.modifiers & Qt.ShiftModifier) {
                                    event.accepted = false;
                                } else {
                                    event.accepted = true;
                                    const msg = promptInput.text;
                                    promptInput.text = "";
                                    root.sendMessage(msg);
                                }
                            }
                        }
                    }

                    PlasmaComponents3.Button {
                        id: sendBtn
                        Layout.alignment: Qt.AlignBottom
                        icon.name: root.isBusy ? "process-stop" : "document-send"
                        text: root.isBusy ? i18n("Stop") : i18n("Send")
                        enabled: root.isBusy || promptInput.text.trim().length > 0
                        onClicked: {
                            if (root.isBusy) {
                                root.stopGeneration();
                            } else {
                                const msg = promptInput.text;
                                promptInput.text = "";
                                root.sendMessage(msg);
                            }
                        }
                    }
                }
            }
        }
    }
}
