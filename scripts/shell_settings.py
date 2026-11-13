#!/usr/bin/env python3
"""Apply shell configuration independently of desktop/theme activation."""
import configparser
import io
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

    def config(path):
        parser = configparser.ConfigParser(interpolation=None, strict=False)
        parser.optionxform = str
        if path.is_file():
            parser.read(path)
        return parser

    def save_config(path, parser):
        output = io.StringIO()
        parser.write(output, space_around_delimiters=False)
        write(path, output.getvalue())

    # Qt/Konsole can retain a profile's explicit font instead of using generic
    # Fontconfig fallbacks. Select a patched text font in the default profile.
    konsolerc = home / '.config/konsolerc'
    terminal = config(konsolerc)
    profile_name = terminal.get('Desktop Entry', 'DefaultProfile', fallback='Soltros.profile')
    if Path(profile_name).name != profile_name or not profile_name.endswith('.profile'):
        profile_name = 'Soltros.profile'
    profile_path = home / '.local/share/konsole' / profile_name
    profile = config(profile_path if profile_path.is_file() else Path('/usr/share/konsole') / profile_name)
    if not profile.has_section('General'):
        profile.add_section('General')
    if not profile.has_option('General', 'Name'):
        profile.set('General', 'Name', 'Soltros')
    if not profile.has_section('Appearance'):
        profile.add_section('Appearance')
    old_font = profile.get('Appearance', 'Font', fallback='monospace,11,-1,5,50,0,0,0,0,0')
    font_parts = old_font.split(',')
    font_parts[0] = 'Hack Nerd Font Mono'
    profile.set('Appearance', 'Font', ','.join(font_parts))
    save_config(profile_path, profile)
    if not terminal.has_section('Desktop Entry'):
        terminal.add_section('Desktop Entry')
    terminal.set('Desktop Entry', 'DefaultProfile', profile_name)
    save_config(konsolerc, terminal)

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
