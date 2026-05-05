#!/bin/bash

# ==========================================
# GLOBAL CONFIGURATION & PACKAGE LISTS
# ==========================================
PURGE_MODE=false

# Ubuntu-specific package names and equivalents
APT_PACKAGES=(
    fish rsync jq btop ripgrep fd-find git-delta alien lm-sensors udisks2 
    udiskie linux-firmware powertop smartmontools usbutils pciutils fwupd 
    xwayland openssh-server libva-mesa-driver mesa-vulkan-drivers pipewire 
    pipewire-audio-client-libraries pipewire-pulse pipewire-jack wireplumber 
    playerctl libvirt-daemon-system libvirt-clients nmap iperf3 wireguard-tools 
    gamemode mangohud goverlay corectrl steam-devices exfatprogs ntfs-3g 
    btrfs-progs gimp deja-dup papirus-icon-theme snapd kdenlive kcalc 
    filelight ark okular libwebkit2gtk-4.1-dev libssl-dev curl wget file 
    libappindicator3-dev librsvg2-dev build-essential software-properties-common
    lutris libfuse2
)

FLATPAKS=(
    net.waterfox.waterfox com.discordapp.Discord com.github.tchx84.Flatseal
    com.bitwarden.desktop org.telegram.desktop it.mijorus.gearlever 
    org.gnome.World.PikaBackup org.videolan.VLC com.github.wwmm.easyeffects 
    io.github.dweymouth.supersonic io.github.dvlv.boxbuddyrs 
    de.leopoldluley.Clapgrep im.nheko.Nheko io.github.flattool.Ignition 
    io.github.flattool.Warehouse io.missioncenter.MissionCenter 
    com.vysp3r.ProtonPlus org.libretro.RetroArch
    com.github.iwalton3.jellyfin-media-player io.podman_desktop.PodmanDesktop 
    org.filezillaproject.Filezilla dev.zed.Zed io.github.shiftey.Desktop 
    org.gtk.Gtk3theme.Breeze org.gtk.Gtk3theme.adw-gtk3 
    org.gtk.Gtk3theme.adw-gtk3-dark org.gustavoperedo.FontDownloader
    sh.loft.devpod com.heroicgameslauncher.hgl org.prismlauncher.PrismLauncher
    org.blender.Blender org.audacityteam.Audacity org.inkscape.Inkscape
    com.github.hugolabe.Wike com.slack.Slack com.github.johnfactotum.Foliate 
    org.mozilla.Thunderbird org.nicotine_plus.Nicotine com.vscodium.codium 
    io.github.victoralvesf.aonsoku org.signal.Signal org.bleachbit.BleachBit 
    com.usebottles.bottles md.obsidian.Obsidian com.obsproject.Studio
)

# ==========================================
# ARGUMENT PARSING & ROOT CHECK
# ==========================================
while [[ "$#" -gt 0 ]]; do
    case $1 in
        --remove) PURGE_MODE=true ;;
        *) echo "Unknown parameter: $1"; exit 1 ;;
    esac
    shift
done

if [ "$EUID" -ne 0 ]; then 
  echo "Error: Please run as root (use sudo)"
  exit 1
fi

ACTUAL_USER=$SUDO_USER
USER_HOME=$(getent passwd "$ACTUAL_USER" | cut -d: -f6)

# ==========================================
# PURGE / REMOVE LOGIC
# ==========================================
if [ "$PURGE_MODE" = true ]; then
    echo -e "\033[0;31m⚠️  WARNING: Full Ubuntu System Purge Initiated.\033[0m"
    read -p "Are you absolutely sure? This removes Nix, Flatpaks, and specific APT configs. [y/N] " confirm
    [[ ! "$confirm" =~ ^[Yy]$ ]] && exit 0

    echo "Reverting shell to bash..."
    usermod -s /bin/bash "$ACTUAL_USER"
    
    echo "Uninstalling Nix..."
    if [ -d "/nix" ]; then
        /nix/nix-installer uninstall --no-confirm || rm -rf /nix
    fi
    rm -f /usr/local/bin/nixmanager
    rm -rf "$USER_HOME/.config/nixpkgs_ubuntu"
    
    echo "Purging Flatpaks..."
    flatpak uninstall -y --all 2>/dev/null
    flatpak uninstall --unused -y 2>/dev/null

    echo "Removing APT Packages and Repos..."
    apt purge -y "${APT_PACKAGES[@]}" 2>/dev/null
    add-apt-repository --remove -y ppa:kisak/kisak-mesa
    add-apt-repository --remove -y ppa:lutris-team/lutris
    rm -f /etc/apt/sources.list.d/tailscale.list
    rm -f /usr/share/keyrings/tailscale-archive-keyring.gpg
    
    apt autoremove -y
    echo "Purge complete. Please reboot."
    exit 0
fi

# ==========================================
# MAIN INSTALLATION ROUTINE
# ==========================================
echo "--- Starting Ubuntu 26.04 Workstation Setup ---"

# 0. Bootstrap Core
apt update && apt install -y git curl wget zsh tar unzip util-linux sudo apt-utils software-properties-common

# 1. Repository Configuration
echo "Adding PPAs and Architecture..."
dpkg --add-architecture i386
add-apt-repository -y ppa:kisak/kisak-mesa
add-apt-repository -y ppa:lutris-team/lutris

