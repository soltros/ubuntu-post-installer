import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import org.kde.kcmutils as KCM

KCM.SimpleKCM {
    id: configPage

    property alias cfg_defaultModel: modelField.text
    property alias cfg_sandboxMode: sandboxCombo.currentValue
    property alias cfg_defaultCwd: cwdField.text
    property alias cfg_focusInputOnOpen: focusInputCheck.checked
    property alias cfg_popupWidth: popupWidthSpin.value
    property alias cfg_popupHeight: popupHeightSpin.value

    Kirigami.FormLayout {
        QQC2.TextField {
            id: modelField
            Kirigami.FormData.label: i18n("Default Codex Model:")
            Layout.fillWidth: true
            placeholderText: "default (or e.g. gpt-6.1-sol, gpt-5.6-sol)"
        }

        QQC2.ComboBox {
            id: sandboxCombo
            Kirigami.FormData.label: i18n("Sandbox Mode:")
            model: ["workspace-write", "read-only", "danger-full-access"]
            textRole: ""
            valueRole: ""
        }

        QQC2.TextField {
            id: cwdField
            Kirigami.FormData.label: i18n("Working Directory:")
            Layout.fillWidth: true
            placeholderText: "/home/derrik"
        }

        QQC2.CheckBox {
            id: focusInputCheck
            Kirigami.FormData.label: i18n("Behavior:")
            text: i18n("Automatically focus prompt box when opening widget")
        }

        RowLayout {
            Kirigami.FormData.label: i18n("Default Popup Size:")
            spacing: Kirigami.Units.smallSpacing

            QQC2.SpinBox {
                id: popupWidthSpin
                from: 380
                to: 1600
                stepSize: 20
            }

            QQC2.Label {
                text: "×"
            }

            QQC2.SpinBox {
                id: popupHeightSpin
                from: 440
                to: 1400
                stepSize: 20
            }

            QQC2.Label {
                text: i18n("px")
            }
        }
    }
}
