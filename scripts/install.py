#!/usr/bin/env python3
"""Apply the b450m-d3sh desktop profile to an existing Kubuntu 26.10 install."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import pwd
import shlex
import shutil
import subprocess
import sys
import tarfile
import urllib.request
from email.utils import parsedate_to_datetime
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SOLTROS_BASE = 'https://github.com/soltros/ubuntu_packages/releases/download/apt-stonking'


def lines(name):
    return [s.strip() for s in (ROOT / 'config' / name).read_text().splitlines()
            if s.strip() and not s.startswith('#')]


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dry-run', action='store_true', help='Print plan without changing anything or using the network')
    p.add_argument('--user', help='Existing desktop user (defaults to sudo caller)')
    p.add_argument('--no-flatpak', action='store_true', help='Report DEB-unavailable apps instead of installing their fallback')
    p.add_argument('--allow-gaps', action='store_true', help='Exit zero despite documented gaps; failures still exit nonzero')
    p.add_argument('--antigravity-only', action='store_true', help='Install the official Antigravity CLI as the desktop user, without system setup')
    p.add_argument('--shell-only', action='store_true', help='Install and repair Zsh, Starship and aliases without the application repository or desktop themes')
    p.add_argument('--user-settings', action='store_true', help='Apply desktop settings only, as your normal user')
    return p.parse_args(argv)


def os_release(path=Path('/etc/os-release')):
    return dict(line.split('=', 1)[0:2] for line in path.read_text().replace('"', '').splitlines() if '=' in line)


def safe_extract(archive, destination):
    """Do not permit an upstream archive to write outside the staging directory."""
    destination = destination.resolve()
    with tarfile.open(archive) as tar:
        for m in tar.getmembers():
            dest = (destination / m.name).resolve()
            if not dest.is_relative_to(destination) or m.isdev() or m.isfifo():
                raise ValueError(f'Unsafe archive member: {m.name}')
            if m.issym() or m.islnk():
                base = dest.parent if m.issym() else destination
                if not (base / m.linkname).resolve().is_relative_to(destination):
                    raise ValueError(f'Unsafe archive link: {m.name}')
        tar.extractall(destination, filter='data')


def safe_unzip(archive, destination):
    destination = destination.resolve()
    with zipfile.ZipFile(archive) as z:
        for m in z.infolist():
            target = (destination / m.filename).resolve()
            if not target.is_relative_to(destination):
                raise ValueError(f'Unsafe ZIP member: {m.filename}')
            if (m.external_attr >> 16) & 0o170000 == 0o120000:
                link = z.read(m).decode()
                if not (target.parent / link).resolve().is_relative_to(destination):
                    raise ValueError(f'Unsafe ZIP link: {m.filename}')
                target.parent.mkdir(parents=True, exist_ok=True)
                target.symlink_to(link)
            elif m.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(z.read(m))
                target.chmod((m.external_attr >> 16) & 0o777 or 0o644)


def merge_resource_tree(source, destination):
    """Overlay managed resources without following old destination symlinks."""
    source, destination = Path(source), Path(destination)
    if destination.is_symlink():
        destination.unlink()
    destination.mkdir(parents=True, exist_ok=True)
    for item in source.iterdir():
        target = destination / item.name
        if item.is_symlink():
            # copytree(dirs_exist_ok=True, symlinks=True) still calls symlink()
            # on existing links, which fails on the second installer run.
            if target.is_symlink() or target.is_file():
                target.unlink()
            target.symlink_to(os.readlink(item))
        elif item.is_dir():
            merge_resource_tree(item, target)
        else:
            if target.is_symlink():
                target.unlink()
            shutil.copy2(item, target)


class Installer:
    def __init__(self, args):
        self.args = args
        self.user = args.user or os.environ.get('SUDO_USER') or pwd.getpwuid(os.getuid()).pw_name
        self.account = pwd.getpwnam(self.user)
        self.home = Path(self.account.pw_dir)
        self.failures = []
        self.gaps = {}
        self.fallbacks = []
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
        self.backup = Path('/var/backups/ubuntu-post-installer') / stamp
        self.cache = Path('/var/cache/ubuntu-post-installer')
        self.state = Path('/var/lib/ubuntu-post-installer')

    def run(self, *cmd, user=False, check=True, capture=False, **kwargs):
        cmd = list(map(str, cmd))
        if user:
            cmd = ['runuser', '-u', self.user, '--', 'env', f'HOME={self.home}',
                   f'XDG_RUNTIME_DIR=/run/user/{self.account.pw_uid}',
                   f'DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/{self.account.pw_uid}/bus'] + cmd
        print('+', shlex.join(cmd), flush=True)
        return subprocess.run(cmd, check=check, text=True, capture_output=capture, **kwargs)

    def attempt(self, label, action):
        try:
            action()
        except (subprocess.SubprocessError, OSError, ValueError, RuntimeError) as exc:
            self.failures.append(f'{label}: {exc}')
            print(f'FAILED: {label}: {exc}', file=sys.stderr, flush=True)

    def write(self, path, text, mode=0o644):
        p = Path(path)
        if p.exists() and p.read_text() == text:
            return
        if p.exists() or p.is_symlink():
            b = self.backup / str(p).lstrip('/')
            b.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, b, follow_symlinks=True)
        p.parent.mkdir(parents=True, exist_ok=True)
        # Replace symlinks rather than following their target when managing files.
        with tempfile.NamedTemporaryFile(mode='w', dir=p.parent, delete=False) as f:
            f.write(text)
        os.chmod(f.name, mode)
        os.replace(f.name, p)

    def apt(self, packages):
        available = []
        for package in packages:
            policy = self.run('apt-cache', 'policy', package, capture=True).stdout
            if 'Candidate:' not in policy or 'Candidate: (none)' in policy:
                self.failures.append(f'APT package has no candidate: {package}')
            else:
                available.append(package)
        if available:
            # A dependency conflict is fatal: do not continue with an unknown base.
            self.run('apt-get', 'install', '-y', *available)

    def repository(self, name, key_url, entry):
        key = self.cache / (name + '.asc')
        self.run('curl', '--fail', '--location', '--retry', '3', '--proto', '=https', key_url, '-o', key)
        if b'-----BEGIN PGP' in key.read_bytes():
            self.run('gpg', '--batch', '--yes', '--dearmor', '--output', self.cache / (name + '.gpg'), key)
        else:
            shutil.copyfile(key, self.cache / (name + '.gpg'))
        keypath = Path('/etc/apt/keyrings') / (name + '.gpg')
        keypath.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(self.cache / (name + '.gpg'), keypath)
        keypath.chmod(0o644)
        self.write(f'/etc/apt/sources.list.d/{name}.list', entry + '\n')

    def check_soltros_release(self):
        # Check the application repository after the independent shell phase.
        # Refuse application/system setup if the target release is unpublished. Never substitute another Ubuntu suite.
        try:
            with urllib.request.urlopen(SOLTROS_BASE + '/soltros-archive-keyring.asc', timeout=30) as response:
                key = response.read()
            with urllib.request.urlopen(SOLTROS_BASE + '/InRelease', timeout=30) as response:
                signed = response.read()
        except OSError as exc:
            raise RuntimeError('Publish the signed apt-stonking release in soltros/ubuntu_packages first. The application/system stage has not been applied. ' + str(exc)) from exc
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            public = tmp / 'key.gpg'
            subprocess.run(['gpg', '--batch', '--yes', '--dearmor', '--output', str(public)], input=key, check=True)
            release = tmp / 'InRelease'
            release.write_bytes(signed)
            env = dict(os.environ, GNUPGHOME=str(tmp))
            subprocess.run(['gpgv', '--keyring', str(public), str(release)], check=True, env=env)
            info = signed.decode()
            if 'Codename: stonking' not in info.splitlines():
                raise RuntimeError('The signed package repository is not for Kubuntu 26.10 (stonking).')
            expiry = next((line.split(': ', 1)[1] for line in info.splitlines() if line.startswith('Valid-Until: ')), None)
            if expiry and parsedate_to_datetime(expiry) <= datetime.datetime.now(datetime.timezone.utc):
                raise RuntimeError('The signed Soltros APT index has expired. Refresh it in the package repository first.')
            current = Path('/etc/apt/keyrings/soltros.gpg')
            if current.exists():
                def fingerprint(path):
                    data = subprocess.check_output(['gpg', '--batch', '--show-keys', '--with-colons', str(path)], env=env, text=True)
                    return next(line.split(':')[9] for line in data.splitlines() if line.startswith('fpr:'))
                if fingerprint(public) != fingerprint(current):
                    raise RuntimeError('The Soltros signing key changed. Verify the key rotation before replacing the installed keyring.')
        self.soltros_key = key

    def antigravity(self):
        script = ROOT / 'scripts/install-antigravity.sh'
        if os.geteuid() == 0:
            if self.account.pw_uid == 0:
                raise RuntimeError('Select a non-root desktop account with --user, or run without sudo.')
            self.run('bash', script, user=True)
        else:
            if os.getuid() != self.account.pw_uid:
                raise RuntimeError('Use sudo with --user to install for a different desktop account.')
            self.run('bash', script)

    def set_default_shell(self):
        desired = '/usr/bin/zsh'
        if os.path.realpath(pwd.getpwnam(self.user).pw_shell) != os.path.realpath(desired):
            self.run('usermod', '-s', desired, self.user)
        actual = pwd.getpwnam(self.user).pw_shell
        if os.path.realpath(actual) != os.path.realpath(desired):
            raise RuntimeError(f'Login shell for {self.user} is still {actual}; expected {desired}.')
        print(f'Default login shell verified for {self.user}: {actual}. Log out of Plasma and back in to refresh SHELL.')

    def shell(self):
        self.run('apt-get', 'update')
        self.run('apt-get', 'install', '-y', 'software-properties-common', 'ca-certificates', 'curl')
        self.run('add-apt-repository', '-y', 'universe')
        self.run('apt-get', 'update')
        self.run('apt-get', 'install', '-y', *lines('shell-apt.txt'))
        self.set_default_shell()
        self.run('starship', '--version')
        resources = json.loads((ROOT / 'config/themes.json').read_text())
        # Icons are a shell dependency, including --shell-only and unpublished APT.
        symbols = next(item for item in resources if item['name'] == 'nerd-fonts')
        self.theme(symbols)
        terminal_font = next(item for item in resources if item['name'] == 'terminal-font')
        self.theme(terminal_font)
        self.run('fc-cache', '-f')
        framework = next(item for item in resources if item['name'] == 'ohmyzsh')
        self.attempt('Oh My Zsh framework', lambda: self.theme(framework))
        self.run('python3', ROOT / 'scripts/shell_settings.py', ROOT, user=True)
        self.run('zsh', '-ic', '[[ "$STARSHIP_SHELL" = zsh ]] && command -v starship && alias ll && alias apt-search && whence -w urb', user=True)

    def system(self):
        self.run('dpkg', '--add-architecture', 'i386')
        self.run('apt-get', 'update')
        self.run('apt-get', 'install', '-y', 'software-properties-common', 'curl', 'ca-certificates', 'gpg')
        for component in ['universe', 'multiverse']:
            self.run('add-apt-repository', '-y', component)
        key = self.cache / 'soltros.asc'
        key.write_bytes(self.soltros_key)
        self.run('gpg', '--batch', '--yes', '--dearmor', '--output', self.cache / 'soltros.gpg', key)
        Path('/etc/apt/keyrings').mkdir(parents=True, exist_ok=True)
        shutil.copyfile(self.cache / 'soltros.gpg', '/etc/apt/keyrings/soltros.gpg')
        Path('/etc/apt/keyrings/soltros.gpg').chmod(0o644)
        self.write('/etc/apt/sources.list.d/soltros.list', f'deb [arch=amd64 signed-by=/etc/apt/keyrings/soltros.gpg] {SOLTROS_BASE} ./\n')
        self.repository('tailscale', 'https://pkgs.tailscale.com/stable/ubuntu/stonking.noarmor.gpg',
            'deb [signed-by=/etc/apt/keyrings/tailscale.gpg] https://pkgs.tailscale.com/stable/ubuntu stonking main')
        self.repository('spotify', 'https://download.spotify.com/debian/pubkey_5384CE82BA52C83A.asc',
            'deb [arch=amd64 signed-by=/etc/apt/keyrings/spotify.gpg] https://repository.spotify.com stable non-free')
        self.repository('kopia', 'https://kopia.io/signing-key',
            'deb [signed-by=/etc/apt/keyrings/kopia.gpg] https://packages.kopia.io/apt/ stable main')
        self.run('apt-get', 'update')
        self.apt(lines('apt.txt') + ['tailscale', 'kopia', 'kopia-ui', 'spotify-client'])
        for source, target in [('fdfind', 'fd'), ('batcat', 'bat')]:
            if shutil.which(source) and not shutil.which(target):
                Path('/usr/local/bin').mkdir(parents=True, exist_ok=True)
                Path('/usr/local/bin', target).symlink_to(shutil.which(source))
        for group in ['input', 'uinput', 'video', 'render', 'docker', 'libvirt', 'kvm', 'vboxusers', 'gamemode']:
            self.run('groupadd', '-f', group)
            self.run('usermod', '-aG', group, self.user)
        self.run('timedatectl', 'set-timezone', 'America/Detroit')
        self.run('locale-gen', 'en_US.UTF-8')
        self.run('update-locale', 'LANG=en_US.UTF-8')
        configs = {
            '/etc/sysctl.d/90-soltros.conf': 'vm.vfs_cache_pressure=50\nvm.swappiness=10\nnet.ipv4.conf.all.rp_filter=2\nnet.ipv4.conf.default.rp_filter=2\n',
            '/etc/udev/rules.d/90-soltros-power.rules': 'ACTION=="add|change", SUBSYSTEM=="usb", TEST=="power/control", ATTR{power/control}="on"\nACTION=="add|change", SUBSYSTEM=="pci", TEST=="power/control", ATTR{power/control}="on"\n',
            '/etc/udev/rules.d/90-soltros-uinput.rules': 'KERNEL=="uinput", GROUP="uinput", MODE="0660", OPTIONS+="static_node=uinput"\n',
            '/etc/modules-load.d/soltros.conf': 'amdgpu\nuinput\nkvm-amd\n',
            '/etc/initramfs-tools/conf.d/soltros': 'MODULES=most\n',
            '/etc/modprobe.d/soltros.conf': 'options bluetooth disable_ertm=Y\nblacklist fglrx\n',
            '/etc/pipewire/pipewire.conf.d/90-rpcs3-audio-stability.conf': 'context.properties = {\n default.clock.rate = 48000\n default.clock.allowed-rates = [ 48000 ]\n default.clock.quantum = 1024\n default.clock.min-quantum = 1024\n default.clock.max-quantum = 1024\n}\n',
            '/etc/gamemode.ini': '[general]\nrenice=10\nsoftrealtime=auto\n',
            '/etc/environment.d/90-soltros.conf': 'ROC_ENABLE_PRE_VEGA=1\n',
            '/etc/default/grub.d/90-soltros.cfg': 'GRUB_CMDLINE_LINUX_DEFAULT="$GRUB_CMDLINE_LINUX_DEFAULT amd_pstate=active pcie_aspm=off transparent_hugepage=never usbcore.autosuspend=-1 radeon.si_support=0 radeon.cik_support=0 amdgpu.si_support=1 amdgpu.cik_support=1 quiet splash loglevel=3 rd.systemd.show_status=auto rd.udev.log_level=3 udev.log_priority=3"\n',
            '/etc/systemd/system/soltros-performance.service': '[Unit]\nDescription=Set performance CPU governor\nAfter=local-fs.target\n[Service]\nType=oneshot\nExecStart=/usr/bin/cpupower frequency-set -g performance\nRemainAfterExit=yes\n[Install]\nWantedBy=multi-user.target\n',
            '/etc/tmpfiles.d/soltros.conf': f'd /data/workspace 0755 {self.user} {self.account.pw_gid} -\n',
        }
        # Kubuntu uses GRUB; keep its disk layout and bootloader.
        for path, value in configs.items():
            self.write(path, value)
        import configparser
        bluetooth = Path('/etc/bluetooth/main.conf')
        settings = configparser.ConfigParser(strict=False, interpolation=None)
        settings.optionxform = str
        if bluetooth.exists():
            settings.read(bluetooth)
        for section, key, value in [('General', 'ControllerMode', 'dual'), ('Policy', 'AutoEnable', 'true')]:
            if not settings.has_section(section):
                settings.add_section(section)
            settings.set(section, key, value)
        import io
        stream = io.StringIO()
        settings.write(stream)
        self.write(bluetooth, stream.getvalue())
        if shutil.which('ufw'):
            for rule in [('22/tcp',), ('27015/tcp',), ('27015/udp',), ('27031:27036/udp',), ('27036:27037/tcp',), ('27040/tcp',)]:
                self.run('ufw', 'allow', *rule)
        self.write('/usr/local/lib/soltros-btrfs-scrub.py', """import json, subprocess
