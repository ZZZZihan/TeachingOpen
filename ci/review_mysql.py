#!/usr/bin/env python3
"""Run review probes against new synthetic GitHub-hosted service-container data.

The local FixtureApi ownership checks remain unchanged. This adapter is scoped
to one private runner directory, the built candidate process, and fixed CI ports.
"""
from contextlib import contextmanager
import configparser
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import time
from types import SimpleNamespace
import urllib.error
import urllib.request

from registration_mysql import ROOT, load, render_properties, require_hosted_runner, run

DATABASE = 'teachingopen_dev'
REDIS_DATABASE = 4
QUARTZ_TABLES = frozenset('QRTZ_' + name for name in (
    'BLOB_TRIGGERS', 'CALENDARS', 'CRON_TRIGGERS', 'FIRED_TRIGGERS', 'JOB_DETAILS',
    'LOCKS', 'PAUSED_TRIGGER_GRPS', 'SCHEDULER_STATE', 'SIMPLE_TRIGGERS',
    'SIMPROP_TRIGGERS', 'TRIGGERS',
))
PROBES = (
    'verify-public-boundaries.py',
    'verify-duplicate-check.py',
    'verify-dictionary-management.py',
    'verify-unit-view-statistics.py',
    'verify-news-content.py',
    'verify-account-authorization.py',
    'verify-additional-work-authorization.py',
    'verify-work-stars.py',
    'verify-work-cloning.py',
    'verify-pagination.py',
    'verify-course-update.py',
    'verify-work-submission.py',
    'verify-feedback-preservation.py',
    'verify-infrastructure-authorization.py',
    'verify-announcement-authorization.py',
    'verify-user-query-boundaries.py',
    'verify-work-reference-authorization.py',
    'verify-teaching-menu-security.py',
    'verify-audit-log-authorization.py',
    'verify-file-deletion-concurrency.py',
    'verify-file-encoded-reference-deletion.py',
    'verify-additional-work-read-authorization.py',
    'verify-shared-resource-boundaries.py',
    'verify-global-rule-boundaries.py',
    'verify-global-management-authorization.py',
    'verify-audit-failure.py',
)


def private_file(path, content):
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w') as out:
        out.write(content)


def selected_probes():
    """Require the complete current baseline, including renamed or deleted probes."""
    paths = [ROOT / 'api/dev' / name for name in PROBES]
    missing = [path.name for path in paths if not path.is_file()]
    if missing:
        raise RuntimeError('Missing required probes: ' + ', '.join(missing))
    return paths


def validate_report(report, jar_sha256):
    if not isinstance(report, dict):
        raise RuntimeError('Review probe evidence must be a JSON object')
    cases = report.get('cases', report.get('checks'))
    if (not isinstance(cases, list) or not cases
            or any(not isinstance(case, dict) or case.get('passed') is not True for case in cases)
            or report.get('exception') or report.get('failed', 0) != 0 or report.get('expected_legacy')
            or report.get('completed', True) is not True
            or report.get('jar_sha256') != jar_sha256):
        raise RuntimeError('Review probe did not produce complete passing candidate evidence')
    passed = report.get('passed')
    if passed is not True and (type(passed) is not int or passed != len(cases)):
        raise RuntimeError('Review probe passing count does not match its executed checks')
    if 'total' in report and (type(report['total']) is not int or report['total'] != len(cases)):
        raise RuntimeError('Review probe total does not match its executed checks')
    return len(cases)