# Tailscale Repo
curl -fsSL https://pkgs.tailscale.com/stable/ubuntu/$(lsb_release -cs).noarmor.gpg | tee /usr/share/keyrings/tailscale-archive-keyring.gpg >/dev/null
curl -fsSL https://pkgs.tailscale.com/stable/ubuntu/$(lsb_release -cs).tailscale-repo.list | tee /etc/apt/sources.list.d/tailscale.list

# 2. Comprehensive APT Install
echo "Installing APT packages..."
apt update && apt upgrade -y
apt install -y "${APT_PACKAGES[@]}"

# 3. Permissions & Groups
echo "Setting user groups for Libvirt/KVM..."
usermod -aG libvirt,kvm,input "$ACTUAL_USER"

# 4. Flatpak Setup
echo "Configuring Flatpaks..."
flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
flatpak install -y flathub "${FLATPAKS[@]}"

# 5. Nix Package Manager Setup
echo "Installing Determinate Nix..."
if ! command -v nix &>/dev/null; then
    curl --proto '=https' --tlsv1.2 -sSf -L https://install.determinate.systems/nix | sh -s -- install --no-confirm
fi

# Create Ubuntu-specific Nix Flake
sudo -H -u "$ACTUAL_USER" mkdir -p "$USER_HOME/.config/nixpkgs_ubuntu"
sudo -H -u "$ACTUAL_USER" tee "$USER_HOME/.config/nixpkgs_ubuntu/flake.nix" > /dev/null << 'EOF'
{
  description = "nixpkgs-ubuntu custom flake";
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";
  outputs = { self, nixpkgs }: {
    legacyPackages.x86_64-linux = import nixpkgs {
      system = "x86_64-linux";
      config.allowUnfree = true;
    };
  };
}
EOF

# 6. Nixmanager CLI Tool
echo "Installing nixmanager..."
cat << 'EOF' > /usr/local/bin/nixmanager
#!/bin/bash
FLAKE_DIR="$HOME/.config/nixpkgs_ubuntu"
main() {
    case "${1:-help}" in
        install) nix profile add "$FLAKE_DIR#$2" ;;
        remove) nix profile remove "$2" ;;
        list) nix profile list ;;
        upgrade) nix profile upgrade ;;
        *) echo "Usage: nixmanager {install|remove|list|upgrade}" ;;
    esac
}
main "$@"
EOF
chmod +x /usr/local/bin/nixmanager

# 7. ZSH & Starship Setup
echo "Configuring Zsh and Starship..."
if [ ! -d "$USER_HOME/.oh-my-zsh" ]; then
    sudo -H -u "$ACTUAL_USER" sh -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)" "" --unattended
fi

# Plugin clones
ZSH_CUSTOM="$USER_HOME/.oh-my-zsh/custom/plugins"
sudo -H -u "$ACTUAL_USER" mkdir -p "$ZSH_CUSTOM"
[[ ! -d "$ZSH_CUSTOM/zsh-autosuggestions" ]] && sudo -H -u "$ACTUAL_USER" git clone https://github.com/zsh-users/zsh-autosuggestions "$ZSH_CUSTOM/zsh-autosuggestions"
[[ ! -d "$ZSH_CUSTOM/zsh-syntax-highlighting" ]] && sudo -H -u "$ACTUAL_USER" git clone https://github.com/zsh-users/zsh-syntax-highlighting "$ZSH_CUSTOM/zsh-syntax-highlighting"

# Starship Binary
if ! command -v starship &>/dev/null; then
    curl -sS https://starship.rs/install.sh | sh -s -- -y
fi

# Final .zshrc Generation
sudo -H -u "$ACTUAL_USER" tee "$USER_HOME/.zshrc" > /dev/null <<EOF
export ZSH="\$HOME/.oh-my-zsh"
ZSH_THEME="terminalparty"
plugins=(git zsh-autosuggestions zsh-syntax-highlighting)
source \$ZSH/oh-my-zsh.sh

# Load Nix
[ -e "/nix/var/nix/profiles/default/etc/profile.d/nix-daemon.sh" ] && . "/nix/var/nix/profiles/default/etc/profile.d/nix-daemon.sh"

# Aliases & Fixes
alias fd='fdfind'
alias update="sudo apt update && sudo apt upgrade -y && flatpak update -y"

# Paths
export PATH="\$PATH:\$HOME/.local/bin"
export EDITOR="nano"

# Theme
eval "\$(starship init zsh)"
EOF

# Set Zsh as default shell (Ubuntu path: /usr/bin/zsh)
usermod -s "$(command -v zsh)" "$ACTUAL_USER"

# 8. Pipewire Service Setup
echo "Enabling Pipewire user services..."
sudo -u "$ACTUAL_USER" systemctl --user enable --now pipewire.service pipewire-pulse.service wireplumber.service

# 9. Verification Audit
echo "--- Final System Audit ---"
for pkg in "${APT_PACKAGES[@]}"; do
    if ! dpkg-query -W -f='${Status}' "$pkg" 2>/dev/null | grep -q "ok installed"; then
        echo "Missing: $pkg. Attempting re-install..."
        apt install -y "$pkg"
    fi
done

echo "=========================================================="
echo "Setup Complete! Rebooting is highly recommended."
echo "NEXT STEPS:"
echo "1. Reboot and run 'tailscale up'."
echo "2. Enjoy Ubuntu 26.04!"
echo "=========================================================="