result = subprocess.run(['findmnt', '--json', '-t', 'btrfs', '-o', 'UUID,TARGET'], text=True, capture_output=True)
if result.returncode not in (0, 1):
    result.check_returncode()
mounts = json.loads(result.stdout or '{}')
seen = set()
def scrub(items):
    for item in items:
        uuid = item.get('uuid')
        if uuid and uuid not in seen:
            subprocess.run(['btrfs', 'scrub', 'start', '-B', item['target']], check=True)
            seen.add(uuid)
        scrub(item.get('children', []))
scrub(mounts.get('filesystems', []))
""")
        self.write('/etc/systemd/system/soltros-btrfs-scrub.service', '[Unit]\nDescription=Scrub mounted Btrfs filesystems\n[Service]\nType=oneshot\nExecStart=/usr/bin/python3 /usr/local/lib/soltros-btrfs-scrub.py\n')
        self.write('/etc/systemd/system/soltros-btrfs-scrub.timer', '[Unit]\nDescription=Weekly Btrfs scrub\n[Timer]\nOnCalendar=weekly\nPersistent=true\n[Install]\nWantedBy=timers.target\n')
        self.run('systemd-tmpfiles', '--create', '/etc/tmpfiles.d/soltros.conf')
        self.run('sysctl', '--system')
        self.run('udevadm', 'control', '--reload-rules')
        self.run('systemctl', 'daemon-reload')
        self.run('systemctl', 'enable', '--now', 'soltros-btrfs-scrub.timer')
        # The desktop profile disables power-profiles-daemon, but does not disable sleep.
        self.run('systemctl', 'disable', '--now', 'power-profiles-daemon.service', check=False)
        for service in ['NetworkManager', 'bluetooth', 'cups', 'ssh', 'docker', 'libvirtd', 'tailscaled', 'sddm']:
            # SDDM changes apply on the next boot, avoiding killing the current session.
            self.attempt(service, lambda s=service: self.run('systemctl', 'enable', *([] if s == 'sddm' else ['--now']), s))
        self.attempt('performance service', lambda: self.run('systemctl', 'enable', '--now', 'soltros-performance.service'))
        self.run('modprobe', 'uinput')
        self.run('update-initramfs', '-u')
        self.run('update-grub')
        self.run('install', '-d', '-o', self.user, '-g', self.account.pw_gid, '/data/workspace')

    def available(self, package):
        result = self.run('apt-cache', 'policy', package, capture=True).stdout
        return 'Candidate:' in result and 'Candidate: (none)' not in result

    def apps(self):
        self.apt(lines('soltros-apt.txt'))
        for name in lines('optional-apt.txt'):
            if self.available(name):
                self.apt([name])
            else:
                self.gaps[name] = 'No Debian package candidate in the configured Kubuntu 26.10 repositories.'
        self.install_fallbacks()

    def install_fallbacks(self):
        fallback_initialized = False
        for item in json.loads((ROOT / 'config/fallbacks.json').read_text()):
            if self.available(item['apt']):
                self.apt([item['apt']])
                continue
            if self.args.no_flatpak:
                self.gaps[item['apt']] = item['reason'] + ' Fallback disabled.'
                continue
            if not fallback_initialized:
                self.run('apt-get', 'install', '-y', 'flatpak')
                self.run('flatpak', 'remote-add', '--system', '--if-not-exists', 'flathub', 'https://dl.flathub.org/repo/flathub.flatpakrepo')
                fallback_initialized = True
            self.attempt(item['apt'], lambda app=item['flatpak']: self.run('flatpak', 'install', '--system', '-y', '--noninteractive', 'flathub', app))
            self.fallbacks.append(item)

    def themes(self):
        for spec in json.loads((ROOT / 'config/themes.json').read_text()):
            if spec['name'] in ['nerd-fonts', 'terminal-font', 'ohmyzsh']:
                continue  # Already installed by the shell stage.
            self.attempt('theme ' + spec['name'], lambda item=spec: self.theme(item))

    def theme(self, spec):
        # Themes are static resources; no application packages are built here.
        path = self.cache / spec['sha256']
        if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != spec['sha256']:
            self.run('curl', '-fL', '--retry', '3', '--proto', '=https', spec['url'], '-o', path)
        if hashlib.sha256(path.read_bytes()).hexdigest() != spec['sha256']:
            raise ValueError('Theme SHA256 mismatch: ' + spec['name'])
        if spec['format'] == 'font':
            dest = Path('/usr/local/share/fonts/RobotoMono.ttf')
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, dest)
            return
        with tempfile.TemporaryDirectory() as temp:
            unpack = Path(temp) / 'unpack'
            unpack.mkdir()
            if spec['format'] == 'zip':
                safe_unzip(path, unpack)
            else:
                safe_extract(path, unpack)
            source = next((p for p in unpack.iterdir() if p.is_dir()), unpack)
            name = spec['name']
            targets = {
                'gtk': '/usr/share/themes/catppuccin-mocha-blue-standard',
                'cursors': '/usr/share/icons/catppuccin-mocha-dark-cursors',
                'sddm': '/usr/share/sddm/themes/catppuccin-mocha-blue',
                'nerd-fonts': '/usr/local/share/fonts/soltros-symbols',
                'terminal-font': '/usr/local/share/fonts/soltros-terminal',
                'kde': '/usr/share/soltros/themes/kde',
                'ohmyzsh': '/usr/share/soltros/themes/ohmyzsh',
                'kvantum': '/usr/share/Kvantum/catppuccin-mocha-blue',
                'plymouth': '/usr/share/plymouth/themes/catppuccin-mocha',
            }
            if name in ['nerd-fonts', 'terminal-font']:
                source = unpack
            if name in ['kvantum', 'plymouth']:
                source /= 'themes/catppuccin-mocha' + ('-blue' if name == 'kvantum' else '')
            merge_resource_tree(source, targets[name])
            if name == 'sddm':
                self.write('/etc/sddm.conf.d/90-soltros.conf', '[Theme]\nCurrent=catppuccin-mocha-blue\n[General]\nDisplayServer=wayland\n')
            if name == 'plymouth':
                theme = '/usr/share/plymouth/themes/catppuccin-mocha/catppuccin-mocha.plymouth'
                self.run('update-alternatives', '--install', '/usr/share/plymouth/themes/default.plymouth', 'default.plymouth', theme, '100')
                self.run('update-alternatives', '--set', 'default.plymouth', theme)
                self.run('update-initramfs', '-u')

    def user_files(self):
        # All user file writes happen under the user's UID, including backups.
        self.run('python3', ROOT / 'scripts/user-settings.py', ROOT, user=True)
        unit = self.home / '.config/systemd/user/soltros-desktop.service'
        self.run('systemctl', '--user', 'daemon-reload', user=True, check=False)
        wants = self.home / '.config/systemd/user/graphical-session.target.wants'
        self.run('mkdir', '-p', wants, user=True)
        self.run('ln', '-sfn', '../soltros-desktop.service', wants / unit.name, user=True)

    def plan(self):
        print('Target: Kubuntu 26.10 amd64; existing Plasma desktop; AMD b450m-d3sh profile.')
        print('User:', self.user)
        if self.args.antigravity_only:
            print('Install official Antigravity CLI as', self.user, 'under', self.home / '.local/bin/agy')
            return
        if self.args.shell_only:
            print('Shell packages:', ' '.join(lines('shell-apt.txt')))
            print('Apply Zsh, Starship, history, completions, git/sudo plugins and APT aliases only.')
            return
        print('APT:', ' '.join(lines('apt.txt')))
        print('Soltros APT packages:', ' '.join(lines('soltros-apt.txt')))
        print('Apply: AMD graphics, i386 Steam libraries, Docker/libvirt/VirtualBox, SSH, Tailscale, Bluetooth, CUPS, audio, performance, locale, Zsh, fonts, Plasma widget and themes.')
        print('Additional APT packages checked at runtime:', ' '.join(lines('optional-apt.txt')))
        print('Last-resort Flatpak candidates:', ', '.join(item['apt'] for item in json.loads((ROOT / 'config/fallbacks.json').read_text())))
        print('Requires signed apt-stonking release:', SOLTROS_BASE)
        print('No disk formatting, mount changes, package pruning, or automatic reboot.')

    def main(self):
        self.plan()
        if self.args.dry_run:
            return 0
        if self.args.shell_only and self.args.antigravity_only:
            raise RuntimeError('Run --shell-only and --antigravity-only separately.')
        if self.args.antigravity_only:
            self.antigravity()
            return 0
        release = os_release()
        if release.get('ID') != 'ubuntu' or release.get('VERSION_ID') != '26.10':
            raise RuntimeError('Only Kubuntu 26.10 is supported; this is not a release-upgrade script.')
        if subprocess.check_output(['dpkg', '--print-architecture'], text=True).strip() != 'amd64':
            raise RuntimeError('This desktop hardware profile requires amd64.')
        if not self.args.shell_only and not shutil.which('update-grub'):
            raise RuntimeError('This profile expects Kubuntu’s GRUB installation; no bootloader conversion is attempted.')
        if not self.args.shell_only and (not shutil.which('plasmashell') or not shutil.which('kwriteconfig6')):
            raise RuntimeError('Install Kubuntu 26.10 first; Plasma 6 is required.')
        if self.args.user_settings:
            if os.geteuid() == 0:
                raise RuntimeError('Run --user-settings without sudo, in your Plasma session.')
            return subprocess.call(['python3', str(ROOT / 'scripts/user-settings.py'), str(ROOT)])
        if os.geteuid() != 0 or self.account.pw_uid == 0:
            raise RuntimeError('Run sudo bash run.sh from your desktop account, or specify --user.')
        self.cache.mkdir(parents=True, exist_ok=True)
        self.state.mkdir(parents=True, exist_ok=True)
        self.backup.mkdir(parents=True, mode=0o700)
        os.environ['DEBIAN_FRONTEND'] = 'noninteractive'
        try:
            self.shell()
            if self.args.shell_only:
                return 1 if self.failures else 0
            self.attempt('Antigravity CLI', self.antigravity)
            self.check_soltros_release()
            self.system()
            self.apps()
            self.themes()
            self.attempt('desktop settings', self.user_files)
        except (subprocess.SubprocessError, OSError, ValueError, RuntimeError) as exc:
            self.failures.append(str(exc))
        report = {'failures': self.failures, 'known_gaps': self.gaps, 'flatpak_fallbacks': self.fallbacks, 'backups': str(self.backup)}
        self.write(self.state / 'last-report.json', json.dumps(report, indent=2) + '\n')
        print(json.dumps(report, indent=2))
        print('Log out/reboot after reviewing the report. Authenticate with sudo tailscale up and codex login separately.')
        return 1 if self.failures else (0 if self.args.allow_gaps or not self.gaps else 2)


if __name__ == '__main__':
    try:
        sys.exit(Installer(parse_args()).main())
    except (RuntimeError, OSError, subprocess.SubprocessError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        sys.exit(1)
