#!/usr/bin/env python3
"""Apply shell configuration independently of desktop/theme activation."""
import datetime
import os
import re
from pathlib import Path
import shlex
import shutil
import sys

SOURCE_LINE = 'source "$HOME/.config/soltros/zshrc"'


class KConfigText:
    """Edit individual plain keys while retaining KDE-specific syntax verbatim."""
    def __init__(self, path):
        self.lines = path.read_text().splitlines(keepends=True) if path.is_file() else []

    def get(self, section, key, fallback=None):
        current = None
        value = fallback
        for line in self.lines:
            stripped = line.strip()
            if stripped.startswith('[') and stripped.endswith(']'):
                current = stripped
            elif current == '[' + section + ']':
                name, separator, content = line.rstrip('\r\n').partition('=')
                if name.strip() == key and separator:
                    value = content
                elif name.strip() == key + '[$d]':
                    value = fallback
        return value

    def set(self, section, key, value):
        header = '[' + section + ']'
        current = None
        found = False
        insertion = None
        result = []
        managed_key = re.compile(re.escape(key) + r'(?:\[\$[^\]]+\])*(?:=.*)?$')
        for line in self.lines:
            stripped = line.strip()
            if stripped.startswith('[') and stripped.endswith(']'):
                if current == header:
                    insertion = len(result)
                current = stripped
                found = found or current == header
            if current == header and managed_key.fullmatch(stripped):
                continue
            result.append(line)
        if current == header:
            insertion = len(result)
        if not found:
            if result and not result[-1].endswith('\n'):
                result[-1] += '\n'
            result.extend(['\n', header + '\n'])
            insertion = len(result)
        elif insertion and not result[insertion - 1].endswith('\n'):
            result[insertion - 1] += '\n'
        result.insert(insertion, key + '=' + value + '\n')
        self.lines = result

    def text(self):
        return ''.join(self.lines)


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

    # Append a strong glyph fallback to the requested font before Fontconfig's
    # weak system fallbacks. This also covers Konsole profiles naming a font
    # directly (e.g. Hack), rather than the generic "monospace" family.
    write(home / '.config/fontconfig/conf.d/99-soltros-terminal-icons.conf', '''<?xml version="1.0"?>
<!DOCTYPE fontconfig SYSTEM "urn:fontconfig:fonts.dtd">
<fontconfig>
 <match target="pattern">
  <edit name="family" mode="append" binding="strong"><string>Symbols Nerd Font Mono</string></edit>
 </match>
</fontconfig>
''')

    # Qt/Konsole can retain a profile's explicit font instead of using generic
    # Fontconfig fallbacks. Select a patched text font in the default profile.
    konsolerc = home / '.config/konsolerc'
    terminal = KConfigText(konsolerc)
    profile_name = terminal.get('Desktop Entry', 'DefaultProfile', fallback='Soltros.profile')
    if Path(profile_name).name != profile_name or not profile_name.endswith('.profile'):
        profile_name = 'Soltros.profile'
    profile_path = home / '.local/share/konsole' / profile_name
    profile = KConfigText(profile_path if profile_path.is_file() else Path('/usr/share/konsole') / profile_name)
    if profile.get('General', 'Name') is None:
        profile.set('General', 'Name', 'Soltros')
    profile.set('General', 'Command', '/usr/bin/zsh')
    profile.set('General', 'Arguments', '/usr/bin/zsh')
    old_font = profile.get('Appearance', 'Font', fallback='monospace,11,-1,5,50,0,0,0,0,0')
    font_parts = old_font.split(',')
    font_parts[0] = 'Hack Nerd Font Mono'
    profile.set('Appearance', 'Font', ','.join(font_parts))
    write(profile_path, profile.text())
    terminal.set('Desktop Entry', 'DefaultProfile', profile_name)
    write(konsolerc, terminal.text())

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
