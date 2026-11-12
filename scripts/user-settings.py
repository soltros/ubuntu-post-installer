#!/usr/bin/env python3
"""Install desktop settings as the logged-in user, preserving existing shell config."""
import datetime
import os
from pathlib import Path
import shutil
import subprocess
import sys


def install(root, home):
    if os.geteuid() == 0:
        raise RuntimeError('User settings must run without root privileges')
    stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    backup = home / '.local/state/ubuntu-post-installer/backups' / stamp

    def write(path, text):
        if path.exists() and path.read_text() == text:
            return
        if path.exists():
            dest = backup / path.relative_to(home)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dest)
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_name(path.name + '.soltros-tmp')
        temp.write_text(text)
        temp.replace(path)

    # Back up files touched by the preserved Plasma activation script.
    for name in ['kdeglobals', 'kwinrc', 'plasmarc', 'kcminputrc', 'kglobalshortcutsrc',
                 'gtk-3.0/settings.ini', 'gtk-4.0/settings.ini']:
        p = home / '.config' / name
        if p.is_file():
            b = backup / '.config' / name
            b.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, b)
    assets = root / 'assets/user'
    for source in assets.rglob('*'):
        if source.is_file():
            text = source.read_text().replace('${HOME}', str(home))
            write(home / source.relative_to(assets), text)
    base = home / '.local/share/ubuntu-setup'
    kde_source = Path('/usr/share/soltros/themes/kde')
    if kde_source.exists():
        kde_work = home / '.cache/ubuntu-post-installer/kde'
        shutil.copytree(kde_source, kde_work, dirs_exist_ok=True)
        subprocess.run(['bash', 'install.sh', '-q', '-n', '1', '13', '1', 'auto'], cwd=kde_work, check=True)
    omz = Path('/usr/share/soltros/themes/ohmyzsh')
    if omz.exists() and not (home / '.oh-my-zsh').exists():
        shutil.copytree(omz, home / '.oh-my-zsh')
    subprocess.run(['python3', str(base / 'fresh/configure.py'), str(home), str(base / 'fresh/catppuccin-mocha.json')], check=True)
    service_wants = home / '.config/systemd/user/default.target.wants'
    service_wants.mkdir(parents=True, exist_ok=True)
    ydotool = service_wants / 'ydotool.service'
    if not ydotool.exists() and not ydotool.is_symlink():
        ydotool.symlink_to('/usr/lib/systemd/user/ydotool.service')
    gnupg = home / '.gnupg'
    gnupg.mkdir(mode=0o700, exist_ok=True)
    agent_conf = gnupg / 'gpg-agent.conf'
    agent = agent_conf.read_text() if agent_conf.exists() else ''
    if 'enable-ssh-support' not in agent.splitlines():
        write(agent_conf, agent.rstrip() + '\nenable-ssh-support\n')
    managed = home / '.config/soltros/zshrc'
    write(managed, '''export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
export SSH_AUTH_SOCK="$(gpgconf --list-dirs agent-ssh-socket)"
export EDITOR=nano
export VISUAL=nano
autoload -Uz compinit && compinit
[ ! -r /usr/share/zsh-autosuggestions/zsh-autosuggestions.zsh ] || source /usr/share/zsh-autosuggestions/zsh-autosuggestions.zsh
export ZSH="$HOME/.oh-my-zsh"
plugins=(git sudo)
ZSH_THEME=""
[ ! -r "$ZSH/oh-my-zsh.sh" ] || source "$ZSH/oh-my-zsh.sh"
alias cat='bat --paging=never'
alias grep=rg
alias find=fd
alias df=duf
alias ls='eza --icons=auto'
alias ll='eza -la --icons=auto --git'
alias tree='eza --tree --icons=auto'
alias aliases='alias'
alias alises='alias'
alias alias-help='alias'
alias update='sudo apt-get update && sudo apt-get upgrade'
command -v starship >/dev/null && eval "$(starship init zsh)"
''')
    zshrc = home / '.zshrc'
    current = zshrc.read_text() if zshrc.exists() else ''
    source_line = 'source "$HOME/.config/soltros/zshrc"'
    if source_line not in current:
        write(zshrc, current.rstrip() + '\n\n# Managed Kubuntu desktop settings\n' + source_line + '\n')
    write(home / '.config/fontconfig/conf.d/60-soltros.conf', '''<?xml version="1.0"?>
<!DOCTYPE fontconfig SYSTEM "urn:fontconfig:fonts.dtd">
<fontconfig>
 <alias><family>sans-serif</family><prefer><family>Inter</family><family>Noto Sans</family><family>DejaVu Sans</family></prefer></alias>
 <alias><family>serif</family><prefer><family>Noto Serif</family><family>DejaVu Serif</family></prefer></alias>
 <alias><family>monospace</family><prefer><family>Roboto Mono</family><family>Symbols Nerd Font</family><family>Hack</family><family>DejaVu Sans Mono</family></prefer></alias>
 <match target="pattern"><edit name="rgba" mode="assign"><const>rgb</const></edit><edit name="hintstyle" mode="assign"><const>hintslight</const></edit></match>
</fontconfig>
''')
    write(home / '.config/systemd/user/soltros-desktop.service', f'''[Unit]
Description=Apply Soltros Plasma desktop settings
After=graphical-session.target
PartOf=graphical-session.target
[Service]
Type=oneshot
ExecStart=/bin/bash "{base}/plasma-settings.sh"
[Install]
WantedBy=graphical-session.target
''')
    applet = base / 'chatgpt-plasmoid'
    subprocess.run(['bash', str(applet / 'install.sh')], check=True)
    # Run settings in-session; login service reapplies them on subsequent logins.
    subprocess.run(['bash', str(base / 'plasma-settings.sh')], check=True)
    subprocess.run(['fc-cache', '-f'], check=True)
    print('Desktop settings installed. Backups:', backup)


if __name__ == '__main__':
    install(Path(sys.argv[1]).resolve(), Path.home())
