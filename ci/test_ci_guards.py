import ast
import os
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import check_java_results as java
import registration_mysql as registration
import review_mysql as review


class CiGuardsTest(unittest.TestCase):
    def test_configuration_comments_are_not_placeholders_but_missing_values_fail(self):
        template = '# Fill @PLACEHOLDER@ in a private copy\nserver.port=@API_PORT@\n'
        self.assertEqual(registration.render_properties(template, {'API_PORT':'18259'}),
                         'server.port=18259\n')
        with self.assertRaises(KeyError): registration.render_properties(template, {})

    def test_local_or_self_hosted_execution_is_rejected_before_connection(self):
        for environment in ({}, {'GITHUB_ACTIONS': 'true', 'RUNNER_ENVIRONMENT': 'self-hosted'}):
            with patch.dict(os.environ, environment, clear=True), patch.object(registration.subprocess, 'run') as call:
                with self.assertRaises(RuntimeError):
                    registration.main()
                call.assert_not_called()
            with patch.dict(os.environ, environment, clear=True), patch.object(review.subprocess, 'run') as call:
                with self.assertRaises(RuntimeError):
                    review.run_reviews(Path('/unrelated'), Path('/candidate'), 'mysql', Path('/root.cnf'), 'redis-cli', 'secret')
                call.assert_not_called()

    def test_unrelated_workspace_is_rejected_before_connection(self):
        with patch.dict(os.environ, {'GITHUB_ACTIONS':'true','RUNNER_ENVIRONMENT':'github-hosted',
                'GITHUB_WORKSPACE':'/unrelated'}, clear=True), patch.object(registration.subprocess, 'run') as call:
            with self.assertRaises(RuntimeError):
                registration.main()
            call.assert_not_called()

    def test_missing_or_skipped_java_suites_are_not_success(self):
        with tempfile.TemporaryDirectory() as raw:
            reports = Path(raw)
            with self.assertRaises(RuntimeError): java.check(reports)
            for name in java.EXPECTED:
                (reports / ('TEST-' + name + '.xml')).write_text(
                    '<testsuite name="' + name + '" tests="1" failures="0" errors="0" skipped="0"/>')
            self.assertEqual(java.check(reports)['tests'], len(java.EXPECTED))
            for name in sorted(java.EXPECTED):
                path = reports / ('TEST-' + name + '.xml')
                original = path.read_text()
                with self.subTest(suite=name, state='missing'):
                    path.unlink()
                    with self.assertRaises(RuntimeError): java.check(reports)
                for result in ('tests="0"', 'tests="1" failures="1"',
                               'tests="1" errors="1"', 'tests="1" skipped="1"'):
                    with self.subTest(suite=name, result=result):
                        path.write_text('<testsuite name="' + name + '" ' + result + '/>')
                        with self.assertRaises(RuntimeError): java.check(reports)
                path.write_text(original)

    def test_java_selection_cli_returns_complete_gate_set_without_requiring_reports(self):
        result = subprocess.run([sys.executable, str(Path(java.__file__).resolve()), '--list'],
                                check=True, capture_output=True, text=True)
        self.assertEqual(result.stdout.strip().split(','), sorted(java.EXPECTED))
        self.assertEqual(result.stderr, '')

    def test_all_current_java_regressions_are_required_except_documented_legacy_suites(self):
        sources = list((java.ROOT / 'api/jeecg-boot-module-system/src/test/java').rglob('*Test.java'))
        names = [path.stem for path in sources]
        self.assertEqual(len(names), len(set(names)), 'Java gate requires unambiguous suite names')
        self.assertEqual(set(names) - {'SampleTest', 'SecurityToolsTest'}, java.EXPECTED)


class ReviewAdapterTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.temp = Path(self.directory.name).resolve()
        self.root = self.temp / 'repository'
        self.jar = self.root / 'api/jeecg-boot-module-system/target/teaching-open-2.8.0.jar'
        self.jar.parent.mkdir(parents=True)
        self.jar.write_bytes(b'unit-test candidate')
        self.dev = self.root / 'api/dev'
        self.dev.mkdir()
        for name in review.PROBES:
            (self.dev / name).touch()
        self.runtime = self.temp / 'private-runtime'
        self.runtime.mkdir(mode=0o700)
        (self.runtime / 'config').mkdir(mode=0o700)
        (self.runtime / 'config/credentials.json').write_text(json.dumps({'test_user_password': 'synthetic'}))
        self.options = self.temp / 'root.cnf'
        self.options.write_text('[client]\nhost=127.0.0.1\nport=33306\nprotocol=tcp\nuser=root\npassword=synthetic\n')
        self.options.chmod(0o600)
        self.root_patch = patch.object(review, 'ROOT', self.root)
        self.root_patch.start(); self.addCleanup(self.root_patch.stop)
        # Unit-level dependency stubs only; no GitHub identity is fabricated and
        # no database, Redis, HTTP listener, or Java process is started.
        self.guard_patch = patch.object(review, 'require_hosted_runner')
        self.guard = self.guard_patch.start(); self.addCleanup(self.guard_patch.stop)
        self.env_patch = patch.dict(os.environ, {'RUNNER_TEMP': str(self.temp)})
        self.env_patch.start(); self.addCleanup(self.env_patch.stop)
        self.context = review.CiFixtureContext(self.runtime, self.jar, '/client/mysql', self.options,
                                             '/client/redis-cli', 'synthetic-redis')

    def test_binding_rejects_other_runtime_jar_connection_or_public_files_before_connection(self):
        with patch.object(review.subprocess, 'run') as connection:
            for runtime, jar in [(self.temp, self.jar), (self.runtime, self.temp / 'different.jar')]:
                with self.assertRaises(RuntimeError): self.context.guard(runtime, jar)
            self.options.chmod(0o644)
            with self.assertRaises(RuntimeError): self.context.guard()
            self.options.chmod(0o600)
            self.options.write_text('[client]\nhost=production.invalid\nport=33306\nprotocol=tcp\nuser=root\n')
            with self.assertRaises(RuntimeError): self.context.mysql_command(self.runtime)
            connection.assert_not_called()

    def test_sql_and_cache_commands_are_bound_to_fixed_container_endpoints(self):
        command = self.context.mysql_command(self.runtime)
        self.assertEqual(command[1], '--defaults-extra-file=' + str(self.options))
        with patch.object(review, 'run', return_value=b'1\n') as execute:
            self.assertEqual(self.context.sql('SELECT 1'), '1')
            self.assertEqual(execute.call_args.args[0][-1], 'teachingopen_dev')
            self.assertEqual(execute.call_args.kwargs['input'], b'SELECT 1')
            self.assertEqual(self.context.cache('GET', 'synthetic-key'), '1')
            self.assertEqual(execute.call_args.args[0], ['/client/redis-cli', '-h', '127.0.0.1',
                             '-p', '36379', '--raw', '-n', '4', 'GET', 'synthetic-key'])
            self.assertEqual(execute.call_args.kwargs['env']['REDISCLI_AUTH'], 'synthetic-redis')

    def test_candidate_requires_live_process_exact_config_hash_and_five_accounts(self):
        self.context.properties = 'private configuration\n'
        review.private_file(self.context.config, self.context.properties)
        self.context.process = Mock(pid=123)
        self.context.process.poll.return_value = 0
        with patch.object(review.subprocess, 'check_output') as inspect:
            with self.assertRaises(RuntimeError): self.context.assert_candidate(self.runtime, self.jar)
            inspect.assert_not_called()
        self.context.process.poll.return_value = None
        self.context.config.write_text('different configuration')
        with self.assertRaises(RuntimeError): self.context.assert_candidate(self.runtime, self.jar)
        self.context.config.write_text(self.context.properties)
        (self.runtime / 'logs').mkdir(mode=0o700)
        review.private_file(self.runtime / 'logs/application.log', 'synthetic application log\n')
        self.context.record_process()
        command = 'java -jar ' + str(self.jar) + ' --spring.config.location=file:' + str(self.context.config)
        names = '\n'.join(['fixture_admin', 'fixture_student_a', 'fixture_student_b', 'fixture_teacher_a', 'fixture_teacher_b'])
        with patch.object(review.subprocess, 'check_output', return_value=command), \
                patch.object(self.context, 'sql', return_value=names) as sql, \
                patch.object(self.context, 'cache', return_value='port\n6379'):
            self.context.assert_candidate(self.runtime, self.jar)
            sql.return_value = 'original-user'
            with self.assertRaises(RuntimeError): self.context.assert_candidate(self.runtime, self.jar)
        self.jar.write_bytes(b'rebuilt candidate')
        with self.assertRaises(RuntimeError): self.context.assert_candidate(self.runtime, self.jar)

    def test_private_process_record_binds_audit_log_to_current_candidate_before_connections(self):
        self.context.properties = 'private configuration\n'
        review.private_file(self.context.config, self.context.properties)
        (self.runtime / 'logs').mkdir(mode=0o700)
        log = self.runtime / 'logs/application.log'
        review.private_file(log, 'synthetic application log\n')
        self.context.process = Mock(pid=123)
        self.context.process.poll.return_value = 0
        with self.assertRaises(RuntimeError):
            self.context.record_process()
        self.assertFalse((self.runtime / 'backend-process.json').exists())
        self.context.process.poll.return_value = None
        self.context.record_process()
        record = self.runtime / 'backend-process.json'
        expected = {'pid': 123, 'jar_path': str(self.jar), 'jar_sha256': self.context.jar_sha256,
                    'application_config': str(self.context.config), 'log_path': str(log)}
        self.assertEqual(json.loads(record.read_text()), expected)
        self.assertEqual(record.stat().st_mode & 0o777, 0o600)
        with self.assertRaises(FileExistsError):
            self.context.record_process()
        with patch.object(self.context, 'sql') as sql, patch.object(self.context, 'cache') as cache, \
                patch.object(review.subprocess, 'check_output') as process:
            for key, value in [('pid', 124), ('jar_path', '/unrelated.jar'),
                               ('jar_sha256', 'different'), ('application_config', '/unrelated.properties'),
                               ('log_path', str(self.temp / 'unrelated.log'))]:
                with self.subTest(key=key):
                    record.write_text(json.dumps({**expected, key: value}))
                    with self.assertRaises(RuntimeError):
                        self.context.assert_candidate(self.runtime, self.jar)
            record.write_text(json.dumps(expected))
            for path in (record, log):
                with self.subTest(public_path=path.name):
                    path.chmod(0o644)
                    with self.assertRaises(RuntimeError):
                        self.context.assert_candidate(self.runtime, self.jar)
                    path.chmod(0o600)
            record.write_text('{invalid')
            with self.assertRaises(RuntimeError):
                self.context.assert_candidate(self.runtime, self.jar)
            record.write_text(json.dumps(expected))
            log.unlink()
            external = self.temp / 'unrelated.log'
            review.private_file(external, 'unrelated application log')
            log.symlink_to(external)
            with self.assertRaises(RuntimeError):
                self.context.assert_candidate(self.runtime, self.jar)
            log.unlink()
            with self.assertRaises(RuntimeError):
                self.context.assert_candidate(self.runtime, self.jar)
            review.private_file(log, 'synthetic application log\n')
            record.unlink()
            with self.assertRaises(RuntimeError):
                self.context.assert_candidate(self.runtime, self.jar)
            external_record = self.temp / 'unrelated-process.json'
            review.private_file(external_record, json.dumps(expected))
            record.symlink_to(external_record)
            with self.assertRaises(RuntimeError):
                self.context.assert_candidate(self.runtime, self.jar)
            sql.assert_not_called(); cache.assert_not_called(); process.assert_not_called()

    def test_adapter_reuses_actual_http_client_and_restores_dependencies_on_exception(self):
        with patch.object(sys, 'path', [str(registration.ROOT / 'api/dev')] + sys.path):
            import local_http
            import local_recovery
        base = local_http.FixtureApi
        adapter = self.context.fixture_api(base)
        self.assertIs(adapter.request, base.request)
        self.assertIs(adapter.login, base.login)
        with patch.object(self.context, 'assert_candidate') as validate:
            api = adapter(self.runtime, self.jar)
            validate.assert_called_once_with(self.runtime, self.jar)
        api.tokens['student_a'] = 'synthetic-token'
        response = io.BytesIO(b'{"success":true}')
        response.status = 200; response.headers = {'Content-Type': 'application/json'}
        with patch.object(local_http, 'urlopen', return_value=response) as http:
            status, payload, _ = api.request('PUT', '/synthetic', 'student_a', {'example': 1})
            self.assertEqual((status, payload), (200, {'success': True}))
            request = http.call_args.args[0]
            self.assertEqual(request.full_url, 'http://127.0.0.1:18259/api/synthetic')
            self.assertEqual(request.get_header('X-access-token'), 'synthetic-token')
        original_sql = local_recovery.mysql_command
        module = SimpleNamespace(FixtureApi=base, mysql_command=original_sql)
        with self.assertRaises(ValueError):
            with review.probe_adapter(module, self.context):
                self.assertIsNot(module.FixtureApi, base)
                self.assertEqual(module.mysql_command(self.runtime), self.context.mysql_command(self.runtime))
                raise ValueError('unit probe failure')
        self.assertIs(module.FixtureApi, base)
        self.assertIs(module.mysql_command, original_sql)
        self.assertIs(local_recovery.mysql_command, original_sql)

    def test_actual_probe_interfaces_bind_the_candidate_and_restore_local_clients(self):
        real_dev = registration.ROOT / 'api/dev'
        args = review.probe_arguments(self.context, self.root / 'ci-results/fixture.json')
        self.assertEqual((args.runtime, args.jar, args.expect_legacy), (self.runtime, self.jar, False))
        with patch.object(sys, 'path', [str(real_dev)] + sys.path):
            import local_recovery
            original_sql = local_recovery.mysql_command
            for name in review.PROBES:
                with self.subTest(probe=name):
                    path = real_dev / name
                    tree = ast.parse(path.read_text())
                    fields = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
                              and isinstance(node.value, ast.Name) and node.value.id == 'args'}
                    self.assertTrue(fields.issubset(vars(args)), 'Probe requires unsupported runner arguments: ' + name)
                    module = registration.load('unit_' + path.stem.replace('-', '_'), path)
                    self.assertTrue(callable(module.verify))
                    original_api = module.FixtureApi
                    original_probe_sql = getattr(module, 'mysql_command', None)
                    with patch.object(self.context, 'assert_candidate') as validate:
                        with self.assertRaisesRegex(ValueError, 'injected adapter failure'):
                            with review.probe_adapter(module, self.context):
                                api = module.FixtureApi(args.runtime, args.jar)
                                self.assertEqual(api.ports, {'mysql': 33306, 'redis': 36379, 'backend': 18259})
                                validate.assert_called_once_with(self.runtime, self.jar)
                                self.assertEqual(local_recovery.mysql_command(self.runtime), self.context.mysql_command(self.runtime))
                                if original_probe_sql is not None:
                                    self.assertEqual(module.mysql_command(self.runtime), self.context.mysql_command(self.runtime))
                                if name == 'verify-audit-failure.py':
                                    with patch.object(local_recovery, 'command', return_value='fixture result') as query:
                                        self.assertEqual(module.sql(self.runtime, 'SELECT 1'), 'fixture result')
                                        self.assertEqual(query.call_args.args[1], self.context.mysql_command(self.runtime) + ['--raw', '-e', 'SELECT 1'])
                                raise ValueError('injected adapter failure')
                    self.assertIs(module.FixtureApi, original_api)
                    self.assertIs(local_recovery.mysql_command, original_sql)
                    if original_probe_sql is not None:
                        self.assertIs(module.mysql_command, original_probe_sql)

    def test_current_baseline_requires_complete_probe_set_including_core_work_flows(self):
        self.assertEqual([p.name for p in review.selected_probes()], list(review.PROBES))
        self.assertEqual(len(review.PROBES), len(set(review.PROBES)))
        self.assertTrue({'verify-course-update.py', 'verify-work-submission.py',
                         'verify-feedback-preservation.py', 'verify-teaching-menu-security.py',
                         'verify-audit-log-authorization.py', 'verify-audit-failure.py',
                         'verify-file-deletion-concurrency.py', 'verify-file-encoded-reference-deletion.py',
                         'verify-additional-work-read-authorization.py', 'verify-shared-resource-boundaries.py',
                         'verify-global-rule-boundaries.py', 'verify-global-management-authorization.py',
                         'verify-minio-demo-disabled.py'
                         }.issubset(review.PROBES))

    def test_each_missing_or_renamed_required_probe_stops_before_any_runtime_activity(self):
        for name in review.PROBES:
            for replacement in (None, '.renamed'):
                with self.subTest(probe=name, replacement=replacement):
                    path = self.dev / name
                    if replacement is None:
                        path.unlink()
                    else:
                        path.rename(path.with_suffix(replacement))
                    try:
                        with self.assertRaisesRegex(RuntimeError, 'Missing required probes: ' + name):
                            review.selected_probes()
                        with patch.object(review, 'CiFixtureContext') as context, \
                                patch.object(review.Path, 'mkdir') as mkdir, \
                                patch.object(review.subprocess, 'Popen') as application, \
                                patch.object(review.subprocess, 'run') as connect:
                            with self.assertRaisesRegex(RuntimeError, 'Missing required probes: ' + name):
                                review.run_reviews(self.runtime, self.jar, '/client/mysql', self.options,
                                                   '/client/redis-cli', 'synthetic')
                            context.assert_not_called(); mkdir.assert_not_called()
                            application.assert_not_called(); connect.assert_not_called()
                        with patch.object(registration, 'require_hosted_runner'), \
                                patch.object(registration.tempfile, 'TemporaryDirectory') as temporary, \
                                patch.object(registration.subprocess, 'Popen') as application, \
                                patch.object(registration.subprocess, 'run') as connect:
                            with self.assertRaisesRegex(RuntimeError, 'Missing required probes: ' + name):
                                registration.main()
                            temporary.assert_not_called(); application.assert_not_called(); connect.assert_not_called()
                    finally:
                        if replacement is not None:
                            path.with_suffix(replacement).rename(path)
                        else:
                            path.touch()

    def test_empty_probe_directory_reports_every_missing_requirement(self):
        for path in self.dev.iterdir():
            path.unlink()
        with self.assertRaisesRegex(RuntimeError, 'Missing required probes:') as failure:
            review.selected_probes()
        for name in review.PROBES:
            self.assertIn(name, str(failure.exception))

    def test_existing_database_error_stops_before_seed_or_application(self):
        with patch.object(review.CiFixtureContext, 'sql', side_effect=['3306', RuntimeError('database exists')]) as sql, \
                patch.object(review.CiFixtureContext, 'cache', side_effect=['port\n6379', '0']), \
                patch.object(review.subprocess, 'Popen') as application:
            with self.assertRaises(RuntimeError):
                review.run_reviews(self.runtime, self.jar, '/client/mysql', self.options, '/client/redis-cli', 'synthetic')
            self.assertEqual(sql.call_args.args[0], 'CREATE DATABASE teachingopen_dev CHARACTER SET utf8mb4')
            application.assert_not_called()

    def test_report_requires_real_nonempty_checks_matching_the_candidate(self):
        for key, passed in [('cases', True), ('checks', 2)]:
            report = {key: [{'passed': True}, {'passed': True}], 'passed': passed, 'jar_sha256': 'candidate'}
            self.assertEqual(review.validate_report(report, 'candidate'), 2)
            for bad in ({key: []}, {key: None}, {key: {}}, {key: [None]}, {key: [{}]},
                        {key: [{'passed': False}]}, {key: [{'passed': 1}]},
                        {'passed': 1}, {'passed': False}, {'passed': 2.0}, {'passed': '2'},
                        {'jar_sha256': 'other'}, {'jar_sha256': None}, {'exception': 'SqlError'},
                        {'total': 3}, {'total': 2.0}, {'failed': 1}, {'expected_legacy': True},
                        {'expected_legacy_teacher_list': True}, {'expected_legacy_management_list': True},
                        {'cleanup_exception': 'SqlError'},
                        {'completed': False}, {'completed': None}, {'completed': 1}):
                with self.subTest(key=key, bad=bad), self.assertRaises(RuntimeError):
                    review.validate_report({**report, **bad}, 'candidate')
        for report in (None, [], 'complete'):
            with self.subTest(report=report), self.assertRaises(RuntimeError):
                review.validate_report(report, 'candidate')


