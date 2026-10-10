#!/usr/bin/env python3
"""Offline rendering and real-file failure/recovery checks; no target services."""
import fcntl
from contextlib import contextmanager, redirect_stdout
import io
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
import test_ip_https_runtime as runtime_test


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


class ReviewedSiteRenderingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.source = self.root / 'reviewed-site.conf'
        self.args = dict(ip='8.8.8.8', web_root='/var/www/teachingopen-current',
            api_upstream='http://127.0.0.1:8080', acme_root='/var/lib/teachingopen-acme',
            certificate='/etc/letsencrypt/live/teachingopen-ip/fullchain.pem',
            private_key='/etc/letsencrypt/live/teachingopen-ip/privkey.pem',
            output=str(self.root / 'rendered'), source_config=str(self.source))
        self.cache_map = '''map $uri $teaching_html_cache_policy {
    default "";
    ~*\\.html$ "no-cache";
}

'''
        self.static = '''    # A missing script/style is not a client-side page route.
    location ~* \\.(js|css)(\\.gz)?$ {
        root /var/www/teachingopen-current;
        try_files $uri =404;
        gzip on;
        gzip_min_length 1k;
        gzip_comp_level 9;
        gzip_types application/javascript text/css;
        gzip_vary on;
        gzip_disable "MSIE [1-6]\\.";
    }

'''
        # A synthetic copy of the supported deployment shape. No production
        # config/path or certificate is read by these tests.
        fixture = self.cache_map + tls.TEMPLATE.read_text()
        fixture = fixture.replace('    listen 80 default_server;',
                                  '    listen 80 default_server;\n    listen 127.0.0.1:8088;')
        fixture = fixture.replace('server_name localhost;', 'server_name 8.8.8.8;')
        fixture = fixture.replace('root /usr/share/nginx/html;', 'root /var/www/teachingopen-current;')
        fixture = fixture.replace('http://api:8080;', 'http://127.0.0.1:8080;')
        fixture = fixture.replace(
            '    add_header Cross-Origin-Resource-Policy $teaching_python_resource_policy always;',
            '    add_header Cross-Origin-Resource-Policy $teaching_python_resource_policy always;\n'
            '    add_header Cache-Control $teaching_html_cache_policy always;')
        fixture = fixture.replace('    location / {', self.static + '    location / {')
        self.source.write_text(fixture)
        self.args['source_sha256'] = tls.digest(self.source.read_bytes())

    def tearDown(self):
        self.temp.cleanup()

    def render(self, **overrides):
        return tls.render(**dict(self.args, **overrides))

    def output(self, name):
        return (Path(self.args['output']) / name).read_text()

    def test_source_provenance_and_all_untouched_business_bytes_are_preserved(self):
        before = self.source.read_bytes()
        with patch.object(tls.subprocess, 'run', side_effect=AssertionError('Rendering must stay offline')):
            result = self.render()
        self.assertEqual(self.source.read_bytes(), before)
        self.assertEqual(result['source_mode'], 'reviewed_site')
        self.assertEqual(result['source_path'], str(self.source))
        self.assertEqual(result['source_sha256'], tls.digest(before))
        bootstrap = self.output('bootstrap.conf').split('\n', 1)[1]
        # Reverse only the design's four deliberate changes. Equality proves
        # the complete reviewed business config survived, not selected snippets.
        bootstrap = bootstrap.replace('''        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Port $server_port;
        proxy_set_header X-Forwarded-Host $host;
''', '')
        bootstrap = bootstrap.replace('        absolute_redirect off;\n', '')
        bootstrap = bootstrap.replace('proxy_set_header X-Forwarded-For $remote_addr;',
                                      'proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;')
        bootstrap = bootstrap.replace('''    location ^~ /.well-known/acme-challenge/ {
        root "/var/lib/teachingopen-acme";
        default_type text/plain;
        try_files $uri =404;
    }

''', '')
        self.assertEqual(bootstrap.encode(), before)

    def test_native_listeners_are_owned_once_and_final_local_http_keeps_business(self):
        self.render()
        bootstrap, trial, final = [self.output(name + '.conf') for name in ('bootstrap', 'trial', 'https')]
        for config in (bootstrap, trial, final):
            self.assertEqual(config.count('listen 127.0.0.1:8088;'), 1)
            self.assertEqual(config.count('listen 80 default_server;'), 1)
        self.assertNotIn('listen 443 ssl', bootstrap)
        self.assertEqual(trial.count('listen 443 ssl default_server;'), 1)
        self.assertEqual(final.count('listen 443 ssl default_server;'), 1)
        tls_trial = 'server\n' + trial.split('\nserver\n')[2]
        self.assertNotIn('8088', tls_trial)
        local = 'server\n' + final.split('\nserver\n')[2].split('\nserver {')[0]
        self.assertNotIn('listen 80', local)
        self.assertNotIn('ssl_', local)
        self.assertIn('proxy_pass              http://127.0.0.1:8080;', local)
        self.assertIn(self.static, local)
        self.assertIn('add_header Cache-Control $teaching_html_cache_policy always;', local)
        self.assertNotIn('return 426', local)
        redirect = final.split('\nserver {')[1]
        self.assertIn('location = /api { return 426; }', redirect)
        self.assertIn('location ^~ /api/ { return 426; }', redirect)
        self.assertIn('return 307 https://8.8.8.8$request_uri;', redirect)

    def test_current_roots_static_404_and_html_cache_survive_all_stages(self):
        self.render()
        for mode, businesses in (('bootstrap', 1), ('trial', 2), ('https', 2)):
            with self.subTest(mode=mode):
                config = self.output(mode + '.conf')
                self.assertEqual(config.count(self.static), businesses)
                self.assertEqual(config.count('root /var/www/teachingopen-current;'), businesses * 2)
                self.assertEqual(config.count(self.cache_map), 1)
                self.assertEqual(config.count('add_header Cache-Control $teaching_html_cache_policy always;'), businesses)
                self.assertNotIn('/usr/share/nginx/html', config)
                self.assertNotIn('Strict-Transport-Security', config)
                self.assertNotIn('$proxy_add_x_forwarded_for', config)

    def test_source_digest_mismatch_refuses_render_before_output(self):
        original = self.source.read_bytes()
        self.source.write_bytes(original + b'# later operator edit\n')
        with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
            self.render()
        self.assertEqual(self.source.read_bytes(), original + b'# later operator edit\n')
        self.assertFalse(Path(self.args['output']).exists())

    def test_source_options_must_be_paired_and_sha256_must_be_explicit(self):
        for overrides in ({'source_config': None}, {'source_sha256': None},
                          {'source_sha256': ''}, {'source_sha256': 'a' * 63},
                          {'source_sha256': 'A' * 64}):
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                self.render(**overrides)
        self.assertFalse(Path(self.args['output']).exists())

    def test_wrong_expected_source_identity_root_or_upstream_are_not_silently_replaced(self):
        for overrides in ({'web_root': '/var/www/teachingopen-old'},
                          {'api_upstream': 'http://127.0.0.1:18080'}, {'ip': '8.8.4.4'}):
            with self.subTest(overrides=overrides), self.assertRaisesRegex(ValueError, 'site profile'):
                self.render(**overrides)
        self.assertFalse(Path(self.args['output']).exists())

    def test_reviewed_but_unsupported_or_nonunique_config_is_rejected(self):
        source = self.source.read_text()
        unsupported = (
            source + '\nserver { listen 8089; }\n',
            source.replace('    listen 127.0.0.1:8088;\n', ''),
            source.replace('    listen 127.0.0.1:8088;', '    listen 0.0.0.0:8088;'),
            source.replace('    listen 127.0.0.1:8088;', '    listen 127.0.0.1:8088;\n    listen 8089;'),
            source.replace('server_name 8.8.8.8;', 'server_name 8.8.8.8;\n    server_name other;'),
            source.replace('root /var/www/teachingopen-current;', 'root /var/www/teachingopen-old;', 1),
            source.replace('        try_files $uri =404;\n', '', 1),
            source.replace('    add_header Cache-Control $teaching_html_cache_policy always;\n', ''),
            source.replace('    location = /api {', '    location = /api {\n        include /etc/nginx/custom.conf;'),
            source.replace('        proxy_set_header        Host $host;',
                           '        proxy_set_header        Host $host;\n        proxy_set_header        Host $host;'),
            source.replace('        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;', ''),
            source.replace('    listen 80 default_server;', '    listen 443 ssl;'),
        )
        for index, config in enumerate(unsupported):
            self.source.write_text(config)
            with self.subTest(index=index), self.assertRaisesRegex(ValueError, 'site profile'):
                self.render(source_sha256=tls.digest(self.source.read_bytes()))
            self.assertEqual(self.source.read_text(), config)
            self.assertFalse(Path(self.args['output']).exists())

    def test_source_symlink_and_missing_path_are_refused(self):
        alias = self.root / 'alias.conf'
        alias.symlink_to(self.source)
        with self.assertRaises(ValueError):
            self.render(source_config=str(alias))
        with self.assertRaises(OSError):
            self.render(source_config=str(self.root / 'missing.conf'))
        self.assertFalse(Path(self.args['output']).exists())


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
        return tls.activate(self.target, self.candidate, self.backup, self.nginx,
                            expected_candidate_sha256=tls.digest(self.candidate.read_bytes()))

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

    def test_expected_target_digest_allows_exact_reviewed_source(self):
        expected = tls.digest(self.target.read_bytes())
        result = tls.activate(self.target, self.candidate, self.backup, self.nginx,
                              expected_target_sha256=expected,
                              expected_candidate_sha256=tls.digest(self.candidate.read_bytes()))
        self.assertEqual(result['status'], 'active')
        self.assertEqual(self.target.read_bytes(), self.candidate.read_bytes())
        self.assertEqual(self.receipt()['previous_sha256'], expected)

    def test_expected_target_digest_refuses_drift_before_nginx_or_backup(self):
        expected = tls.digest(self.target.read_bytes())
        self.target.write_bytes(b'later release config\n')
        with self.assertRaisesRegex(ValueError, 'Target changed since review'):
            tls.activate(self.target, self.candidate, self.backup, self.nginx,
                         expected_target_sha256=expected,
                         expected_candidate_sha256=tls.digest(self.candidate.read_bytes()))
        self.assertEqual(self.target.read_bytes(), b'later release config\n')
        self.assertEqual(stat.S_IMODE(self.target.stat().st_mode), 0o640)
        self.assertFalse(self.backup.exists())
        self.assertFalse(self.events.exists())

    def test_expected_target_digest_rejects_malformed_checksum(self):
        original = self.target.read_bytes()
        with self.assertRaisesRegex(ValueError, 'SHA-256'):
            tls.activate(self.target, self.candidate, self.backup, self.nginx,
                         expected_target_sha256='',
                         expected_candidate_sha256=tls.digest(self.candidate.read_bytes()))
        self.assertEqual(self.target.read_bytes(), original)
        self.assertFalse(self.backup.exists())
        self.assertFalse(self.events.exists())

    def test_candidate_digest_is_required_by_python_api_and_cli(self):
        with self.assertRaises(TypeError):
            tls.activate(self.target, self.candidate, self.backup, self.nginx)
        result = subprocess.run([sys.executable, str(Path(tls.__file__).resolve()), 'activate',
            '--target', str(self.target), '--candidate', str(self.candidate),
            '--backup', str(self.backup), '--nginx', str(self.nginx)],
            capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 2)
        self.assertIn('--expected-candidate-sha256', result.stderr)
        self.assertEqual(self.target.read_bytes(), b'old configuration\n')
        self.assertFalse(self.backup.exists())
        self.assertFalse(self.events.exists())

    def test_candidate_digest_rejects_malformed_review_before_any_state_write(self):
        for expected in (None, '', 'a' * 63, 'A' * 64):
            with self.subTest(expected=expected), self.assertRaisesRegex(ValueError, 'SHA-256'):
                tls.activate(self.target, self.candidate, self.backup, self.nginx,
                             expected_candidate_sha256=expected)
        self.assertEqual(self.target.read_bytes(), b'old configuration\n')
        self.assertFalse(self.backup.exists())
        self.assertFalse(self.events.exists())
        self.assertFalse(self.target.with_name('.' + self.target.name + '.teachingopen-https.lock').exists())

    def test_modified_candidate_is_refused_before_any_state_write_or_nginx(self):
        expected = tls.digest(self.candidate.read_bytes())
        self.candidate.write_bytes(b'valid but unreviewed candidate\n')
        with self.assertRaisesRegex(ValueError, 'Candidate changed since review'):
            tls.activate(self.target, self.candidate, self.backup, self.nginx,
                         expected_candidate_sha256=expected)
        result = subprocess.run([sys.executable, str(Path(tls.__file__).resolve()), 'activate',
            '--target', str(self.target), '--candidate', str(self.candidate),
            '--expected-candidate-sha256', expected,
            '--backup', str(self.backup), '--nginx', str(self.nginx)],
            capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 1)
        self.assertIn('Candidate changed since review', result.stderr)
        self.assertEqual(self.target.read_bytes(), b'old configuration\n')
        self.assertFalse(self.backup.exists())
        self.assertFalse(self.events.exists())
        self.assertFalse(self.target.with_name('.' + self.target.name + '.teachingopen-https.lock').exists())

    def test_candidate_changes_after_read_cannot_change_activated_reviewed_bytes(self):
        reviewed = self.candidate.read_bytes()
        original_lock = tls.target_lock

        @contextmanager
        def candidate_changes_before_lock(target):
            self.candidate.write_bytes(b'unreviewed replacement after candidate read\n')
            with original_lock(target):
                yield

        with patch.object(tls, 'target_lock', candidate_changes_before_lock):
            result = tls.activate(self.target, self.candidate, self.backup, self.nginx,
                                  expected_candidate_sha256=tls.digest(reviewed))
        self.assertEqual(self.target.read_bytes(), reviewed)
        self.assertEqual(result['active_sha256'], tls.digest(reviewed))
        self.assertEqual(self.receipt()['candidate_sha256'], tls.digest(reviewed))
        self.assertNotEqual(self.target.read_bytes(), self.candidate.read_bytes())

    def test_completion_receipt_failure_restores_and_reloads_before_reporting_error(self):
        save_receipt = tls.save_receipt

        def fail_completion(backup, receipt):
            if receipt['status'] == 'active':
                raise OSError('simulated disk full')
            return save_receipt(backup, receipt)

        with patch.object(tls, 'save_receipt', fail_completion), self.assertRaisesRegex(
                RuntimeError, 'completion receipt persistence after accepted Nginx reload') as raised:
            self.activate()
        self.assertIn('status=activation_failed_recovered', str(raised.exception))
        self.assertIn('previous configuration bytes restored and reloaded', str(raised.exception))
        self.assertEqual(self.target.read_bytes(), b'old configuration\n')
        self.assertEqual(self.receipt()['status'], 'activation_failed_recovered')
        self.assertEqual([event['data'] for event in self.logged() if event['args'] == ['-s', 'reload']],
                         ['new configuration\n', 'old configuration\n'])

    def test_completion_and_recovery_receipt_failure_preserve_recovered_live_status(self):
        save_receipt = tls.save_receipt

        def fail_final_receipts(backup, receipt):
            if receipt['status'] != 'switching':
                raise OSError('simulated persistent disk full')
            return save_receipt(backup, receipt)

        with patch.object(tls, 'save_receipt', fail_final_receipts), self.assertRaises(RuntimeError) as raised:
            self.activate()
        message = str(raised.exception)
        self.assertIn('status=activation_failed_recovered', message)
        self.assertIn('recovery receipt persistence failed; durable receipt may be stale', message)
        self.assertIn('previous configuration bytes restored and reloaded', message)
        self.assertIn('target_disk_sha256=' + tls.digest(b'old configuration\n'), message)
        self.assertIn('live responses remain unverified', message)
        self.assertEqual(self.target.read_bytes(), b'old configuration\n')
        self.assertEqual(self.receipt()['status'], 'switching')

    def test_failed_reload_and_recovery_receipt_failure_still_report_recovery(self):
        self.candidate.write_text('RELOAD_FAIL candidate')
        save_receipt = tls.save_receipt

        def fail_recovery_receipt(backup, receipt):
            if receipt['status'] == 'activation_failed_recovered':
                raise OSError('simulated disk full')
            return save_receipt(backup, receipt)

        with patch.object(tls, 'save_receipt', fail_recovery_receipt), self.assertRaises(RuntimeError) as raised:
            self.activate()
        self.assertIn('status=activation_failed_recovered', str(raised.exception))
        self.assertIn('recovery receipt persistence failed', str(raised.exception))
        self.assertEqual(self.target.read_bytes(), b'old configuration\n')
        self.assertEqual(self.logged()[-1], {'args': ['-s', 'reload'], 'data': 'old configuration\n'})

    def test_failed_recovery_and_receipt_failure_report_unknown_live_state(self):
        self.always_fail_reload.touch()
        save_receipt = tls.save_receipt

        def fail_recovery_receipt(backup, receipt):
            if receipt['status'] == 'recovery_required':
                raise OSError('simulated disk full')
            return save_receipt(backup, receipt)

        with patch.object(tls, 'save_receipt', fail_recovery_receipt), self.assertRaises(RuntimeError) as raised:
            self.activate()
        self.assertIn('status=recovery_required', str(raised.exception))
        self.assertIn('live Nginx configuration is unknown', str(raised.exception))
        self.assertIn('recovery receipt persistence failed', str(raised.exception))
        self.assertEqual(self.receipt()['status'], 'switching')
        self.assertEqual((self.backup / 'previous.conf').read_bytes(), b'old configuration\n')

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
            '--expected-candidate-sha256', tls.digest(self.candidate.read_bytes()),
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

    def test_rollback_completion_receipt_failure_recovers_candidate_and_reports_active(self):
        self.activate()
        save_receipt = tls.save_receipt

        def fail_completion(backup, receipt):
            if receipt['status'] == 'rolled_back':
                raise OSError('simulated disk full')
            return save_receipt(backup, receipt)

        with patch.object(tls, 'save_receipt', fail_completion), self.assertRaises(RuntimeError) as raised:
            self.rollback()
        self.assertIn('completion receipt persistence after accepted Nginx reload', str(raised.exception))
        self.assertIn('status=active', str(raised.exception))
        self.assertEqual(self.target.read_bytes(), self.candidate.read_bytes())
        self.assertEqual(self.receipt()['status'], 'active')
        self.assertEqual([event['data'] for event in self.logged() if event['args'] == ['-s', 'reload']],
                         ['new configuration\n', 'old configuration\n', 'new configuration\n'])

    def test_rollback_completion_and_recovery_receipt_failure_preserve_active_status(self):
        self.activate()
        save_receipt = tls.save_receipt

        def fail_final_receipts(backup, receipt):
            if receipt['status'] != 'rolling_back':
                raise OSError('simulated persistent disk full')
            return save_receipt(backup, receipt)

        with patch.object(tls, 'save_receipt', fail_final_receipts), self.assertRaises(RuntimeError) as raised:
            self.rollback()
        self.assertIn('status=active', str(raised.exception))
        self.assertIn('recovery receipt persistence failed', str(raised.exception))
        self.assertIn('previous configuration bytes restored and reloaded', str(raised.exception))
        self.assertEqual(self.target.read_bytes(), self.candidate.read_bytes())
        self.assertEqual(self.receipt()['status'], 'rolling_back')
        # The earlier durable intermediate receipt still supports explicit recovery.
        self.assertEqual(self.rollback()['status'], 'rolled_back')

    def test_interrupted_rollback_receipt_failure_with_original_bytes_preserves_correct_status(self):
        self.activate()
        self.target.write_bytes(b'old configuration\n')
        tls.save_receipt(self.backup, dict(self.receipt(), status='rolling_back'))
        save_receipt = tls.save_receipt
        failed = False

        def fail_first_completion(backup, receipt):
            nonlocal failed
            if receipt['status'] == 'rolled_back' and not failed:
                failed = True
                raise OSError('simulated disk full')
            return save_receipt(backup, receipt)

        with patch.object(tls, 'save_receipt', fail_first_completion), self.assertRaises(RuntimeError) as raised:
            self.rollback()
        self.assertIn('status=rolled_back', str(raised.exception))
        self.assertEqual(self.target.read_bytes(), b'old configuration\n')
        self.assertEqual(self.receipt()['status'], 'rolled_back')
        self.assertEqual(self.rollback()['status'], 'rolled_back')

    def test_rollback_recovery_and_receipt_failure_report_unknown_live_state(self):
        self.activate()
        self.always_fail_reload.touch()
        save_receipt = tls.save_receipt

        def fail_recovery_receipt(backup, receipt):
            if receipt['status'] == 'recovery_required':
                raise OSError('simulated disk full')
            return save_receipt(backup, receipt)

        with patch.object(tls, 'save_receipt', fail_recovery_receipt), self.assertRaises(RuntimeError) as raised:
            self.rollback()
        self.assertIn('status=recovery_required', str(raised.exception))
        self.assertIn('live Nginx configuration is unknown', str(raised.exception))
        self.assertIn('recovery receipt persistence failed', str(raised.exception))
        self.assertEqual(self.target.read_bytes(), self.candidate.read_bytes())
        self.assertEqual(self.receipt()['status'], 'rolling_back')

    def test_rollback_intermediate_receipt_failure_does_not_switch_configuration(self):
        self.activate()
        events_before = self.logged()
        with patch.object(tls, 'save_receipt', side_effect=OSError('simulated disk full')):
            with self.assertRaises(OSError):
                self.rollback()
        self.assertEqual(self.target.read_bytes(), self.candidate.read_bytes())
        self.assertEqual(self.logged(), events_before)
        self.assertEqual(self.receipt()['status'], 'active')

    def test_symlink_target_candidate_and_backup_parent_refused(self):
        alias = self.root / 'alias.conf'
        alias.symlink_to(self.target)
        with self.assertRaises(ValueError):
            tls.activate(alias, self.candidate, self.backup, self.nginx,
                         expected_candidate_sha256=tls.digest(self.candidate.read_bytes()))
        with self.assertRaises(ValueError):
            tls.activate(self.target, alias, self.backup, self.nginx,
                         expected_candidate_sha256=tls.digest(self.candidate.read_bytes()))
        directory_alias = self.root / 'alias-dir'
        directory_alias.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ValueError):
            tls.activate(self.target, self.candidate, directory_alias / 'backup', self.nginx,
                         expected_candidate_sha256=tls.digest(self.candidate.read_bytes()))
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


