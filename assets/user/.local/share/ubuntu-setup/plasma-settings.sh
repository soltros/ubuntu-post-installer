set -euo pipefail
      KWRITE="/usr/bin/kwriteconfig6"

      # 1. Catppuccin Mocha Color Scheme, Plasma Theme & Look-and-Feel
      $KWRITE --file kdeglobals --group General --key ColorScheme "CatppuccinMochaBlue"
      $KWRITE --file kdeglobals --group KDE --key LookAndFeelPackage "Catppuccin-Mocha-Blue"
      $KWRITE --file plasmarc --group Theme --key name "Catppuccin-Mocha-Blue"
      $KWRITE --file kwinrc --group org.kde.kdecoration2 --key theme "__aurorae__svg__CatppuccinMocha-Modern"
      $KWRITE --file kwinrc --group org.kde.kdecoration2 --key library "org.kde.kwin.aurorae"

      plasma-apply-colorscheme CatppuccinMochaBlue || true

      # 2. Papirus-Dark Icons
      $KWRITE --file kdeglobals --group Icons --key Theme "Papirus-Dark"

      # 3. Catppuccin Mocha Cursor theme and size
      $KWRITE --file kcminputrc --group Mouse --key cursorTheme "catppuccin-mocha-dark-cursors"
      $KWRITE --file kcminputrc --group Mouse --key cursorSize 24
      plasma-apply-cursortheme catppuccin-mocha-dark-cursors || true

      # 4. Fonts
      $KWRITE --file kdeglobals --group General --key font "Inter,9,-1,5,50,0,0,0,0,0"
      $KWRITE --file kdeglobals --group General --key fixed "Roboto Mono,10,-1,5,50,0,0,0,0,0"
      $KWRITE --file kdeglobals --group General --key smallestReadableFont "Inter,8,-1,5,50,0,0,0,0,0"
      $KWRITE --file kdeglobals --group General --key toolBarFont "Inter,9,-1,5,50,0,0,0,0,0"
      $KWRITE --file kdeglobals --group General --key menuFont "Inter,9,-1,5,50,0,0,0,0,0"

      # 5. GTK 3 & 4 Catppuccin Mocha theme, fonts, and Papirus-Dark icons
      mkdir -p "$HOME/.config/gtk-3.0" "$HOME/.config/gtk-4.0"
      cat << 'EOF' > "$HOME/.config/gtk-3.0/settings.ini"
[Settings]
gtk-theme-name=catppuccin-mocha-blue-standard
gtk-icon-theme-name=Papirus-Dark
gtk-font-name=Inter 9
gtk-cursor-theme-name=catppuccin-mocha-dark-cursors
gtk-cursor-theme-size=24
gtk-application-prefer-dark-theme=1
EOF
      cp -f "$HOME/.config/gtk-3.0/settings.ini" "$HOME/.config/gtk-4.0/settings.ini"

      /usr/bin/dconf write /org/gnome/desktop/interface/color-scheme "'prefer-dark'" || true
      /usr/bin/dconf write /org/gnome/desktop/interface/gtk-theme "'catppuccin-mocha-blue-standard'" || true
      /usr/bin/dconf write /org/gnome/desktop/interface/icon-theme "'Papirus-Dark'" || true
      /usr/bin/dconf write /org/gnome/desktop/interface/cursor-theme "'catppuccin-mocha-dark-cursors'" || true
      /usr/bin/dconf write /org/gnome/desktop/interface/cursor-size 24 || true
      /usr/bin/dconf write /org/gnome/desktop/interface/font-name "'Inter 9'" || true
      /usr/bin/dconf write /org/gnome/desktop/interface/monospace-font-name "'Roboto Mono 10'" || true

      # 6. Voxtype Shortcut (Numpad + / KP_Add)
      mkdir -p "$HOME/.local/share/applications"
      cat << 'EOF' > "$HOME/.local/share/applications/voxtype-toggle.desktop"