class FixtureSeedTest(unittest.TestCase):
    def seed_module(self):
        with patch.object(sys, 'path', [str(registration.ROOT / 'api/dev')] + sys.path):
            return registration.load('unit_fixture_seed', registration.ROOT / 'api/dev/seed-fixtures.py')

    def test_builder_creates_exact_synthetic_fixtures_before_migration_without_connecting(self):
        module = self.seed_module()
        with tempfile.TemporaryDirectory() as raw:
            runtime = Path(raw); (runtime / 'uploads').mkdir()
            with patch.object(module, 'assert_database') as database, \
                    patch.object(module.subprocess, 'run') as compile_java, \
                    patch.object(module.subprocess, 'check_output', return_value='encrypted-fixture') as password:
                statements, accounts = module.build_fixture_seed(registration.ROOT / 'api', runtime,
                    Path('/unit/jdk'), {'test_user_password': 'synthetic-password'})
                database.assert_not_called()
                self.assertEqual(compile_java.call_count, 1)
                self.assertEqual(password.call_count, 5)
                for call in password.call_args_list:
                    self.assertIn('synthetic-password\n', call.kwargs['input'])
                    self.assertNotIn('synthetic-password', call.args[0])
            self.assertEqual(set(accounts), {'fixture_admin', 'fixture_teacher_a', 'fixture_teacher_b',
                                             'fixture_student_a', 'fixture_student_b'})
            self.assertEqual([p.read_text() for p in sorted((runtime / 'uploads').iterdir())],
                             ['synthetic work a\n', 'synthetic work b\n'])
            self.assertLess(statements.index('fixture_role_student'), statements.index('COMMIT;'))
            self.assertLess(statements.index('fixture_allow_registration'), statements.index('COMMIT;'))
            self.assertLess(statements.index('COMMIT;'), statements.index('DROP PROCEDURE IF EXISTS'))
            self.assertEqual(statements.count('INSERT INTO `sys_user`'), 5)

    def test_local_seed_keeps_ownership_guard_before_builder_or_connection(self):
        module = self.seed_module()
        with patch.object(module, 'assert_database', side_effect=RuntimeError('wrong server')), \
                patch.object(module, 'build_fixture_seed') as build, patch.object(module.subprocess, 'run') as connect:
            with self.assertRaises(RuntimeError): module.seed(Path('/unowned'), Path('/unit/jdk'))
            build.assert_not_called(); connect.assert_not_called()


if __name__ == '__main__': unittest.main()
