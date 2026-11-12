# Soltros Kubuntu workstation

Apply Derrik’s AMD desktop profile to an existing **Kubuntu 26.10 amd64** installation. `run.sh` installs applications, configures services, and applies the Plasma desktop settings. Run it again to reapply the managed configuration.

Applications come from Kubuntu’s APT repositories, [Soltros Ubuntu Packages](https://github.com/soltros/ubuntu_packages), or official vendor `.deb` downloads. The post-installer does not compile applications or build packages. Flatpak is used only for the explicitly listed apps that have no supported Debian package candidate.

## Run

```bash
sudo apt update
sudo apt install git python3 gnupg

git clone https://github.com/soltros/ubuntu-post-installer.git
cd ubuntu-post-installer
bash run.sh --dry-run
sudo bash run.sh
```

**Repository prerequisite:** the package repository must publish a signed **`apt-stonking`** release first. Its current configuration lists only `noble` and `resolute`, and no release was published when this installer was prepared. The installer checks the 26.10 release, its signature, suite, expiry and any previously installed signing key before changing system settings. It refuses to substitute a different Ubuntu release’s packages. Follow the package repository’s maintainer instructions to publish the matching release; this repository does not generate signing keys or publish application packages.

Run from your normal desktop account using `sudo`. Another existing account can be selected with `sudo bash run.sh --user derrik`. The installer uses that account’s actual home directory and does not create accounts, set passwords, repartition disks, modify mounts, change the hostname, replace the bootloader, remove existing software or automatically reboot.

To prohibit every Flatpak fallback:

```bash
sudo bash run.sh --no-flatpak
```

To reapply just the user settings from your Plasma session:

```bash
bash run.sh --user-settings
```

This last command expects the packages and theme resources to have been installed already.

## What gets configured

| Area | Configuration |
|---|---|
| Desktop | Existing Plasma 6 / Wayland, SDDM, Catppuccin Mocha Blue, Papirus Dark, dark GTK settings, cursors and Kvantum resources |
| Fonts | Inter, Roboto Mono, Symbols Nerd Font, Noto/CJK/emoji, Hack, Fira Code and the desktop font preferences |
| Audio | PipeWire/Pulse compatibility, 48 kHz and a fixed 1024-frame quantum |
| AMD desktop | Mesa/Vulkan including i386 libraries, OpenCL, firmware, AMD performance kernel parameters and performance CPU governor |
| USB/Bluetooth | Runtime power-control rules, Bluetooth dual mode, automatic adapter power and ERTM option |
| Services | NetworkManager, Bluetooth, CUPS, SSH, Docker, libvirt, Tailscale and a weekly scrub of mounted Btrfs filesystems |
| Gaming | Steam, GameMode settings and Steam firewall rules when UFW is installed; firewall enablement is preserved |
| User | Zsh, git/sudo plugins, autosuggestions, Starship, utility aliases, workspace directory and necessary device/virtualization groups |
| Plasma extras | ChatGPT/Codex widget, Fresh theme, dictation and TV shortcuts, and the Durandal launcher configuration |
| Locale | `America/Detroit`, `en_US.UTF-8`, existing keyboard layout preserved (Kubuntu’s normal US layout matches the profile) |

The profile is intended for the AMD desktop. It applies desktop-oriented power settings, opens SSH, grants Docker and device-group access, and changes managed Plasma preferences. Review `--dry-run` and the configuration files before applying it elsewhere.

The dictation, TV and Durandal launchers reference `voxtype`, `~/.local/bin/tv-bigpicture-toggle`, and `hermes`. Those programs were not supplied by the active source desktop profile; they must exist separately for those launchers to work. Account credentials, application data, browser profiles and SSH keys are not copied from another installation.

## Package sources

- [`config/apt.txt`](config/apt.txt): distribution packages. These package names were checked against the 26.10 archive; installed candidates are checked again at runtime.
- [`config/soltros-apt.txt`](config/soltros-apt.txt): `chatgpt`, `sharpemu`, `waterfox`, `termsmith`, `vpn-manager`, `brave-browser`, `recomplauncher`, `codex`, `lichii`, and `xenia`, installed directly from your APT repository.
- [`config/vendor-debs.json`](config/vendor-debs.json): official Debian downloads for Fresh, Bitwarden, Zettlr, Discord and BrowserOS. A configured APT candidate takes priority; otherwise the checksum-locked vendor `.deb` is installed with APT so dependencies and removal remain package-managed.
- Spotify, Kopia and Tailscale use their official signed APT repositories.
- [`config/optional-apt.txt`](config/optional-apt.txt): additional packages checked in configured repositories. Missing candidates are listed as parity gaps rather than silently replaced. This currently includes Antigravity, dotool, caffeine-ng, Adapta and xpadneo.

### Last-resort Flatpaks

APT is checked first **on every run** for each of these names. A Flatpak is installed only when no APT candidate exists. These are the only configured exceptions; `--no-flatpak` reports them as missing instead.

| Application | APT name checked first | Last-resort app ID | Reason |
|---|---|---|---|
| RuneLite | `runelite` | `net.runelite.RuneLite` | Official Linux release is a JAR/AppImage |
| Bolt | `bolt-launcher` | `com.adamcake.Bolt` | Official release is a ZIP |
| RPCS3 | `rpcs3` | `net.rpcs3.RPCS3` | Official Linux binary is an AppImage |
| xemu | `xemu` | `app.xemu.xemu` | No verified 26.10 Debian repository found |
| Telegram | `telegram-desktop` | `org.telegram.desktop` | Official tarball; absent from the 26.10 archive |
| Ghidra | `ghidra` | `org.ghidra_sre.Ghidra` | Official release is a ZIP |
| Pinta | `pinta` | `com.github.PintaProject.Pinta` | Absent from the 26.10 archive; no supported vendor DEB found |

The fallback policy is conservative: a generic third-party DEB for an older release is not treated as verified 26.10 support. Add future Debian packages to your APT repository and the installer will prefer them automatically. It does not remove an already installed Flatpak when an APT package becomes available.

## Updates and configuration

Normal packaged updates:

```bash
sudo apt update
sudo apt upgrade
```

If fallback apps were installed, update those with `sudo flatpak update`.

Refresh the post-installer and reapply configuration with:

```bash
git pull --ff-only
sudo bash run.sh
```

Vendor download pins and the checksum-locked theme/font resources are maintained in this repository; they change when their manifests are updated. No development-kernel PPA or graphics-driver PPA is enabled. Kubuntu’s supported kernel and GRUB remain in use.

System files are backed up before changes under `/var/backups/ubuntu-post-installer/<timestamp>/`. User configuration backups live under `~/.local/state/ubuntu-post-installer/backups/`. Existing `.zshrc` content is preserved and a managed configuration is sourced once. The Plasma login service reapplies managed appearance preferences each login.

Review `/var/lib/ubuntu-post-installer/last-report.json` after a run:

- Exit **0**: installation finished and no package gaps were found.
- Exit **1**: an installation/configuration operation failed, or a prerequisite was unavailable. Preflight failures are printed before system changes.
- Exit **2**: managed setup completed but packages in the parity report are unavailable. `--allow-gaps` changes only this exit status; it does not hide failures or missing packages.

Reboot after reviewing the report. Authenticate Tailscale with `sudo tailscale up` and Codex with `codex login`. Existing Secure Boot settings are retained; VirtualBox or controller DKMS packages may require the normal MOK enrollment process.

## Validation

```bash
python3 -m unittest discover -s tests -v
bash -n run.sh
bash run.sh --dry-run
```

CI checks script syntax, manifest consistency, archive extraction, vendor checksum rejection, fallback decisions and a harmless preview. The installation has not been exercised on a complete Kubuntu desktop VM here; GPU, display-manager, Secure Boot and interactive desktop behavior require a real-machine/VM run. A signed 26.10 package release is also required before an end-to-end installation can succeed.
