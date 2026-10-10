import os
import io
import json
from pathlib import Path
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
            name = sorted(java.EXPECTED)[0]
            (reports / ('TEST-' + name + '.xml')).write_text(
                '<testsuite name="' + name + '" tests="1" skipped="1"/>')
            with self.assertRaises(RuntimeError): java.check(reports)


class ReviewAdapterTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.temp = Path(self.directory.name).resolve()
        self.root = self.temp / 'repository'
        self.jar = self.root / 'api/jeecg-boot-module-system/target/teaching-open-2.8.0.jar'
        self.jar.parent.mkdir(parents=True)
        self.jar.write_bytes(b'unit-test candidate')
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

    def test_discovery_only_selects_present_probes_and_gates_course_fix(self):
        dev = self.root / 'api/dev'; dev.mkdir()
        for name in ('verify-work-stars.py', 'verify-course-update.py'):
            (dev / name).touch()
        request = self.root / 'CourseMapUpdateRequest.java'
        with patch.object(review, 'COURSE_REQUEST', request):
            self.assertEqual([p.name for p in review.selected_probes()], ['verify-work-stars.py'])
            request.touch()
            self.assertEqual([p.name for p in review.selected_probes()], ['verify-work-stars.py', 'verify-course-update.py'])

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
            for bad in ({key: []}, {key: [{'passed': False}]}, {'passed': 1}, {'jar_sha256': 'other'},
                        {'exception': 'SqlError'}, {'total': 3}, {'failed': 1}):
                with self.assertRaises(RuntimeError): review.validate_report({**report, **bad}, 'candidate')


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
