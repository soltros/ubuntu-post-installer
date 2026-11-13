import contextlib
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import flatpak_desktop


class FlatpakDesktopTests(unittest.TestCase):
    def test_plasma_environment_keeps_custom_paths_and_deduplicates_on_repeat(self):
        for original in ['', '/opt/custom/share:/usr/share']:
            with self.subTest(original=original), tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / 'env.sh'
                path.write_text(flatpak_desktop.SESSION_ENV)
                env = dict(os.environ, HOME=folder, XDG_DATA_HOME=folder + '/custom-data', XDG_DATA_DIRS=original)
                result = subprocess.check_output(['bash', '-c', '. "$1"; . "$1"; printf %s "$XDG_DATA_DIRS"', 'test', str(path)], env=env, text=True)
                paths = result.split(':')
                for required in [folder + '/custom-data/flatpak/exports/share', '/var/lib/flatpak/exports/share']:
                    self.assertEqual(paths.count(required), 1)
                for preserved in (original or '/usr/local/share:/usr/share').split(':'):
                    self.assertIn(preserved, paths)

    def test_repair_is_repeatable_and_refreshes_cache_as_current_user(self):
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder)
            with patch.dict(os.environ, {'XDG_DATA_HOME': str(home / 'data')}), patch.object(flatpak_desktop.os, 'geteuid', return_value=1000), patch.object(flatpak_desktop.shutil, 'which', return_value='/usr/bin/kbuildsycoca6'), patch.object(flatpak_desktop.subprocess, 'run') as run, contextlib.redirect_stdout(io.StringIO()):
                flatpak_desktop.configure_flatpak_desktop(home)
                flatpak_desktop.configure_flatpak_desktop(home)
            self.assertTrue((home / 'data/flatpak/exports/share/applications').is_dir())
            self.assertEqual((home / '.config/plasma-workspace/env/90-soltros-flatpak.sh').read_text(), flatpak_desktop.SESSION_ENV)
            self.assertEqual(run.call_count, 2)
            self.assertIn('kbuildsycoca6 --noincremental', run.call_args.args[0][2])
            self.assertFalse((home / '.local/state/ubuntu-post-installer/backups').exists())
