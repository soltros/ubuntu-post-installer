A comprehensive post-installation shell script optimized for Ubuntu Workstation (specifically tested for Ubuntu 26.04 LTS). 

This script handles repository configuration, multi-manager package installations (APT, Flatpak, Nix), user environment customization, and includes built-in verification loops to ensure reliable deployments.

## Features & Architecture

* **Repository Bootstrapping**: Initializes core utilities before enabling essential Third-Party PPAs (Kisak Mesa for graphics and Lutris) and the Tailscale repository.
* **Failsafe Package Management**: Implements an active verification phase. It checks the installation status of all requested APT and Flatpak packages and automatically retries any that failed due to temporary mirror sync issues or network timeouts.
* **Nix Package Manager Integration**: 
    * Installs Nix via the Determinate Systems installer for modern, reliable management.
    * Configures a local, hidden flake (`~/.config/nixpkgs_ubuntu`) with unfree packages enabled.
    * Generates `nixmanager`, a custom CLI wrapper located in `/usr/local/bin`, simplifying standard package operations (`install`, `remove`, `list`, `upgrade`).
* **Environment & Shell**: 
    * Configures Zsh as the default shell (correctly mapping to `/usr/bin/zsh`).
    * Installs Oh My Zsh and essential plugins (autosuggestions, syntax-highlighting) for the calling user.
    * Integrates **Starship** for a cross-shell prompt experience.
* **Software Provisioning**: 
    * *Core CLI tools*: fish, zsh, starship, btop, ripgrep, jq, fd-find.
    * *System utilities*: Tailscale, full PipeWire stack (audio/pulse/jack), libvirt/KVM, fwupd, snapd.
    * *Gaming tools*: Steam, MangoHud, GameMode, CoreCtrl, Lutris.
    * *Flatpaks*: Enables Flathub and installs a comprehensive suite including Discord, Waterfox, Obsidian, Signal, and Aonsoku.
* **Compatibility Layer**: Automatically handles Ubuntu-specific naming quirks (e.g., aliasing `fdfind` to `fd`) to ensure Fedora-trained muscle memory remains intact.

## Usage

The script must be run locally. It relies on `$SUDO_USER` to properly configure personal files and environments, so it must be executed via `sudo` rather than from a direct root shell.

1. Clone the repository and navigate into the directory:
```bash
git clone https://github.com/soltros/ubuntu-post-installer.git
cd ubuntu-post-installer
```

2. Make the script executable:
```bash
chmod +x run.sh
```

3. Execute the script:
```bash
sudo ./run.sh
```

### Optional Arguments

* **System Purge**: To revert the environment, remove Nix, uninstall Flatpaks/APT packages, and rollback the shell to Bash:
  ```bash
  sudo ./run.sh --remove
  ```
  *(Note: This requires a manual confirmation prompt before executing the teardown).*

## Important Notes

* **Privilege Handling**: Do not run this script by logging in as root (e.g., `su -`). You must run it as your standard user via `sudo ./run.sh`. The script extracts your actual username to correctly map the Zsh, Nix, and Flatpak configurations to your home directory.
* **Ubuntu Naming Conventions**: Some packages differ from Fedora. For example, the script installs `fd-find` and creates an alias so you can still use the `fd` command.
* **PipeWire Setup**: The script explicitly enables PipeWire user services via `systemctl --user` to ensure audio works immediately upon login.
* **Reboot**: A system reboot is mandatory after the script completes to properly apply kernel updates, user group changes (especially for `libvirt` and `kvm`), systemd services, and the default shell swap.
```
