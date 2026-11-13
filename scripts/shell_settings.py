#!/usr/bin/env python3
"""Apply shell configuration independently of desktop/theme activation."""
import datetime
import os
from pathlib import Path
import shlex
import shutil
import sys

SOURCE_LINE = 'source "$HOME/.config/soltros/zshrc"'


def configure_shell(root, home):
    if os.geteuid() == 0:
        raise RuntimeError('Shell settings must be written as the desktop user')
    stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    backup = home / '.local/state/ubuntu-post-installer/backups' / stamp

    def write(path, content):
        if path.exists() and path.read_text() == content:
            return
        if path.exists():
            dest = backup / path.relative_to(home)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dest)
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_name(path.name + '.soltros-tmp')
        temp.write_text(content)
        temp.replace(path)

    framework = Path('/usr/share/soltros/themes/ohmyzsh')
    if framework.exists() and not (home / '.oh-my-zsh').exists():
        shutil.copytree(framework, home / '.oh-my-zsh')
    config = 'export SOLTROS_INSTALLER_DIR=' + shlex.quote(str(root.resolve())) + '\n'
    config += (root / 'assets/zsh/soltros.zsh').read_text()
    write(home / '.config/soltros/zshrc', config)
    rc = home / '.zshrc'
    current = rc.read_text() if rc.exists() else ''
    # Move our exact hook to the end so existing prompts cannot override it.
    # Preserve all other personal settings, and migrate the previous hook.
    filtered = [line for line in current.splitlines() if line.strip() not in {
        SOURCE_LINE, '# Managed Kubuntu desktop settings', '# Managed Soltros shell settings'}]
    result = '\n'.join(filtered).rstrip() + '\n\n# Managed Soltros shell settings\n' + SOURCE_LINE + '\n'
    write(rc, result)
    starship = home / '.config/starship.toml'
    if not starship.exists():
        write(starship, '# Use the standard Starship prompt and modules.\nadd_newline = true\n')
    print('Zsh configuration installed. Open a new terminal or run exec zsh. Backups:', backup)


if __name__ == '__main__':
    configure_shell(Path(sys.argv[1]).resolve(), Path.home())