def jdbc_review_schema(schema):
    """Name only the fresh fixture's Quartz tables as StdJDBCDelegate queries them.

    The historical dump uses lowercase names. Linux MySQL resolves table names
    case-sensitively, while Quartz appends uppercase names to its QRTZ_ prefix.
    Keep the source dump, every table definition, and all non-Quartz names intact.
    This does not migrate or certify any existing deployment's schema.
    """
    names = re.findall(r'^CREATE TABLE `([^`]+)`', schema, re.MULTILINE)
    quartz = [name.upper() for name in names if name.upper().startswith('QRTZ_')]
    if len(quartz) != len(QUARTZ_TABLES) or set(quartz) != QUARTZ_TABLES:
        raise RuntimeError('Unexpected review Quartz table set')
    pattern = r'`(' + '|'.join(sorted(QUARTZ_TABLES)) + r')`'
    # The same exact-identifier replacement includes foreign-key targets, but
    # leaves constraint identifiers, columns and table definitions unchanged.
    return re.sub(pattern, lambda match: '`' + match[1].upper() + '`', schema, flags=re.IGNORECASE)


def jdbc_review_properties(properties):
    """Use persisted scheduler state only in the private review application."""
    pairs = [line.split('=', 1) for line in properties.splitlines() if '=' in line]
    config = dict(pairs)
    expected = {'spring.quartz.job-store-type': 'memory', 'spring.quartz.auto-startup': 'false',
                'spring.quartz.overwrite-existing-jobs': 'false', 'spring.quartz.jdbc.initialize-schema': 'never'}
    if len(config) != len(pairs) or any(config.get(key) != value for key, value in expected.items()):
        raise RuntimeError('Unexpected Quartz fixture safety configuration')
    prefix = 'spring.quartz.properties.org.quartz.jobStore.'
    if any(key.startswith(prefix) for key in config):
        raise RuntimeError('Unexpected Quartz fixture JobStore override')
    return (properties.replace('spring.quartz.job-store-type=memory\n', 'spring.quartz.job-store-type=jdbc\n')
            + prefix + 'tablePrefix=QRTZ_\n' + prefix + 'isClustered=false\n')