class RuntimeDiagnosticsTests(unittest.TestCase):
    """Exercise failure reports offline; no Docker or HTTP services are started."""

    def fixture(self):
        return runtime_test.Runtime(Path('/synthetic-fixture'), 'synthetic-image', {'checks': []})

    def test_non_200_echo_keeps_status_body_and_request_without_retry(self):
        fixture = self.fixture()
        body = b'<html>502 Bad Gateway</html>'
        with patch.object(fixture, 'request', return_value=(502, {'content-type': 'text/html'}, body)) as request:
            with self.assertRaisesRegex(AssertionError, 'returns HTTP 200'):
                fixture.api('bootstrap HTTP')
        self.assertEqual(request.call_count, 1)
        details = fixture.report['checks'][-1]['details']
        self.assertEqual(details['status'], 502)
        self.assertEqual(details['method'], 'GET')
        self.assertEqual(details['path'], '/api/runtime-echo/item%20one?method=GET&literal=a%2Fb')
        self.assertEqual(details['content_type'], 'text/html')
        self.assertEqual(details['body_preview'], body.decode())

    def test_malformed_echo_is_an_assertion_with_bounded_original_body(self):
        for body in (b'', b'<html>error</html>', b'=value', b'key=one\nkey=two', b'key=\xff'):
            with self.subTest(body=body):
                fixture = self.fixture()
                with self.assertRaises(AssertionError):
                    fixture.echo_response('fixture', 'POST', '/api/fixture', 200, {}, body)
                details = fixture.report['checks'][-1]['details']
                self.assertEqual(details['status'], 200)
                self.assertIn('format_error', details)
                self.assertEqual(details['body_preview'], body.decode('utf-8', errors='replace'))
        body = b'x' * (runtime_test.RESPONSE_PREVIEW_BYTES + 100)
        fixture = self.fixture()
        with self.assertRaises(AssertionError):
            fixture.echo_response('fixture', 'POST', '/api/fixture', 502, {}, body)
        details = fixture.report['checks'][-1]['details']
        self.assertEqual(len(details['body_preview']), runtime_test.RESPONSE_PREVIEW_BYTES)
        self.assertEqual(details['body_bytes'], len(body))
        self.assertTrue(details['body_truncated'])

    def test_valid_echo_preserves_empty_values_and_embedded_equals(self):
        fixture = self.fixture()
        values, details = fixture.echo_response('fixture', 'GET', '/api/fixture', 200,
            {'content-type': 'text/plain'}, b'method=GET\nuri=/api/fixture?item=a=b\nbody=')
        self.assertEqual(values, {'method': 'GET', 'uri': '/api/fixture?item=a=b', 'body': ''})
        self.assertEqual(details['status'], 200)
        self.assertTrue(fixture.report['checks'][-1]['passed'])

    def test_every_echo_entry_point_supplies_original_response_context(self):
        entries = (
            (lambda fixture: fixture.api('bootstrap HTTP'), 'bootstrap HTTP', 'GET',
             '/api/runtime-echo/item%20one?method=GET&literal=a%2Fb'),
            (lambda fixture: fixture.forwarded_header_boundary(), 'HTTPS forwarding boundary', 'GET',
             '/api/forwarded-boundary'),
            (lambda fixture: fixture.native_business('native HTTP'), 'native HTTP', 'POST',
             '/api/native-loopback?probe=1'))
        for invoke, stage, method, path in entries:
            with self.subTest(stage=stage):
                fixture = self.fixture()
                with patch.object(fixture, 'request', return_value=(502, {}, b'original response')), \
                        patch.object(fixture, 'record'), \
                        patch.object(fixture, 'echo_response', side_effect=AssertionError('echo reached')) as echo:
                    with self.assertRaisesRegex(AssertionError, 'echo reached'):
                        invoke(fixture)
                echo.assert_called_once_with(stage, method, path, 502, {}, b'original response')

    def test_stability_check_runs_all_four_methods_in_ten_rounds_without_sleep(self):
        fixture = self.fixture()

        def echo(method, path, *, tls=False, body=None):
            response = f'method={method}\nuri={path}\nbody={body or ""}\nscheme=http\nforwarded_proto=http'.encode()
            return 200, {'cross-origin-resource-policy': 'same-site'}, response

        with patch.object(fixture, 'request', side_effect=echo) as request, \
                patch.object(runtime_test.time, 'sleep', side_effect=AssertionError('no stability sleeps')):
            fixture.api_stability('bootstrap HTTP')
        self.assertEqual(request.call_count, 40)
        self.assertEqual([call.args[0] for call in request.call_args_list], ['GET', 'POST', 'PUT', 'DELETE'] * 10)
        self.assertEqual(fixture.report['api_stability']['rounds_completed'], 10)
        self.assertEqual(fixture.report['api_stability']['request_retries'], 0)
        self.assertTrue(all(row['passed'] for row in fixture.report['checks']))

    def test_stability_failure_stops_without_retry_and_preserves_round_and_method(self):
        fixture = self.fixture()
        with patch.object(fixture, 'request', return_value=(502, {}, b'upstream unavailable')) as request:
            with self.assertRaisesRegex(AssertionError, 'consecutive round 1/10'):
                fixture.api_stability('bootstrap HTTP')
        self.assertEqual(request.call_count, 1)
        self.assertEqual(fixture.report['api_stability']['rounds_completed'], 0)
        details = fixture.report['checks'][-1]['details']
        self.assertEqual(details['stage'], 'bootstrap HTTP consecutive round 1/10')
        self.assertEqual(details['method'], 'GET')
        self.assertEqual(details['status'], 502)
        self.assertEqual(details['body_preview'], 'upstream unavailable')

    def test_fixture_starts_persistent_upstream_with_loopback_binding(self):
        fixture = self.fixture()
        inspection = [{'NetworkSettings': {'Ports': {
            '80/tcp': [{'HostIp': '127.0.0.1', 'HostPort': '18001'}],
            '443/tcp': [{'HostIp': '127.0.0.1', 'HostPort': '18002'}]}}}]
        results = [subprocess.CompletedProcess([], 0, fixture.name, ''),
                   subprocess.CompletedProcess([], 0, json.dumps(inspection), '')]
        with patch.object(runtime_test, 'command', side_effect=results) as command, \
                patch.object(fixture, 'wait_until'), patch.object(fixture, 'worker_permissions'), \
                patch.object(fixture, 'nginx', return_value=subprocess.CompletedProcess([], 0)):
            fixture.start()
        arguments = command.call_args_list[0].args[0]
        script = arguments[-1]
        self.assertIn('nc -lk -s 127.0.0.1 -p 18080 -e /fixture/upstream.sh & ', script)
        self.assertNotIn('while true', script)
        self.assertEqual([arguments[index + 1] for index, value in enumerate(arguments) if value == '--publish'],
                         ['127.0.0.1::80', '127.0.0.1::443'])
        self.assertTrue(fixture.started)
        self.assertEqual((fixture.http_port, fixture.https_port), (18001, 18002))

    def failure_report(self, verify, *, logs_error=None, cleanup_error=None):
        events = []

        def prepare(fixture):
            fixture.record('synthetic setup', True)
            (fixture.directory / 'fixture-nginx-diagnostics.log').write_text('synthetic nginx diagnostic')

        def start(fixture):
            fixture.started = True

        def logs(args, *, check=True):
            self.assertEqual(args[:5], ['docker', 'logs', '--timestamps', '--tail', '100'])
            self.assertTrue(args[-1].startswith('teachingopen-ip-https-test-'))
            self.assertFalse(check)
            events.append('logs before cleanup')
            if logs_error:
                raise logs_error
            return subprocess.CompletedProcess(args, 0, 'x' * 20000, 'upstream connection refused')

        def cleanup(fixture):
            events.append('cleanup')
            if cleanup_error:
                raise cleanup_error
            fixture.started = False
            fixture.record('owned runtime container removed', True)

        with tempfile.TemporaryDirectory() as raw:
            output = Path(raw) / 'result.json'
            with patch.object(runtime_test.Runtime, 'prepare', prepare), \
                    patch.object(runtime_test.Runtime, 'start', start), \
                    patch.object(runtime_test.Runtime, 'verify', verify), \
                    patch.object(runtime_test.Runtime, 'cleanup', cleanup), \
                    patch.object(runtime_test, 'command', side_effect=logs), \
                    patch.object(sys, 'argv', ['runtime-test', '--output', str(output)]), redirect_stdout(io.StringIO()):
                result = runtime_test.main()
            self.assertEqual(result, 1)
            report = json.loads(output.read_text())
        self.assertFalse(report['passed'])
        self.assertEqual(set(report['scenarios']), {'template'})
        self.assertEqual(events, ['logs before cleanup', 'cleanup'])
        return report

    def test_http_failure_saves_json_and_bounded_logs_before_cleanup(self):
        def verify(fixture):
            fixture.echo_response('bootstrap HTTP', 'GET', '/api/fixture', 502,
                                  {'content-type': 'text/html'}, b'<html>502 Bad Gateway</html>')
        report = self.failure_report(verify)
        self.assertEqual(report['error_type'], 'AssertionError')
        scenario = report['scenarios']['template']
        self.assertFalse(scenario['passed'])
        self.assertEqual(scenario['nginx_diagnostics'], 'synthetic nginx diagnostic')
        self.assertTrue(scenario['docker_logs']['truncated'])
        self.assertEqual(len(scenario['docker_logs']['text']), runtime_test.DOCKER_LOG_CHARACTERS)
        self.assertTrue(scenario['docker_logs']['text'].endswith('upstream connection refused'))
        failed = [row for row in report['checks'] if not row['passed']]
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0]['details']['status'], 502)
        self.assertEqual(report['checks_passed'], 2)

    def test_unexpected_exception_still_saves_failure_json(self):
        def verify(fixture):
            raise ValueError('unexpected response parser failure')
        report = self.failure_report(verify)
        self.assertEqual(report['error_type'], 'ValueError')
        self.assertEqual(report['error'], 'unexpected response parser failure')
        self.assertEqual(report['scenarios']['template']['error_type'], 'ValueError')

    def test_log_or_cleanup_failure_cannot_replace_original_error(self):
        def verify(fixture):
            raise ValueError('original failure')
        report = self.failure_report(verify, logs_error=OSError('cannot read logs'))
        self.assertEqual(report['error'], 'original failure')
        self.assertEqual(report['scenarios']['template']['docker_logs_error'], 'OSError: cannot read logs')
        report = self.failure_report(verify, cleanup_error=RuntimeError('cleanup failure'))
        self.assertEqual(report['error'], 'original failure')
        self.assertEqual(report['scenarios']['template']['cleanup_error'], 'RuntimeError: cleanup failure')
        self.assertIn('docker_logs', report['scenarios']['template'])


if __name__ == '__main__':
    unittest.main()
