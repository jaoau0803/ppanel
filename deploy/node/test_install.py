"""Local tests: python3 -m unittest discover -s deploy/node -v (no root/network)."""
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import unittest


SCRIPT = Path(__file__).with_name('install.sh').resolve()
BASH = shutil.which('bash')


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def run_script(self, *args, env=None):
        return subprocess.run([BASH, str(SCRIPT), *args], cwd=self.root,
                              env=env, capture_output=True, text=True, timeout=10)

    def helper(self, *args):
        return subprocess.run([BASH, '-c', 'source "$1"; shift; helper "$@"',
                               'test', str(SCRIPT), *map(str, args)], cwd=self.root,
                              capture_output=True, text=True, timeout=10)

    def test_help_without_dependencies_or_side_effects(self):
        env = dict(os.environ, PATH=str(self.root))
        for flag in ('--help', '-h'):
            result = self.run_script(flag, env=env)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('jaoau0803/ppanel', result.stdout)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_missing_dependency_has_explicit_error(self):
        result = self.run_script(env=dict(os.environ, PATH=str(self.root)))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('missing dependency: python3', result.stderr)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_invalid_arguments(self):
        cases = [('--unknown',), ('--version',), ('--secret-key', ''),
                 ('--server-id', '--repo'), ('--version', 'v1.2.3'),
                 ('--version', 'node-v1.2.3/evil'), ('--version', 'node-v01.2.3'),
                 ('--repo', '../bad'), ('--repo', 'owner/repo/extra'),
                 ('--repo', '-owner/repo'), ('--server-id', '0'),
                 ('--server-id', '-1'), ('--server-id', '1;id'),
                 ('--server-id', '2147483648'), ('--api-host', 'file:///etc/passwd'),
                 ('--api-host', 'https://user:pass@example.com'),
                 ('--api-host', 'https://example.com:bad'),
                 ('--api-host', 'https://example.com?q=x'),
                 ('--secret-key', 'a\nb'), ('--repo', 'a/b', '--repo', 'c/d')]
        for args in cases:
            with self.subTest(args=args):
                result = self.run_script(*args)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('Error:', result.stderr)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_valid_prerelease_and_quoted_secret(self):
        result = self.helper('validate', 'node-v1.2.3-rc.1', 'jaoau0803/ppanel',
                             'https://panel.example.com/api', '7', 'a:"\\# yes')
        self.assertEqual(result.returncode, 0, result.stderr)
        target = self.root / 'config.yml'
        secret = 'x"\\: # yaml injection 中文'
        result = self.helper('config', 'https://panel.example.com', '7', secret, target)
        self.assertEqual(result.returncode, 0, result.stderr)
        text = target.read_text()
        value = next(line.split(': ', 1)[1] for line in text.splitlines()
                     if line.startswith('  SecretKey:'))
        self.assertEqual(json.loads(value), secret)
        self.assertIn('  ServerID: 7\n', text)

    def test_release_selection(self):
        releases = self.root / 'releases.json'
        def release(tag, date, **kw):
            return dict(tag_name=tag, published_at=date, draft=False, prerelease=False, **kw)
        data = [release('node-v1.2.3', '2025-01-01T00:00:00Z'),
                release('backend-v99.0.0', '2026-03-01T00:00:00Z'),
                release('node-v1.3.0', '2026-01-01T00:00:00Z'),
                release('node-v1.9.0-rc.1', '2026-04-01T00:00:00Z')]
        data += [dict(data[2], tag_name='node-v2.0.0', prerelease=True),
                 dict(data[2], tag_name='node-v3.0.0', draft=True)]
        releases.write_text(json.dumps(data))
        result = self.helper('select', releases)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.rstrip().endswith('node-v1.3.0'))

    def test_archive_only_extracts_required_regular_files(self):
        archive = self.root / 'node.tar.gz'
        dest = self.root / 'files'
        dest.mkdir()
        names = ['ppnode', 'geoip.dat', 'geosite.dat', 'LICENSE', 'THIRD_PARTY_NOTICES.md']
        def make_archive(symlink=False):
            with tarfile.open(archive, 'w:gz') as tar:
                for name in names + ['../escape', 'unneeded']:
                    info = tarfile.TarInfo(name)
                    if symlink and name == 'ppnode':
                        info.type = tarfile.SYMTYPE
                        info.linkname = '/etc/passwd'
                        tar.addfile(info)
                    else:
                        info.size = 4
                        tar.addfile(info, io.BytesIO(b'data'))
        make_archive()
        result = self.helper('unpack', archive, dest)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(sorted(p.name for p in dest.iterdir()), sorted(names))
        self.assertFalse((self.root / 'escape').exists())
        make_archive(symlink=True)
        self.assertNotEqual(self.helper('unpack', archive, dest).returncode, 0)

    def test_checksum_exact_match_and_duplicates(self):
        sums, target = self.root / 'SHA256SUMS', self.root / 'checksum'
        asset = 'ppanel-node-linux-amd64.tar.gz'
        digest = hashlib.sha256(b'test').hexdigest()
        sums.write_text(f'{digest}  {asset}\n')
        result = self.helper('checksum', sums, asset, target)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(target.read_text(), f'{digest}  {asset}\n')
        sums.write_text(sums.read_text() * 2)
        self.assertNotEqual(self.helper('checksum', sums, asset, target).returncode, 0)
        self.assertNotEqual(self.helper('checksum', sums, 'other', target).returncode, 0)

    def mocked_main(self, fail_download=False):
        # Stop at staging. Never execute installation commands or write system paths.
        # EUID is readonly: substitute only the root/systemd guards in an in-memory
        # copy; the real main, pagination and download failure paths remain intact.
        source = SCRIPT.read_text().replace(
            '[[ $EUID == 0 ]]', '[[ 0 == 0 ]]').replace(
            '[[ -d /run/systemd/system ]]', '[[ 1 == 1 ]]')
        local_script = self.root / 'mock-install.sh'
        local_script.write_text(source)
        body = r'''
source "$1"
uname() { if [[ "$1" == -s ]]; then echo Linux; else echo x86_64; fi; }
systemctl() { echo unexpected-systemctl >&2; return 99; }
sha256sum() { echo unexpected-checksum >&2; return 99; }
mktemp() { python3 -c 'import os,tempfile; print(tempfile.mkdtemp(dir=os.environ["TEST_ROOT"]))'; }
install() { echo unexpected-install >&2; return 99; }
download() {
    echo "$1" >> "$TEST_ROOT/requests"
    if [[ "$FAIL_DOWNLOAD" == yes ]]; then return 22; fi
    case "$1" in
        *'page=1') python3 -c 'import json,sys; json.dump([dict(tag_name="backend-v1", draft=False, prerelease=False)]*100,open(sys.argv[1],"w"))' "$2" ;;
        *'page=2') printf '%s' '[{"tag_name":"node-v1.2.3","draft":false,"prerelease":false,"published_at":"2026-01-01T00:00:00Z"}]' > "$2" ;;
        *ppanel-node-linux-amd64.tar.gz) exit 42 ;;
        *) return 98 ;;
    esac
}
main --api-host https://example.com --server-id 1 --secret-key test
'''
        env = dict(os.environ, TEST_ROOT=str(self.root), TMPDIR=str(self.root),
                   FAIL_DOWNLOAD='yes' if fail_download else 'no')
        return subprocess.run([BASH, '-c', body, 'test', str(local_script)], env=env,
                              capture_output=True, text=True, timeout=10)

    def test_pagination_before_download(self):
        result = self.mocked_main()
        self.assertEqual(result.returncode, 42, result.stderr)
        requests = (self.root / 'requests').read_text().splitlines()
        self.assertIn('page=1', requests[0])
        self.assertIn('page=2', requests[1])
        self.assertIn('/node-v1.2.3/ppanel-node-linux-amd64.tar.gz', requests[2])
        self.assertFalse(any(p.is_dir() for p in self.root.iterdir()))

    def test_failed_download_does_not_install_and_cleans_temp(self):
        result = self.mocked_main(fail_download=True)
        self.assertEqual(result.returncode, 22, result.stderr)
        self.assertNotIn('unexpected-', result.stderr)
        self.assertFalse(any(p.is_dir() for p in self.root.iterdir()))


if __name__ == '__main__':
    unittest.main()
