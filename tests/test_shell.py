import contextlib
import importlib.util
import io
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import shell_settings
import install as installer


class ShellTests(unittest.TestCase):
    def configure(self, home):
        with patch.object(shell_settings.os, 'geteuid', return_value=1000), contextlib.redirect_stdout(io.StringIO()):
            shell_settings.configure_shell(ROOT, home)

    def test_configuration_preserves_personal_settings_and_moves_hook_last(self):
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder)
            original = 'export PERSONAL_SETTING=kept\n' + shell_settings.SOURCE_LINE + '\nPROMPT="old prompt"\n'
            (home / '.zshrc').write_text(original)
            self.configure(home)
            first = (home / '.zshrc').read_text()
            self.assertIn('export PERSONAL_SETTING=kept', first)
            self.assertEqual(first.count(shell_settings.SOURCE_LINE), 1)
            self.assertTrue(first.rstrip().endswith(shell_settings.SOURCE_LINE))
            self.configure(home)
            self.assertEqual((home / '.zshrc').read_text(), first)
            backups = list((home / '.local/state/ubuntu-post-installer/backups').glob('*/.zshrc'))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_text(), original)

    def test_existing_starship_configuration_is_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder)
            (home / '.config').mkdir()
            existing = 'format = "personal prompt"\n'
            (home / '.config/starship.toml').write_text(existing)
            self.configure(home)
            self.assertEqual((home / '.config/starship.toml').read_text(), existing)

    @unittest.skipUnless(shutil.which('zsh'), 'Zsh required for startup integration check')
    def test_interactive_zsh_loads_prompt_aliases_and_ubuntu_binary_names(self):
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder)
            binary = home / 'bin'
            binary.mkdir()
            for name in ['batcat', 'fdfind', 'rg', 'duf', 'eza']:
                p = binary / name
                p.write_text('#!/bin/sh\nexit 0\n')
                p.chmod(0o755)
            starship = binary / 'starship'
            real = os.environ.get('SOLTROS_TEST_STARSHIP')
            if real:
                starship.symlink_to(real)
            else:
                starship.write_text('#!/bin/sh\nif [ "$1" = init ]; then\n  printf \'export STARSHIP_SHELL=zsh\\nPROMPT=starship-prompt\\n\'\nfi\n')
                starship.chmod(0o755)
            (home / '.zshrc').write_text('PROMPT="old prompt"\n')
            self.configure(home)
            env = dict(os.environ, HOME=str(home), ZDOTDIR=str(home), PATH=str(binary) + ':/usr/bin:/bin', TERM='xterm-256color')
            # The standard CI image has batcat/fdfind, rather than bat/fd.
            script = '''[[ $STARSHIP_SHELL = zsh ]] && [[ $PROMPT = *starship* ]] || exit 21
[[ $aliases[ll] = 'eza -la --icons=auto --git' ]] || exit 22
[[ $aliases[apt-search] = 'apt-cache search' ]] || exit 23
[[ $aliases[cat] = *bat* ]] || exit 24
(( $+functions[urb] && $+functions[ufu] && $+functions[ufu-rebuild] )) || exit 25
alias-help | /usr/bin/grep -q apt-install || exit 26
[[ $path[1] = $HOME/.local/bin ]] || exit 27
print -r -- shell-startup-ok
'''
            result = subprocess.run(['zsh', '-i', '-c', script], env=env, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('shell-startup-ok', result.stdout)

    def test_shell_only_preview_has_no_network_or_processes(self):
        i = installer.Installer(installer.parse_args(['--shell-only', '--dry-run']))
        with patch.object(installer.subprocess, 'run', side_effect=AssertionError('command')), patch.object(installer.urllib.request, 'urlopen', side_effect=AssertionError('network')), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(i.main(), 0)

    def test_shell_is_applied_before_repository_failure(self):
        i = installer.Installer(installer.parse_args([]))
        i.account = SimpleNamespace(pw_uid=1000)
        calls = []
        i.shell = lambda: calls.append('shell')
        i.antigravity = lambda: calls.append('antigravity')
        def fail_repo():
            calls.append('repo')
            raise RuntimeError('unpublished')
        i.check_soltros_release = fail_repo
        i.system = lambda: self.fail('system stage should not run')
        i.write = lambda *args: None
        with tempfile.TemporaryDirectory() as folder:
            i.cache, i.state, i.backup = [Path(folder) / name for name in ['cache', 'state', 'backups']]
            with patch.object(installer.os, 'geteuid', return_value=0), patch.object(installer, 'os_release', return_value={'ID': 'ubuntu', 'VERSION_ID': '26.10'}), patch.object(installer.subprocess, 'check_output', return_value='amd64'), patch.object(installer.shutil, 'which', return_value='/usr/bin/mock'), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(i.main(), 1)
        self.assertEqual(calls, ['shell', 'antigravity', 'repo'])

    def test_sudo_antigravity_switches_to_desktop_account(self):
        i = installer.Installer(installer.parse_args(['--antigravity-only']))
        i.account = SimpleNamespace(pw_uid=1000)
        calls = []
        i.run = lambda *args, **kwargs: calls.append((args, kwargs))
        with patch.object(installer.os, 'geteuid', return_value=0):
            i.antigravity()
        self.assertTrue(calls[0][1]['user'])
        self.assertEqual(calls[0][0][1].name, 'install-antigravity.sh')

    def test_antigravity_only_does_not_require_apt_or_desktop(self):
        i = installer.Installer(installer.parse_args(['--antigravity-only']))
        calls = []
        i.antigravity = lambda: calls.append('cli')
        with patch.object(installer, 'os_release', side_effect=AssertionError('desktop check')), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(i.main(), 0)
        self.assertEqual(calls, ['cli'])


if __name__ == '__main__':
    unittest.main()