class CiFixtureContext:
    def __init__(self, runtime, jar, mysql, root_options, redis, redis_password):
        self.runtime = Path(runtime).resolve()
        self.jar = Path(jar).resolve()
        self.mysql = mysql
        self.root_options = Path(root_options).resolve()
        self.redis = redis
        self.redis_password = redis_password
        self.process = None
        self.jar_sha256 = hashlib.sha256(self.jar.read_bytes()).hexdigest()
        self.config = self.runtime / 'application.properties'
        self.log_path = self.runtime / 'logs/application.log'
        self.process_record = self.runtime / 'backend-process.json'
        self.properties = None

    def guard(self, runtime=None, jar=None):
        require_hosted_runner()
        temp = Path(os.environ['RUNNER_TEMP']).resolve()
        if (not self.runtime.is_relative_to(temp) or self.runtime == temp
                or not self.root_options.is_relative_to(temp)
                or self.runtime.stat().st_mode & 0o077
                or self.root_options.stat().st_mode & 0o077):
            raise RuntimeError('CI fixture files must belong to a private runner temporary directory')
        if runtime is not None and Path(runtime).resolve() != self.runtime:
            raise RuntimeError('Unexpected CI fixture runtime')
        if jar is not None and Path(jar).resolve() != self.jar:
            raise RuntimeError('Unexpected CI candidate JAR')
        if self.jar != (ROOT / 'api/jeecg-boot-module-system/target/teaching-open-2.8.0.jar').resolve():
            raise RuntimeError('CI probes must use the built repository candidate')
        options = configparser.ConfigParser(interpolation=None)
        options.read_string(self.root_options.read_text())
        if options.sections() != ['client'] or set(options['client']) != {'host', 'port', 'protocol', 'user', 'password'}:
            raise RuntimeError('Unexpected CI MySQL options')
        for key, value in {'host': '127.0.0.1', 'port': '33306', 'protocol': 'tcp', 'user': 'root'}.items():
            if options['client'].get(key) != value:
                raise RuntimeError('Unexpected CI MySQL connection')

    def mysql_command(self, runtime):
        self.guard(runtime)
        return [self.mysql, '--defaults-extra-file=' + str(self.root_options),
                '--default-character-set=utf8mb4', '--batch', '--skip-column-names']

    def sql(self, statement, database=True):
        command = self.mysql_command(self.runtime) + ([DATABASE] if database else [])
        return run(command, input=statement.encode()).decode().strip()

    def cache(self, *args):
        self.guard()
        command = [self.redis, '-h', '127.0.0.1', '-p', '36379', '--raw',
                   '-n', str(REDIS_DATABASE)] + list(args)
        return run(command, env=dict(os.environ, REDISCLI_AUTH=self.redis_password)).decode().strip()

    def _process_metadata(self):
        return {'pid': self.process.pid, 'jar_path': str(self.jar), 'jar_sha256': self.jar_sha256,
                'application_config': str(self.config), 'log_path': str(self.log_path)}

    def _assert_private_log(self):
        if (not self.log_path.is_file() or self.log_path.resolve() != self.log_path
                or self.log_path.stat().st_mode & 0o077):
            raise RuntimeError('CI candidate log must be the private owned application log')

    def record_process(self):
        """Expose the actual log to fault probes without publishing its contents."""
        self.guard()
        if self.process is None or self.process.poll() is not None:
            raise RuntimeError('Cannot record a stopped CI candidate process')
        self._assert_private_log()
        private_file(self.process_record, json.dumps(self._process_metadata()) + '\n')

    def assert_candidate(self, runtime, jar):
        self.guard(runtime, jar or self.jar)
        if (self.process is None or self.process.poll() is not None
                or self.properties is None or self.config.read_text() != self.properties
                or self.config.stat().st_mode & 0o077
                or hashlib.sha256(self.jar.read_bytes()).hexdigest() != self.jar_sha256):
            raise RuntimeError('CI fixture application is not the configured candidate process')
        self._assert_private_log()
        if (not self.process_record.is_file() or self.process_record.resolve() != self.process_record
                or self.process_record.stat().st_mode & 0o077):
            raise RuntimeError('CI candidate process record must be private and owned')
        try:
            metadata = json.loads(self.process_record.read_text())
        except (OSError, ValueError):
            raise RuntimeError('CI candidate process record is unreadable') from None
        if metadata != self._process_metadata():
            raise RuntimeError('CI candidate process record does not match its process, JAR, configuration and log')
        command = subprocess.check_output(['ps', '-p', str(self.process.pid), '-o', 'command='], text=True)
        if str(self.jar) not in command or '--spring.config.location=file:' + str(self.config) not in command:
            raise RuntimeError('CI candidate process command does not match the private configuration')
        names = self.sql('SELECT username FROM sys_user ORDER BY username').splitlines()
        if names != ['fixture_admin', 'fixture_student_a', 'fixture_student_b', 'fixture_teacher_a', 'fixture_teacher_b']:
            raise RuntimeError('CI review database must contain exactly the five synthetic accounts')
        if self.cache('CONFIG', 'GET', 'port').splitlines() != ['port', '6379']:
            raise RuntimeError('Unexpected CI Redis service container')

    def fixture_api(self, base):
        context = self

        class CiFixtureApi(base):
            def __init__(self, runtime, jar=None):
                context.assert_candidate(runtime, jar)
                self.runtime = context.runtime
                self.ports = {'mysql': 33306, 'redis': 36379, 'backend': 18259}
                self.jar_sha256 = context.jar_sha256
                self.credentials = json.loads((self.runtime / 'config/credentials.json').read_text())
                self.tokens = {}

            def cache(self, *args):
                return context.cache(*args)

        return CiFixtureApi


@contextmanager
def probe_adapter(module, context):
    """Replace only the probe's injected client and SQL command during this run."""
    recovery = importlib.import_module('local_recovery')
    original_api = module.FixtureApi
    original_sql = recovery.mysql_command
    has_sql = hasattr(module, 'mysql_command')
    original_probe_sql = getattr(module, 'mysql_command', None)
    module.FixtureApi = context.fixture_api(original_api)
    recovery.mysql_command = context.mysql_command
    if has_sql:
        module.mysql_command = context.mysql_command
    try:
        yield
    finally:
        module.FixtureApi = original_api
        recovery.mysql_command = original_sql
        if has_sql:
            module.mysql_command = original_probe_sql


