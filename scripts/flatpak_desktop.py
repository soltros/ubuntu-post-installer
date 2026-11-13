#!/usr/bin/env python3
"""Restore Flatpak desktop discovery for Plasma, as the desktop user."""
import datetime
import os
from pathlib import Path
import shutil
import subprocess

SESSION_ENV = '''# Keep Flatpak launchers visible to Plasma and its application watcher.
export XDG_DATA_DIRS="${XDG_DATA_DIRS:-/usr/local/share:/usr/share}"
for soltros_flatpak_share in "${XDG_DATA_HOME:-$HOME/.local/share}/flatpak/exports/share" /var/lib/flatpak/exports/share; do
    case ":$XDG_DATA_DIRS:" in
        *":$soltros_flatpak_share:"*) ;;
        *) XDG_DATA_DIRS="$soltros_flatpak_share:$XDG_DATA_DIRS" ;;
    esac
done
export XDG_DATA_DIRS
unset soltros_flatpak_share
'''


def configure_flatpak_desktop(home):
    if os.geteuid() == 0:
        raise RuntimeError('Run Flatpak desktop setup without sudo, as your desktop user.')
    path = home / '.config/plasma-workspace/env/90-soltros-flatpak.sh'
    if not path.exists() or path.read_text() != SESSION_ENV:
        if path.exists():
            stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
            backup = home / '.local/state/ubuntu-post-installer/backups' / stamp / path.relative_to(home)
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, backup)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + '.tmp')
        temporary.write_text(SESSION_ENV)
        temporary.replace(path)
    path.chmod(0o755)
    # Create the user export directory before Plasma starts watching it.
    data_home = Path(os.environ.get('XDG_DATA_HOME') or home / '.local/share')
    (data_home / 'flatpak/exports/share/applications').mkdir(parents=True, exist_ok=True)
    if shutil.which('kbuildsycoca6'):
        subprocess.run(['bash', '-c', '. "$1"; exec kbuildsycoca6 --noincremental', 'flatpak-desktop', str(path)], check=True)
    print('Flatpak paths configured for Plasma. Log out and back in once to apply the session environment.')


if __name__ == '__main__':
    configure_flatpak_desktop(Path.home())