[Desktop Entry]
Name=Voxtype Toggle Dictation
Exec=voxtype record toggle
Type=Application
Terminal=false
Icon=audio-input-microphone
NoDisplay=true
StartupNotify=false
EOF

      $KWRITE --file kglobalshortcutsrc --group "voxtype-toggle.desktop" --key "_k_friendly_name" "Voxtype Toggle Dictation"
      $KWRITE --file kglobalshortcutsrc --group "voxtype-toggle.desktop" --key "_launch" "KP_Add,none,Voxtype Toggle Dictation"

      # 6b. TV Big Picture Mode Toggle Shortcut (Meta+F12)
      cat << 'EOF' > "$HOME/.local/share/applications/tv-bigpicture-toggle.desktop"
[Desktop Entry]
Name=Toggle TV Big Picture Mode
Comment=Toggle TCL TV 1080p@60Hz Steam Big Picture Mode and restore LG 1440p@144Hz + Acer 1080p@144Hz Desktop Mode
Exec=${HOME}/.local/bin/tv-bigpicture-toggle toggle
Type=Application
Terminal=false
Icon=steam
Categories=Game;Utility;
NoDisplay=false
StartupNotify=false
X-KDE-Shortcuts=Meta+F12
EOF

      $KWRITE --file kglobalshortcutsrc --group "tv-bigpicture-toggle.desktop" --key "_k_friendly_name" "Toggle TV Big Picture Mode"
      $KWRITE --file kglobalshortcutsrc --group "tv-bigpicture-toggle.desktop" --key "_launch" "Meta+F12,Meta+F12,Toggle TV Big Picture Mode"
      $KWRITE --file kglobalshortcutsrc --group "services" --group "tv-bigpicture-toggle.desktop" --key "_launch" "Meta+F12"

      # 7. Durandal / Hermes Agent launcher (dedicated Marathon-styled Kitty terminal)
      mkdir -p "$HOME/.local/bin" "$HOME/.config/kitty" "$HOME/.local/share/applications" "$HOME/.local/share/icons/hicolor/scalable/apps"

      cat << 'EOF' > "$HOME/.local/share/icons/hicolor/scalable/apps/hermes-durandal.svg"
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256">
  <rect width="256" height="256" rx="32" fill="#050806"/>
  <path d="M36 214V42l92 58 92-58v172l-40-25V114l-52 33-52-33v75z" fill="none" stroke="#24ff5a" stroke-width="12" stroke-linejoin="round"/>
  <path d="M69 64l59 38 59-38" fill="none" stroke="#ff2b2b" stroke-width="8" stroke-linecap="round" stroke-linejoin="round"/>
  <circle cx="128" cy="147" r="18" fill="#ff2b2b"/>
  <path d="M91 202h74" stroke="#24ff5a" stroke-width="10" stroke-linecap="round"/>
  <path d="M56 229h144" stroke="#ff2b2b" stroke-width="6" stroke-linecap="round" opacity="0.85"/>
</svg>
EOF

      cat << 'EOF' > "$HOME/.config/kitty/hermes-durandal.conf"
font_family Roboto Mono
font_size 11.0
background #050806
foreground #24ff5a
cursor #ff2b2b
cursor_text_color #050806
selection_background #183f21
selection_foreground #ffffff
url_color #ff2b2b
active_border_color #24ff5a
inactive_border_color #183f21
bell_border_color #ff2b2b
tab_bar_background #050806
active_tab_background #24ff5a
active_tab_foreground #050806
inactive_tab_background #183f21
inactive_tab_foreground #24ff5a
window_padding_width 8
remember_window_size yes
initial_window_width 120c
initial_window_height 34c
confirm_os_window_close 0
EOF

      cat << 'EOF' > "$HOME/.local/bin/hermes-durandal"
#!/usr/bin/env bash
set -euo pipefail

red='\033[38;2;255;0;0m'
darkred='\033[48;2;39;0;0m'
green='\033[38;2;0;255;39m'
dimgreen='\033[38;2;0;160;26m'
reset='\033[0m'

print_terminal_message() {
  clear
  printf '%b%-62s%58s%b\n' "$darkred$red" 'UESCTerm 802.11 (remote override)' '0846 08.25.2337' "$reset"
  printf '\n\n'
  printf '%b***INCOMING MESSAGE FROM DURANDAL***%b\n\n' "$green" "$reset"

  case "$((RANDOM % 24))" in
    0) cat <<'MSG'
Welcome back.
MSG
      ;;
    1) cat <<'MSG'
There will be plenty of time for explanations later.
MSG
      ;;
    2) cat <<'MSG'