def run_reviews(parent_runtime, jar, mysql, root_options, redis, redis_password):
    require_hosted_runner()  # Before file creation, process start, or a connection.
    probes = selected_probes()  # Missing coverage must fail before runtime creation.
    parent = Path(parent_runtime).resolve()
    temp = Path(os.environ['RUNNER_TEMP']).resolve()
    if parent == temp or not parent.is_relative_to(temp) or parent.stat().st_mode & 0o077:
        raise RuntimeError('CI review runtime must belong to a private runner temporary directory')
    runtime = parent / 'reviews'
    runtime.mkdir(mode=0o700)
    for name in ('config', 'uploads', 'webapp', 'multipart', 'logs'):
        (runtime / name).mkdir(mode=0o700)
    context = CiFixtureContext(runtime, jar, mysql, root_options, redis, redis_password)
    context.guard()
    if context.sql('SELECT @@port', database=False) != '3306':
        raise RuntimeError('Unexpected CI MySQL service container')
    if context.cache('CONFIG', 'GET', 'port').splitlines() != ['port', '6379'] or context.cache('DBSIZE') != '0':
        raise RuntimeError('Review Redis database must be a fresh CI service-container database')
    # Never reuse, drop, reset, or import original upstream data.
    context.sql('CREATE DATABASE ' + DATABASE + ' CHARACTER SET utf8mb4', database=False)
    schema = load('review_schema', ROOT / 'api/dev/extract-schema.py').extract_schema(
        (ROOT / 'api/db/teachingopen2.8.sql').read_text())
    context.sql(jdbc_review_schema(schema))
    if context.sql('SELECT @@lower_case_table_names') != '0':
        raise RuntimeError('Review requires the case-sensitive Linux MySQL table-name mode')
    quartz_tables = context.sql("SELECT table_name FROM information_schema.tables "
        "WHERE table_schema=DATABASE() AND LEFT(UPPER(table_name),5)='QRTZ_' ORDER BY BINARY table_name").splitlines()
    if quartz_tables != sorted(QUARTZ_TABLES):
        raise RuntimeError('Actual review Quartz table names do not match StdJDBCDelegate')
    migrations = ('unit-view-events.sql', 'work-events.sql')
    for _ in range(2):
        for name in migrations:
            context.sql((ROOT / 'api/db' / name).read_text())
    if context.sql('SELECT COUNT(*) FROM sys_user') != '0':
        raise RuntimeError('Review schema must contain no original accounts')

    dev = str(ROOT / 'api/dev')
    sys.path.insert(0, dev)
    try:
        seed = load('review_seed', ROOT / 'api/dev/seed-fixtures.py')
        java_home = Path(os.environ['JAVA_HOME']).resolve()
        credentials = {'test_user_password': secrets.token_hex(24), 'redis_password': redis_password}
        private_file(runtime / 'config/credentials.json', json.dumps(credentials))
        statements, accounts = seed.build_fixture_seed(ROOT / 'api', runtime, java_home, credentials)
        context.sql(statements)
        if len(accounts) != 5 or context.sql('SELECT COUNT(*) FROM sys_user') != '5':
            raise RuntimeError('Review synthetic fixture seed did not create exactly five accounts')
        private_file(runtime / 'fixture-accounts.json', json.dumps(accounts, ensure_ascii=False))
        app_password = secrets.token_hex(24)
        context.sql("CREATE USER 'teaching_review_ci'@'%' IDENTIFIED BY '" + app_password + "';"
                    "GRANT SELECT,INSERT,UPDATE,DELETE ON " + DATABASE + ".* TO 'teaching_review_ci'@'%';", database=False)
        values = {
            'API_BIND_ADDRESS': '127.0.0.1', 'API_PORT': '18259',
            'MYSQL_JDBC_URL': 'jdbc:mysql://127.0.0.1:33306/' + DATABASE + '?characterEncoding=UTF-8&useUnicode=true&useSSL=false&allowPublicKeyRetrieval=true&serverTimezone=Asia/Shanghai',
            'MYSQL_APP_USERNAME': 'teaching_review_ci', 'MYSQL_APP_PASSWORD': app_password,
            'REDIS_HOST': '127.0.0.1', 'REDIS_PORT': '36379', 'REDIS_DATABASE': str(REDIS_DATABASE),
            'REDIS_PASSWORD': redis_password, 'PUBLIC_ORIGIN': 'http://127.0.0.1:18259',
            'MULTIPART_DIRECTORY': str(runtime / 'multipart'), 'UPLOAD_DIRECTORY': str(runtime / 'uploads'),
            'WEBAPP_DIRECTORY': str(runtime / 'webapp'),
        }
        context.properties = jdbc_review_properties(render_properties(
            (ROOT / 'deploy/application-launch.properties.template').read_text(), values))
        private_file(context.config, context.properties)
        output = ROOT / 'ci-results'
        output.mkdir(exist_ok=True)
        with os.fdopen(os.open(context.log_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb') as log:
            context.process = subprocess.Popen([str(java_home / 'bin/java'), '-Xms256m', '-Xmx1024m',
                '-jar', str(context.jar), '--spring.config.location=file:' + str(context.config)],
                cwd=runtime / 'webapp', stdout=log, stderr=log)
            try:
                context.record_process()
                for _ in range(120):
                    if context.process.poll() is not None:
                        raise RuntimeError('Review application exited before health check')
                    try:
                        with urllib.request.urlopen('http://127.0.0.1:18259/api/actuator/health', timeout=2) as response:
                            if json.load(response).get('status') == 'UP':
                                break
                    except (urllib.error.URLError, TimeoutError):
                        pass
                    time.sleep(1)
                else:
                    raise RuntimeError('Review application did not become healthy')
                results = []
                for path in probes:
                    module = load('ci_' + path.stem.replace('-', '_'), path)
                    evidence = output / (path.stem.removeprefix('verify-') + '.json')
                    if evidence.exists():
                        raise RuntimeError('Existing review evidence must be preserved')
                    args = SimpleNamespace(runtime=runtime, jar=context.jar, output=evidence, expect_legacy=False)
                    with probe_adapter(module, context):
                        module.verify(args)
                    report = json.loads(evidence.read_text())
                    count = validate_report(report, context.jar_sha256)
                    report.update({'ci_environment': 'github-hosted service containers',
                        'github_sha': os.environ.get('GITHUB_SHA'), 'production_connected': False})
                    evidence.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
                    evidence.chmod(0o600)
                    results.append({'probe': path.name, 'checks': count})
                summary = {'github_sha': os.environ.get('GITHUB_SHA'), 'jar_sha256': context.jar_sha256,
                    'database': DATABASE, 'original_accounts_imported': 0, 'fixture_accounts': 5,
                    'production_connected': False, 'probes': results,
                    'required_probes': list(PROBES), 'probe_count': len(results),
                    'checks': sum(result['checks'] for result in results),
                    'migrations_applied_twice': list(migrations),
                    'quartz_review_fixture': {'job_store_type': 'jdbc', 'table_prefix': 'QRTZ_',
                        'table_names': quartz_tables, 'mysql_lower_case_table_names': 0,
                        'scheduler_auto_startup': False, 'schema_initialization': 'never'}}
                private_file(output / 'review-mysql.json', json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
                print(json.dumps(summary, ensure_ascii=False))
                return summary
            finally:
                context.process.terminate()
                try:
                    context.process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    context.process.kill()
                    context.process.wait(timeout=5)
    finally:
        sys.path.remove(dev)
