#!/usr/bin/env python3
"""Registration acceptance on disposable GitHub-hosted service containers only.

Creates a new fixed test DB, imports repository DDL (never original INSERTs),
applies the real migrations and runs the existing HTTP/SQL acceptance probe.
No production inputs, backup transfer, deployment or local scheduling.
"""
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
DATABASE = 'teachingopen_check_ci'


def require_hosted_runner():
    if os.environ.get('GITHUB_ACTIONS') != 'true' or os.environ.get('RUNNER_ENVIRONMENT') != 'github-hosted':
        raise RuntimeError('Only a disposable GitHub-hosted runner is supported')
    if Path(os.environ.get('GITHUB_WORKSPACE', '')).resolve() != ROOT:
        raise RuntimeError('Unexpected GitHub workspace')


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def render_properties(template, values):
    # Template comments describe @PLACEHOLDER@ syntax but are not configuration.
    active = '\n'.join(line for line in template.splitlines() if not line.lstrip().startswith('#'))
    return re.sub(r'@([A-Z_]+)@', lambda m: values[m.group(1)], active) + '\n'


def run(command, **kwargs):
    result = subprocess.run(command, capture_output=True, timeout=90, **kwargs)
    if result.returncode:
        raise RuntimeError(Path(command[0]).name + ' failed with exit ' + str(result.returncode))
    return result.stdout


def main():
    require_hosted_runner()
    os.umask(0o077)
    mysql, redis = shutil.which('mysql'), shutil.which('redis-cli')
    if not mysql or not redis:
        raise RuntimeError('MySQL and Redis test clients are required')
    root_password = os.environ['CI_MYSQL_ROOT_PASSWORD']
    if not re.fullmatch('[A-Za-z0-9-]+', root_password):
        raise ValueError('Unexpected synthetic MySQL password')
    jar = ROOT / 'api/jeecg-boot-module-system/target/teaching-open-2.8.0.jar'
    if not jar.is_file():
        raise RuntimeError('Build the candidate JAR before registration acceptance')
    with tempfile.TemporaryDirectory(prefix='teachingopen-ci-', dir=os.environ['RUNNER_TEMP']) as raw:
        runtime = Path(raw)
        root_options = runtime / 'root.cnf'
        root_options.write_text('[client]\nhost=127.0.0.1\nport=33306\nprotocol=tcp\nuser=root\npassword=' + root_password + '\n')
        root_options.chmod(0o600)
        command = [mysql, '--defaults-extra-file=' + str(root_options), '--default-character-set=utf8mb4', '-N']

        def sql(statement, database=True):
            return run(command + ([DATABASE] if database else []), input=statement.encode()).decode().strip()

        # No IF NOT EXISTS, reset, or reuse of an existing database.
        sql('CREATE DATABASE ' + DATABASE + ' CHARACTER SET utf8mb4', database=False)
        schema = load('schema', ROOT / 'api/dev/extract-schema.py').extract_schema(
            (ROOT / 'api/db/teachingopen2.8.sql').read_text())
        sql(schema)
        if sql('SELECT COUNT(*) FROM sys_user') != '0':
            raise RuntimeError('The CI schema must contain no original accounts')
        sql("INSERT INTO sys_role(id,role_name,role_code) VALUES ('ci-student','CI student','student');"
            "INSERT INTO sys_config(id,config_key,config_value,config_enabled) VALUES ('ci-reg','allowReg','0',1);")
        migrations = ['phone-profile-registration.sql', 'enable-phone-registration.sql']
        # Run twice to also exercise migration idempotency on the real engine.
        for _ in range(2):
            for name in migrations:
                sql((ROOT / 'api/db' / name).read_text())
        app_password = secrets.token_hex(24)
        redis_password = secrets.token_hex(24)
        sql("CREATE USER 'teaching_ci'@'%' IDENTIFIED BY '" + app_password + "';"
            "GRANT SELECT,INSERT,UPDATE,DELETE ON " + DATABASE + ".* TO 'teaching_ci'@'%';", database=False)
        run([redis, '-h', '127.0.0.1', '-p', '36379', 'CONFIG', 'SET', 'requirepass', redis_password])
        for directory in ('uploads', 'webapp', 'multipart'):
            (runtime / directory).mkdir(mode=0o700)
        values = {
            'API_BIND_ADDRESS': '127.0.0.1', 'API_PORT': '18259',
            'MYSQL_JDBC_URL': 'jdbc:mysql://127.0.0.1:33306/' + DATABASE + '?characterEncoding=UTF-8&useUnicode=true&useSSL=false&allowPublicKeyRetrieval=true&serverTimezone=Asia/Shanghai',
            'MYSQL_APP_USERNAME': 'teaching_ci', 'MYSQL_APP_PASSWORD': app_password,
            'REDIS_HOST': '127.0.0.1', 'REDIS_PORT': '36379', 'REDIS_DATABASE': '3',
            'REDIS_PASSWORD': redis_password, 'PUBLIC_ORIGIN': 'http://127.0.0.1:18259',
            'MULTIPART_DIRECTORY': str(runtime / 'multipart'), 'UPLOAD_DIRECTORY': str(runtime / 'uploads'),
            'WEBAPP_DIRECTORY': str(runtime / 'webapp'),
        }
        template = (ROOT / 'deploy/application-launch.properties.template').read_text()
        properties = render_properties(template, values)
        config = runtime / 'application.properties'
        config.write_text(properties)
        config.chmod(0o600)
        probe_config = runtime / 'probe.json'
        probe_config.write_text(json.dumps({'database': DATABASE, 'base_url': 'http://127.0.0.1:18259/api',
            'application_config': str(config), 'redis_database': 3, 'mysql': mysql,
            'mysql_options': str(root_options), 'redis_cli': redis}))
        probe_config.chmod(0o600)
        with (runtime / 'application.log').open('wb') as log:
            process = subprocess.Popen(['java', '-Xms256m', '-Xmx1024m', '-jar', str(jar),
                '--spring.config.location=file:' + str(config)], cwd=runtime / 'webapp', stdout=log, stderr=log)
            try:
                for attempt in range(120):
                    if process.poll() is not None:
                        raise RuntimeError('Isolated application exited before health check')
                    try:
                        with urllib.request.urlopen('http://127.0.0.1:18259/api/actuator/health', timeout=2) as response:
                            if json.load(response).get('status') == 'UP':
                                break
                    except (urllib.error.URLError, TimeoutError):
                        pass
                    time.sleep(1)
                else:
                    raise RuntimeError('Isolated application did not become healthy')
                result = load('probe', ROOT / 'deploy/verify_registration.py').main(probe_config)
                if result['passed'] != 32:
                    raise RuntimeError('Registration acceptance did not execute all 32 checks')
                result.update({'mysql_version': sql('SELECT VERSION()'), 'schema_tables': int(sql(
                    'SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=DATABASE()')),
                    'migrations_applied_twice': migrations, 'original_accounts_imported': 0,
                    'github_sha': os.environ.get('GITHUB_SHA'), 'production_connected': False})
                output = ROOT / 'ci-results'
                output.mkdir(exist_ok=True)
                (output / 'registration.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
                print(json.dumps(result, ensure_ascii=False))
            finally:
                process.terminate()
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)


if __name__ == '__main__':
    main()
