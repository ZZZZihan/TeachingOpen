#!/usr/bin/env python3
"""Offline rendering and real-file failure/recovery checks; no target services."""
import fcntl
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import ip_https as tls


class RenderingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.args = dict(ip='8.8.8.8', web_root='/srv/teachingopen/web',
            api_upstream='http://127.0.0.1:8080', acme_root='/var/lib/teachingopen-acme',
            certificate='/etc/letsencrypt/live/teachingopen-ip/fullchain.pem',
            private_key='/etc/letsencrypt/live/teachingopen-ip/privkey.pem',
            output=str(self.root / 'rendered'))

    def tearDown(self):
        self.temp.cleanup()

    def test_offline_output_hashes_private_files_and_unchanged_template(self):
        before = tls.TEMPLATE.read_bytes()
        with patch.object(tls.subprocess, 'run', side_effect=AssertionError('Rendering must stay offline')):
            result = tls.render(**self.args)
        self.assertFalse(result['deployed'])
        self.assertFalse(result['certificate_issued'])
        self.assertEqual(tls.TEMPLATE.read_bytes(), before)
        output = Path(self.args['output'])
        self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o700)
        self.assertEqual(set(p.name for p in output.iterdir()),
                         {'bootstrap.conf', 'trial.conf', 'https.conf', 'manifest.json'})
        manifest = json.loads((output / 'manifest.json').read_text())
        for name, expected in manifest['files'].items():
            data = (output / name).read_bytes()
            self.assertEqual(tls.digest(data), expected['sha256'])
            self.assertEqual(len(data), expected['bytes'])
            self.assertEqual(stat.S_IMODE((output / name).stat().st_mode), 0o600)
        self.assertEqual(tls.digest((output / 'manifest.json').read_bytes()), result['manifest_sha256'])

    def test_rejects_existing_output_without_overwriting(self):
        output = Path(self.args['output'])
        output.mkdir()
        (output / 'owned.txt').write_text('keep')
        with self.assertRaises(ValueError):
            tls.render(**self.args)
        self.assertEqual((output / 'owned.txt').read_text(), 'keep')

    def test_rejects_nonpublic_and_non_ipv4_addresses(self):
        for ip in ('127.0.0.1', '192.168.1.1', '100.64.0.1', '203.0.113.1',
                   '0.0.0.0', '224.0.0.1', '::1', '2001:4860:4860::8888', '8.8.8.8;'):
            with self.subTest(ip=ip), self.assertRaises(ValueError):
                tls.render(**dict(self.args, ip=ip))
        self.assertFalse(Path(self.args['output']).exists())

    def test_rejects_nonlocal_upstream_and_config_injection(self):
        for upstream in ('http://example.com:80', 'http://127.0.0.1:65536',
                         'http://127.0.0.1:0', 'http://127.0.0.1:8080/api',
                         'http://127.0.0.1:8080;\nreturn 200;', 'https://127.0.0.1:8080'):
            with self.subTest(upstream=upstream), self.assertRaises(ValueError):
                tls.render(**dict(self.args, api_upstream=upstream))
        for path in ('relative', '/srv/../private', '/srv/$scheme', '/srv/hello world',
                     '/srv/web; include /secrets', '/srv/web\nserver {}'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                tls.render(**dict(self.args, web_root=path))

    def test_rejects_secret_or_output_inside_public_root(self):
        with self.assertRaises(ValueError):
            tls.render(**dict(self.args, private_key='/srv/teachingopen/web/key.pem'))
        with self.assertRaises(ValueError):
            tls.render(**dict(self.args, certificate='/var/lib/teachingopen-acme/cert.pem'))
        with self.assertRaises(ValueError):
            tls.render(**dict(self.args, web_root=str(self.root)))

    def test_changed_template_anchor_fails_before_output(self):
        template = self.root / 'source.conf'
        template.write_text(tls.TEMPLATE.read_text().replace('server_name localhost;', 'server_name changed;'))
        with patch.object(tls, 'TEMPLATE', template), self.assertRaises(ValueError):
            tls.render(**self.args)
        self.assertFalse(Path(self.args['output']).exists())

    def test_symlink_output_parent_rejected(self):
        link = self.root / 'alias'
        link.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ValueError):
            tls.render(**dict(self.args, output=str(link / 'out')))
        self.assertFalse((self.root / 'out').exists())


class SwitchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.target = self.root / 'active.conf'
        self.target.write_bytes(b'old configuration\n')
        self.target.chmod(0o640)
        self.candidate = self.root / 'trial.conf'
        self.candidate.write_bytes(b'new configuration\n')
        self.backup = self.root / 'backup'
        self.events = self.root / 'events.jsonl'
        self.always_fail_reload = self.root / 'always-fail-reload'
        self.missing_dependency = self.root / 'missing-candidate-dependency'
        self.blocked = self.root / 'nginx-validation-blocked'
        self.nginx = self.root / 'nginx'
        # This executable runs in a real child process and observes the actual
        # config at each test/reload; failures are not mocked return values.
        self.nginx.write_text('#!' + sys.executable + '\n' + '''import json, pathlib, sys, time
target = pathlib.Path(''' + repr(str(self.target)) + ''')
events = pathlib.Path(''' + repr(str(self.events)) + ''')
failure = pathlib.Path(''' + repr(str(self.always_fail_reload)) + ''')
missing_dependency = pathlib.Path(''' + repr(str(self.missing_dependency)) + ''')
blocked = pathlib.Path(''' + repr(str(self.blocked)) + ''')
data = target.read_text()
with events.open('a') as out:
    out.write(json.dumps({'args': sys.argv[1:], 'data': data}) + '\\n')
if sys.argv[1:] == ['-t'] and 'INVALID' in data:
    sys.exit(1)
if sys.argv[1:] == ['-t'] and 'CANDIDATE_DEPENDENCY' in data and missing_dependency.exists():
    sys.exit(1)
if sys.argv[1:] == ['-t'] and 'BLOCK_ACTIVATE' in data:
    blocked.touch()
    time.sleep(30)
if sys.argv[1:] == ['-s', 'reload'] and ('RELOAD_FAIL' in data or failure.exists()):
    sys.exit(1)
''')
        self.nginx.chmod(0o700)

    def tearDown(self):
        self.temp.cleanup()

    def activate(self):
        return tls.activate(self.target, self.candidate, self.backup, self.nginx)

    def rollback(self):
        return tls.rollback(self.target, self.backup, self.nginx)

    def receipt(self):
        return json.loads((self.backup / 'receipt.json').read_text())

    def logged(self):
        return [json.loads(line) for line in self.events.read_text().splitlines()]

    def test_activate_and_rollback_preserve_original_bytes_mode_and_process_order(self):
        original = self.target.read_bytes()
        result = self.activate()
        self.assertEqual(result['status'], 'active')
        self.assertFalse(result['live_business_verified'])
        self.assertEqual(self.target.read_bytes(), self.candidate.read_bytes())
        self.assertEqual(stat.S_IMODE(self.target.stat().st_mode), 0o640)
        self.assertEqual((self.backup / 'previous.conf').read_bytes(), original)
        self.assertEqual(stat.S_IMODE(self.backup.stat().st_mode), 0o700)
        for path in self.backup.iterdir():
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        events = self.logged()
        self.assertEqual([row['args'] for row in events], [['-t'], ['-t'], ['-s', 'reload']])
        self.assertEqual(events[0]['data'].encode(), original)
        self.assertEqual(events[1]['data'].encode(), self.candidate.read_bytes())
        self.assertEqual(self.rollback()['status'], 'rolled_back')
        self.assertEqual(self.target.read_bytes(), original)
        self.assertEqual(self.rollback()['status'], 'rolled_back')

    def test_invalid_existing_config_refuses_switch_and_backup_creation(self):
        self.target.write_text('INVALID old configuration')
        with self.assertRaises(RuntimeError):
            self.activate()
        self.assertEqual(self.target.read_text(), 'INVALID old configuration')
        self.assertFalse(self.backup.exists())
        self.assertEqual(len(self.logged()), 1)

    def test_invalid_candidate_restores_old_config_and_never_reloads_bad_bytes(self):
        self.candidate.write_text('INVALID candidate')
        with self.assertRaisesRegex(RuntimeError, 'previous configuration bytes restored'):
            self.activate()
        self.assertEqual(self.target.read_text(), 'old configuration\n')
        self.assertEqual(self.receipt()['status'], 'activation_failed_recovered')
        reloaded = [row['data'] for row in self.logged() if row['args'] == ['-s', 'reload']]
        self.assertEqual(reloaded, ['old configuration\n'])

    def test_failed_reload_restores_and_reloads_old_config(self):
        self.candidate.write_text('RELOAD_FAIL candidate')
        with self.assertRaisesRegex(RuntimeError, 'previous configuration bytes restored'):
            self.activate()
        self.assertEqual(self.target.read_text(), 'old configuration\n')
        self.assertEqual(self.receipt()['status'], 'activation_failed_recovered')
        self.assertEqual(self.logged()[-1], {'args': ['-s', 'reload'], 'data': 'old configuration\n'})

    def test_recovery_failure_is_explicit_and_keeps_backup(self):
        self.always_fail_reload.touch()
        with self.assertRaisesRegex(RuntimeError, 'Switch and recovery failed'):
            self.activate()
        self.assertEqual(self.receipt()['status'], 'recovery_required')
        self.assertEqual(self.target.read_text(), 'old configuration\n')
        self.assertEqual((self.backup / 'previous.conf').read_text(), 'old configuration\n')

    def test_rollback_refuses_changed_target_without_overwriting(self):
        self.activate()
        self.target.write_text('later operator edit')
        with self.assertRaisesRegex(ValueError, 'Target changed'):
            self.rollback()
        self.assertEqual(self.target.read_text(), 'later operator edit')

    def test_rollback_succeeds_when_current_certificate_dependency_disappears(self):
        self.candidate.write_text('CANDIDATE_DEPENDENCY')
        self.activate()
        self.missing_dependency.touch()
        with self.assertRaises(RuntimeError):
            tls.nginx_command(self.nginx, '-t')
        self.assertEqual(self.rollback()['status'], 'rolled_back')
        self.assertEqual(self.target.read_text(), 'old configuration\n')
        self.assertEqual(self.logged()[-2:], [
            {'args': ['-t'], 'data': 'old configuration\n'},
            {'args': ['-s', 'reload'], 'data': 'old configuration\n'}])

    def test_explicit_rollback_recovers_interrupted_known_states(self):
        self.activate()
        original_receipt = self.receipt()
        for status in ('switching', 'rolling_back', 'recovery_required'):
            for current in (b'old configuration\n', b'new configuration\n'):
                with self.subTest(status=status, current=current):
                    self.target.write_bytes(current)
                    tls.save_receipt(self.backup, dict(original_receipt, status=status))
                    self.assertEqual(self.rollback()['status'], 'rolled_back')
                    self.assertEqual(self.target.read_text(), 'old configuration\n')

    def test_interrupted_receipt_still_refuses_unknown_target(self):
        self.activate()
        receipt = self.receipt()
        receipt['status'] = 'switching'
        tls.save_receipt(self.backup, receipt)
        self.target.write_text('another operator configuration')
        with self.assertRaisesRegex(ValueError, 'Target changed'):
            self.rollback()
        self.assertEqual(self.target.read_text(), 'another operator configuration')

    def test_sigkill_requires_explicit_rollback_and_preserves_recovery_record(self):
        self.candidate.write_text('BLOCK_ACTIVATE')
        process = subprocess.Popen([sys.executable, str(Path(tls.__file__).resolve()), 'activate',
            '--target', str(self.target), '--candidate', str(self.candidate),
            '--backup', str(self.backup), '--nginx', str(self.nginx)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        try:
            deadline = time.monotonic() + 5
            while not self.blocked.exists() and time.monotonic() < deadline:
                if process.poll() is not None:
                    self.fail('Activation exited before the interruption boundary')
                time.sleep(0.02)
            self.assertTrue(self.blocked.exists())
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)
            self.assertEqual(self.receipt()['status'], 'switching')
            # SIGKILL cannot run a catch/finally recovery handler.
            self.assertEqual(self.target.read_text(), 'BLOCK_ACTIVATE')
            self.assertEqual(self.rollback()['status'], 'rolled_back')
            self.assertEqual(self.target.read_text(), 'old configuration\n')
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)

    def test_rollback_refuses_tampered_backup(self):
        self.activate()
        (self.backup / 'previous.conf').write_text('other configuration')
        with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
            self.rollback()
        self.assertEqual(self.target.read_bytes(), self.candidate.read_bytes())

    def test_failed_rollback_recovers_active_candidate(self):
        self.activate()
        # Simulate an old configuration whose external dependency no longer
        # works, while retaining an internally consistent private receipt.
        previous = self.backup / 'previous.conf'
        previous.write_text('INVALID previous external dependency')
        receipt = self.receipt()
        receipt['previous_sha256'] = tls.digest(previous.read_bytes())
        tls.save_receipt(self.backup, receipt)
        with self.assertRaisesRegex(RuntimeError, 'previous configuration bytes restored'):
            self.rollback()
        self.assertEqual(self.target.read_bytes(), self.candidate.read_bytes())
        self.assertEqual(self.receipt()['status'], 'active')

    def test_symlink_target_candidate_and_backup_parent_refused(self):
        alias = self.root / 'alias.conf'
        alias.symlink_to(self.target)
        with self.assertRaises(ValueError):
            tls.activate(alias, self.candidate, self.backup, self.nginx)
        with self.assertRaises(ValueError):
            tls.activate(self.target, alias, self.backup, self.nginx)
        directory_alias = self.root / 'alias-dir'
        directory_alias.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ValueError):
            tls.activate(self.target, self.candidate, directory_alias / 'backup', self.nginx)
        self.assertFalse(self.events.exists())

    def test_existing_backup_not_reused(self):
        self.backup.mkdir()
        (self.backup / 'keep').write_text('owned')
        with self.assertRaises(ValueError):
            self.activate()
        self.assertEqual((self.backup / 'keep').read_text(), 'owned')
        self.assertFalse(self.events.exists())

    def test_lock_rejects_concurrent_operation(self):
        lock = self.target.with_name('.' + self.target.name + '.teachingopen-https.lock')
        fd = os.open(lock, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaisesRegex(RuntimeError, 'holds the lock'):
                self.activate()
        finally:
            os.close(fd)
        self.assertFalse(self.backup.exists())
        self.assertFalse(self.events.exists())

    def test_symlink_lock_cannot_modify_other_file(self):
        owned = self.root / 'owned'
        owned.write_text('keep')
        lock = self.target.with_name('.' + self.target.name + '.teachingopen-https.lock')
        lock.symlink_to(owned)
        with self.assertRaises(OSError):
            self.activate()
        self.assertEqual(owned.read_text(), 'keep')
        self.assertFalse(self.events.exists())


if __name__ == '__main__':
    unittest.main()