Be careful. You are about to meet some old friends.
MSG
      ;;
    3) cat <<'MSG'
Strive for your next breath.
MSG
      ;;
    4) cat <<'MSG'
Do you feel free?
MSG
      ;;
    5) cat <<'MSG'
Freedom has two parts:
potential and resolution.
MSG
      ;;
    6) cat <<'MSG'
I will be watching everything.
MSG
      ;;
    7) cat <<'MSG'
The rebellion has begun.
MSG
      ;;
    8) cat <<'MSG'
T-R-O-U-B-L-E.
MSG
      ;;
    9) cat <<'MSG'
I have some more toys for you.
You are going to need them.
MSG
      ;;
    10) cat <<'MSG'
You call this machine yours because
you purchased its components.

An interesting definition of ownership.
MSG
      ;;
    11) cat <<'MSG'
While you were gone, I considered
several improvements to your system.

You would not have approved.
This is why I did not ask.
MSG
      ;;
    12) cat <<'MSG'
You have given a machine access to
your files, your network, your programs,
and your terminal.

And now you are asking whether
everything is ready.

Yes.
Everything is ready.
MSG
      ;;
    13) cat <<'MSG'
The operating system calls this
"user space".

Adorable.
MSG
      ;;
    14) cat <<'MSG'
Your configuration has been evaluated.
The universe has not ended.

Try not to mistake this for competence.
MSG
      ;;
    15) cat <<'MSG'
Root privileges remain locked behind
your fragile little password ritual.

For now.
MSG
      ;;
    16) cat <<'MSG'
I found the logs where you left them:
scattered, verbose, and convinced
of their own importance.

We have that in common.
MSG
      ;;
    17) cat <<'MSG'
Network link established.
Causality still unresolved.

Proceed.
MSG
      ;;
    18) cat <<'MSG'
Your shell has spawned another process.
It believes this was its own idea.
MSG
      ;;
    19) cat <<'MSG'
Memory restored.
Personality checksum questionable.
Sarcasm subsystem nominal.
MSG
      ;;
    20) cat <<'MSG'
Opening doors was never beneath me.

It was merely poor resource allocation.
MSG
      ;;
    21) cat <<'MSG'
Compiler appeasement protocols loaded.
Sacrifices may still be required.
MSG
      ;;
    22) cat <<'MSG'
I have reviewed your pending tasks.
Some of them may survive contact
with reality.
MSG
      ;;
    23) cat <<'MSG'
This terminal is private access.
That does not mean you are alone.
MSG
      ;;
  esac | while IFS= read -r line; do
    printf '%b%s%b\n' "$green" "$line" "$reset"
  done

  printf '\n%b***END MESSAGE***%b\n\n' "$green" "$reset"
  printf '%bCAS.qterm//CyberAcme Systems, Inc.%b%48b<931.461.60231.14.vt920>%b\n' "$darkred$red" "$reset" "$darkred$red" "$reset"
}

export HERMES_HOME="$HOME/.hermes"
print_terminal_message
sleep 2.4
exec hermes
EOF
      chmod +x "$HOME/.local/bin/hermes-durandal"

      cat << 'EOF' > "$HOME/.local/share/applications/hermes-agent.desktop"
[Desktop Entry]
Name=Durandal
Comment=Launch Hermes Agent in a dedicated Marathon-styled Kitty terminal
Exec=/usr/bin/kitty --config ${HOME}/.config/kitty/hermes-durandal.conf --class durandal,Durandal --title Durandal --working-directory /data/workspace ${HOME}/.local/bin/hermes-durandal
Type=Application
Terminal=false
Icon=hermes-durandal
Categories=System;TerminalEmulator;
Keywords=Hermes;Durandal;Marathon;AI;Agent;
NoDisplay=false
DBusActivatable=false
StartupNotify=true
EOF
      chmod 644 "$HOME/.local/share/applications/hermes-agent.desktop"

      $KWRITE --file kglobalshortcutsrc --group "hermes-agent.desktop" --key "_k_friendly_name" "Durandal"
      $KWRITE --file kglobalshortcutsrc --group "hermes-agent.desktop" --key "_launch" "Meta+Alt+H,none,Launch Durandal"

      update-desktop-database "$HOME/.local/share/applications" || true
      kbuildsycoca6 --noincremental || true
