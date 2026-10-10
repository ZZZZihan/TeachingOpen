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
PROBES = (
    'verify-public-boundaries.py',
    'verify-news-content.py',
    'verify-account-authorization.py',
    'verify-additional-work-authorization.py',
    'verify-work-stars.py',
    'verify-work-cloning.py',
    'verify-pagination.py',
)
COURSE_REQUEST = ROOT / ('api/jeecg-boot-module-system/src/main/java/'
                         'org/jeecg/modules/teaching/model/CourseMapUpdateRequest.java')


def private_file(path, content):
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w') as out:
        out.write(content)


def selected_probes():
    names = list(PROBES)
    if COURSE_REQUEST.is_file():
        names.append('verify-course-update.py')
    return [ROOT / 'api/dev' / name for name in names if (ROOT / 'api/dev' / name).is_file()]


def validate_report(report, jar_sha256):
    cases = report.get('cases', report.get('checks'))
    if (not isinstance(cases, list) or not cases
            or any(case.get('passed') is not True for case in cases)
            or report.get('exception') or report.get('failed', 0) != 0 or report.get('expected_legacy')
            or report.get('jar_sha256') != jar_sha256):
        raise RuntimeError('Review probe did not produce complete passing candidate evidence')
    passed = report.get('passed')
    if passed is not True and (type(passed) is not int or passed != len(cases)):
        raise RuntimeError('Review probe passing count does not match its executed checks')
    if 'total' in report and report['total'] != len(cases):
        raise RuntimeError('Review probe total does not match its executed checks')
    return len(cases)


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

    def assert_candidate(self, runtime, jar):
        self.guard(runtime, jar or self.jar)
        if (self.process is None or self.process.poll() is not None
                or self.properties is None or self.config.read_text() != self.properties
                or self.config.stat().st_mode & 0o077
                or hashlib.sha256(self.jar.read_bytes()).hexdigest() != self.jar_sha256):
            raise RuntimeError('CI fixture application is not the configured candidate process')
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
    context.sql(schema)
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
        context.properties = render_properties((ROOT / 'deploy/application-launch.properties.template').read_text(), values)
        private_file(context.config, context.properties)
        output = ROOT / 'ci-results'
        output.mkdir(exist_ok=True)
        with (runtime / 'logs/application.log').open('wb') as log:
            context.process = subprocess.Popen([str(java_home / 'bin/java'), '-Xms256m', '-Xmx1024m',
                '-jar', str(context.jar), '--spring.config.location=file:' + str(context.config)],
                cwd=runtime / 'webapp', stdout=log, stderr=log)
            try:
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
                probes = selected_probes()
                if not probes:
                    raise RuntimeError('No review probes are available in this candidate')
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
                    'unavailable_probes': [name for name in PROBES if not (ROOT / 'api/dev' / name).is_file()],
                    'course_update_enabled': COURSE_REQUEST.is_file()}
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
