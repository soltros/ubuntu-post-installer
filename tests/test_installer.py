import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('installer', ROOT / 'scripts/install.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class InstallerTests(unittest.TestCase):
    def installer(self, *args):
        return mod.Installer(mod.parse_args(list(args)))

    def test_preview_has_no_commands_or_network(self):
        with patch.object(mod.subprocess, 'run', side_effect=AssertionError('command executed')), patch.object(mod.urllib.request, 'urlopen', side_effect=AssertionError('network used')):
            self.assertEqual(self.installer('--dry-run').main(), 0)

    def test_unpublished_repository_stops_before_writes(self):
        i = self.installer()
        with patch.object(mod.urllib.request, 'urlopen', side_effect=urllib.error.HTTPError('url', 404, 'not found', {}, None)), patch.object(i, 'write', side_effect=AssertionError('file written')):
            with self.assertRaisesRegex(RuntimeError, 'apt-stonking'):
                i.check_soltros_release()

    def test_all_apt_candidates_prevent_flatpak_commands(self):
        i = self.installer()
        calls = []
        i.available = lambda _: True
        i.apt = lambda packages: calls.extend(packages)
        i.run = lambda *a, **k: self.fail('fallback command executed')
        i.install_fallbacks()
        self.assertEqual(len(calls), len(json.loads((ROOT / 'config/fallbacks.json').read_text())))
        self.assertEqual(i.fallbacks, [])

    def test_prohibited_fallback_records_gaps_without_installing(self):
        i = self.installer('--no-flatpak')
        i.available = lambda _: False
        i.run = lambda *a, **k: self.fail('command executed')
        i.install_fallbacks()
        self.assertIn('rpcs3', i.gaps)
        self.assertEqual(i.fallbacks, [])

    def test_one_missing_deb_installs_only_its_documented_fallback(self):
        i = self.installer()
        calls = []
        i.available = lambda name: name != 'runelite'
        i.apt = lambda _: None
        i.run = lambda *args, **kwargs: calls.append(args)
        i.install_fallbacks()
        installs = [c for c in calls if c[:2] == ('flatpak', 'install')]
        self.assertEqual(len(installs), 1)
        self.assertEqual(installs[0][-1], 'net.runelite.RuneLite')

    def test_tar_traversal_and_device_are_rejected(self):
        for name, kind in [('../escape', tarfile.REGTYPE), ('device', tarfile.CHRTYPE)]:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temp:
                temp = Path(temp)
                archive = temp / 'bad.tar'
                with tarfile.open(archive, 'w') as tar:
                    info = tarfile.TarInfo(name)
                    info.type = kind
                    tar.addfile(info)
                with self.assertRaises(ValueError):
                    mod.safe_extract(archive, temp / 'unpack')

    def test_tar_escaping_link_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp)
            archive = temp / 'bad.tar'
            with tarfile.open(archive, 'w') as tar:
                info = tarfile.TarInfo('link')
                info.type = tarfile.SYMTYPE
                info.linkname = '../../escape'
                tar.addfile(info)
            with self.assertRaises(ValueError):
                mod.safe_extract(archive, temp / 'unpack')

    def test_zip_valid_internal_symlink_and_escape(self):
        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp)
            archive = temp / 'good.zip'
            with zipfile.ZipFile(archive, 'w') as z:
                z.writestr('theme/value', 'ok')
                link = zipfile.ZipInfo('theme/link')
                link.create_system = 3
                link.external_attr = (0o120777 << 16)
                z.writestr(link, 'value')
            mod.safe_unzip(archive, temp / 'good')
            self.assertEqual((temp / 'good/theme/link').read_text(), 'ok')
            with zipfile.ZipFile(archive, 'w') as z:
                z.writestr('../escape', 'bad')
            with self.assertRaises(ValueError):
                mod.safe_unzip(archive, temp / 'bad')

    def test_custom_apps_only_use_apt(self):
        i = self.installer()
        packages = []
        i.apt = lambda names: packages.extend(names)
        i.available = lambda name: False
        i.install_fallbacks = lambda: None
        i.run = lambda *a, **k: self.fail('Direct application download attempted')
        i.apps()
        for name in ['fresh-editor', 'bitwarden', 'zettlr', 'discord', 'browserclaw', 'xemu']:
            self.assertIn(name, packages)
        self.assertFalse((ROOT / 'config/vendor-debs.json').exists())

    def test_backup_write_is_repeatable_and_does_not_follow_symlink(self):
        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp)
            i = self.installer()
            i.backup = temp / 'backups'
            target, managed = temp / 'other', temp / 'managed'
            target.write_text('original')
            managed.symlink_to(target)
            i.write(managed, 'new')
            i.write(managed, 'new')
            self.assertEqual(target.read_text(), 'original')
            self.assertFalse(managed.is_symlink())
            self.assertEqual(managed.read_text(), 'new')
            backup = i.backup / str(managed).lstrip('/')
            self.assertEqual(backup.read_text(), 'original')

    def test_manifests_are_unique_https_and_checksum_locked(self):
        for filename in ['apt.txt', 'soltros-apt.txt', 'optional-apt.txt']:
            items = mod.lines(filename)
            self.assertEqual(len(items), len(set(items)), filename)
        for filename in ['themes.json']:
            for item in json.loads((ROOT / 'config' / filename).read_text()):
                self.assertTrue(item['url'].startswith('https://'))
                self.assertRegex(item['sha256'], r'^[0-9a-f]{64}$')
        self.assertNotIn('flatpak', mod.lines('apt.txt'))


if __name__ == '__main__':
    unittest.main()
