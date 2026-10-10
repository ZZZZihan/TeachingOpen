#!/usr/bin/env python3
"""Freeze and verify a private Linux/arm64 synthetic candidate; never run Docker."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import stat
import subprocess
import sys
import tempfile

FORMAT = 2
NGINX_SHA256 = '93b019f547c36b708d46ac175368aee69a234495e6456b3e48e75d681e799a40'
TEMPLATE_SHA256 = '8854226931f4aea3fd076f90ff0c0e73b932fff2ef885a0fb4d19f6034b8ce64'
PLATFORM = 'linux/arm64'
IMAGES = {
    'api': 'eclipse-temurin@sha256:d05fc020fcaae47f67ac951f7d6f3430278b78216c121a1162fdad14826bab95',
    'db': 'mysql@sha256:6752fee1ed70df146fe22d5d1656deee79463f780a24cb7e67c807f2f07d7dc5',
    'redis': 'redis@sha256:6aa2a40135cd61fe5f3359b5d8644151a25de7f7ddd806dfd6d48f8ad9d748c5',
    'web': 'nginx@sha256:0985e772fb9f729e6fa0980da05fca5d9c468e870eed43071545afa9d2e27d94',
}
MUTABLE_DIRECTORIES = ['data/mysql', 'data/redis', 'data/uploads', 'data/webapp', 'data/logs']
HELPERS = [
    'api/dev/extract-schema.py', 'api/dev/role_flow_fixture.py',
    'api/dev/local_recovery.py', 'api/dev/local_runtime.py',
    'api/dev/production_fixture.py', 'api/dev/scratch_cloud_recovery.py',
    'api/dev/FixturePassword.java', 'api/dev/application-localtest.properties.template',
    'api/db/teachingopen2.8.sql',
    'api/jeecg-boot-base-common/src/main/java/org/jeecg/common/util/PasswordUtil.java',
    'api/dev/role-flow-assets/lesson.mp4', 'api/dev/role-flow-assets/starter.sb3',
    'api/dev/role-flow-assets/starter.sjr', 'web/nginx/default.conf',
    'api/db/phone-profile-registration.sql', 'api/db/enable-phone-registration.sql',
    'deploy/registration_upgrade.py',
]


def registration_tool(source=None):
    path = (source / 'deploy/registration_upgrade.py') if source is not None else Path(__file__).with_name('registration_upgrade.py')
    spec = importlib.util.spec_from_file_location('_candidate_registration_upgrade', path)
    module = importlib.util.module_from_spec(spec)
    old = sys.dont_write_bytecode
    try:
        sys.dont_write_bytecode = True
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = old
    return module


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def checked_path(path, kind='file', missing=False):
    """Reject symlinks in every component, including otherwise harmless parents."""
    path = Path(os.path.abspath(path))
    for component in [*reversed(path.parents), path]:
        try:
            mode = component.lstat().st_mode
        except FileNotFoundError:
            if missing and component == path:
                return path
            raise ValueError('Missing path: ' + str(component)) from None
        if stat.S_ISLNK(mode):
            raise ValueError('Symlink path is forbidden: ' + str(component))
        expected_directory = component != path or kind == 'directory'
        if not (stat.S_ISDIR(mode) if expected_directory else stat.S_ISREG(mode)):
            raise ValueError('Expected ordinary ' + ('directory: ' if expected_directory else 'file: ') + str(component))
    if missing:
        raise ValueError('Output already exists: ' + str(path))
    return path


def relative_path(value):
    if not isinstance(value, str) or not value or '\\' in value or '\x00' in value:
        raise ValueError('Invalid relative path')
    parsed = PurePosixPath(value)
    if parsed.is_absolute() or any(p in ('', '.', '..') for p in value.split('/')):
        raise ValueError('Path traversal is forbidden')
    return value


def file_inventory(directory):
    directory = checked_path(directory, 'directory')
    result = {}
    for parent, dirs, files in os.walk(directory, followlinks=False):
        for name in dirs:
            checked_path(Path(parent) / name, 'directory')
        for name in files:
            path = checked_path(Path(parent) / name)
            result[path.relative_to(directory).as_posix()] = {'bytes': path.stat().st_size, 'sha256': sha256(path)}
    return dict(sorted(result.items()))


def checked_inventory(value):
    if not isinstance(value, dict) or not value:
        raise ValueError('Expected nonempty path-to-file manifest')
    for name, receipt in value.items():
        relative_path(name)
        if not isinstance(receipt, dict) or set(receipt) != {'bytes', 'sha256'}:
            raise ValueError('Invalid file receipt')
        if type(receipt['bytes']) is not int or receipt['bytes'] < 0:
            raise ValueError('Invalid file byte count')
        check_digest(receipt['sha256'])
    return value


def read_json(path):
    def unique(pairs):
        result = {}
        for name, value in pairs:
            if name in result:
                raise ValueError('Duplicate JSON object key')
            result[name] = value
        return result
    return json.loads(Path(path).read_text(encoding='utf-8'), object_pairs_hook=unique)


def check_digest(value):
    if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{64}', value):
        raise ValueError('Expected lowercase SHA256')


def git_commit(source):
    def git(*args):
        completed = subprocess.run(['git', '-C', str(source), *args], capture_output=True, text=True)
        if completed.returncode:
            raise ValueError('Source must be a readable Git checkout')
        return completed.stdout.strip()
    if Path(git('rev-parse', '--show-toplevel')).resolve() != source:
        raise ValueError('Source must be the Git checkout root')
    if git('status', '--porcelain', '--untracked-files=no'):
        raise ValueError('Source has tracked changes; freeze a clean candidate first')
    return git('rev-parse', 'HEAD')


def load_source_helpers(source):
    """Import trusted, explicitly selected source. This is not a Python sandbox."""
    names = ['local_runtime', 'scratch_cloud_recovery', 'local_recovery', 'production_fixture', 'role_flow_fixture']
    old_modules = {name: sys.modules.get(name) for name in names}
    old_path = list(sys.path)
    old_bytecode = sys.dont_write_bytecode
    try:
        sys.dont_write_bytecode = True
        for name in names:
            sys.modules.pop(name, None)
        sys.path.insert(0, str(source / 'api/dev'))
        def load(name, path):
            spec = importlib.util.spec_from_file_location(name, path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            spec.loader.exec_module(module)
            return module
        extractor = load('_candidate_extract', source / 'api/dev/extract-schema.py')
        fixture = load('role_flow_fixture', source / 'api/dev/role_flow_fixture.py')
        return extractor, fixture
    finally:
        sys.dont_write_bytecode = old_bytecode
        sys.path[:] = old_path
        for name, previous in old_modules.items():
            if previous is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous
        sys.modules.pop('_candidate_extract', None)


def password_hashes(source, java_home, credentials, accounts):
    if java_home is None:
        raise ValueError('create requires --java-home pointing to JDK 8')
    home = checked_path(java_home, 'directory')
    java, javac = checked_path(home / 'bin/java'), checked_path(home / 'bin/javac')
    version = subprocess.run([str(java), '-version'], capture_output=True, text=True)
    if version.returncode or not re.search(r'version "1\.8\.', version.stdout + version.stderr):
        raise ValueError('Expected JDK 8')
    with tempfile.TemporaryDirectory(prefix='teaching-candidate-password-') as temporary:
        classes = Path(temporary)
        result = subprocess.run([str(javac), '-d', str(classes),
            str(source / 'api/dev/FixturePassword.java'),
            str(source / HELPERS[9])], capture_output=True)
        if result.returncode:
            raise ValueError('FixturePassword compilation failed')
        hashes = {}
        for username in accounts:
            salt = secrets.token_hex(4)
            result = subprocess.run([str(java), '-cp', str(classes), 'FixturePassword'],
                input=username + '\n' + credentials['test_user_password'] + '\n' + salt + '\n',
                capture_output=True, text=True)
            length = ((len(username.encode('utf-8')) // 8) + 1) * 16
            if result.returncode or not re.fullmatch('[0-9a-f]{' + str(length) + '}', result.stdout):
                raise ValueError('FixturePassword did not produce the expected hash')
            hashes[username] = {'password': result.stdout, 'salt': salt}
        return hashes


def write_file(root, name, data, mode=0o600):
    path = root / relative_path(name)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with path.open('xb') as out:
        out.write(data.encode('utf-8') if isinstance(data, str) else data)
    path.chmod(mode)


def json_bytes(value):
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + '\n'


def application_config(template, credentials, port):
    values = {'BACKEND_PORT': '8080', 'MYSQL_PORT': '3306', 'REDIS_PORT': '6379',
        'FRONTEND_PORT': str(port), 'RUNTIME': '/app',
        'MYSQL_APP_PASSWORD': credentials['mysql_app_password'], 'REDIS_PASSWORD': credentials['redis_password']}
    for key, value in values.items():
        template = template.replace('@' + key + '@', value)
    if re.search(r'@[A-Z_]+@', template):
        raise ValueError('Unknown configuration template placeholder')
    overrides = {'server.address': '0.0.0.0', 'spring.redis.host': 'redis',
        'jeecg.media.cookie-name': 'teaching_media_' + str(port)}
    lines = []
    for line in template.splitlines():
        key, separator, value = line.partition('=')
        if key == 'spring.datasource.dynamic.datasource.master.url':
            value = value.replace('127.0.0.1:3306/', 'db:3306/')
        if key in overrides:
            value = overrides[key]
        lines.append(key + separator + value)
    return '\n'.join(lines) + '\n'


def compose_config(project, port):
    def bind(source, target, readonly=True):
        return {'type': 'bind', 'source': './' + source, 'target': target, 'read_only': readonly,
                'bind': {'create_host_path': False}}
    shared = {'platform': PLATFORM, 'networks': ['candidate'], 'restart': 'no'}
    services = {
        'db': {**shared, 'image': IMAGES['db'], 'mem_limit': '1g',
            'environment': {'MYSQL_DATABASE': 'teachingopen_dev', 'MYSQL_USER': 'teaching_dev',
                'MYSQL_ROOT_PASSWORD_FILE': '/run/secrets/mysql-root-password',
                'MYSQL_PASSWORD_FILE': '/run/secrets/mysql-app-password'},
            'command': ['--character-set-server=utf8mb4', '--collation-server=utf8mb4_unicode_ci', '--mysqlx=0'],
            'volumes': [bind('data/mysql', '/var/lib/mysql', False), bind('init', '/docker-entrypoint-initdb.d'),
                bind('config/mysql-root-password', '/run/secrets/mysql-root-password'),
                bind('config/mysql-app-password', '/run/secrets/mysql-app-password'),
                bind('config/mysql-client.cnf', '/run/secrets/mysql-client.cnf')],
            'healthcheck': {'test': ['CMD', 'mysqladmin', '--defaults-extra-file=/run/secrets/mysql-client.cnf', 'ping', '--silent'],
                'interval': '5s', 'timeout': '3s', 'retries': 40, 'start_period': '20s'}},
        'redis': {**shared, 'image': IMAGES['redis'], 'mem_limit': '256m', 'command': ['redis-server', '/etc/redis/candidate.conf'],
            'volumes': [bind('data/redis', '/data', False), bind('config/redis.conf', '/etc/redis/candidate.conf')]},
        'api': {**shared, 'image': IMAGES['api'], 'working_dir': '/app', 'mem_limit': '1536m',
            'entrypoint': ['java'], 'command': ['-Xms256m', '-Xmx1g', '-jar', '/app/app.jar', '--spring.profiles.active=dev,localtest',
                '--spring.config.additional-location=file:/app/config/application-localtest.properties'],
            'depends_on': {'db': {'condition': 'service_healthy'}, 'redis': {'condition': 'service_started'}},
            'volumes': [bind('app/app.jar', '/app/app.jar'),
                bind('config/application-localtest.properties', '/app/config/application-localtest.properties'),
                bind('data/uploads', '/app/uploads', False), bind('data/webapp', '/app/webapp', False),
                bind('data/logs', '/logs', False)]},
        'web': {**shared, 'networks': ['candidate', 'ingress'], 'image': IMAGES['web'], 'mem_limit': '128m', 'entrypoint': ['nginx'], 'command': ['-g', 'daemon off;'],
            'depends_on': ['api'], 'ports': [{'target': 80, 'published': str(port), 'host_ip': '127.0.0.1', 'protocol': 'tcp'}],
            'volumes': [bind('web/dist', '/usr/share/nginx/html'), bind('web/nginx.conf', '/etc/nginx/conf.d/default.conf')]},
    }
    return {'name': project, 'services': services,
        'networks': {'candidate': {'internal': True}, 'ingress': {'driver': 'bridge', 'internal': False}}}


def immutable_inventory(bundle):
    """Do not walk, stat, or read runtime data underneath the fixed data boundary."""
    result = {}
    for child in bundle.iterdir():
        if child.name == 'data':
            checked_path(child, 'directory')
            continue
        if child.name == 'manifest.json':
            checked_path(child)
            continue
        if child.is_dir() and not child.is_symlink():
            for name, value in file_inventory(child).items():
                result[child.name + '/' + name] = value
        else:
            path = checked_path(child)
            result[path.name] = {'bytes': path.stat().st_size, 'sha256': sha256(path)}
    return dict(sorted(result.items()))


def expected_mode(name):
    if name.startswith('web/dist/') or name == 'web/nginx.conf':
        return 0o644
    if name.startswith('init/') or name in ('config/mysql-root-password', 'config/mysql-app-password', 'config/redis.conf'):
        return 0o444
    return 0o600


def verify_bundle(bundle):
    bundle = checked_path(bundle, 'directory')
    if stat.S_IMODE(bundle.stat().st_mode) != 0o700:
        raise ValueError('Bundle directory must have mode 0700')
    manifest_path = checked_path(bundle / 'manifest.json')
    if stat.S_IMODE(manifest_path.stat().st_mode) != 0o600:
        raise ValueError('Manifest must have mode 0600')
    manifest = read_json(manifest_path)
    fields = {'format', 'kind', 'source_commit', 'generator_sha256', 'helper_sha256', 'artifact_inputs',
        'files', 'mutable_directories', 'fixture_counts', 'fixtures', 'images', 'platform', 'port', 'compose_project', 'database_upgrade'}
    if not isinstance(manifest, dict) or set(manifest) != fields:
        raise ValueError('Missing or unknown manifest field')
    if type(manifest.get('format')) is not int or manifest['format'] != FORMAT or manifest.get('kind') != 'teachingopen-linux-synthetic-candidate':
        raise ValueError('Unknown candidate manifest')
    if not isinstance(manifest['source_commit'], str) or not re.fullmatch('[0-9a-f]{40}|[0-9a-f]{64}', manifest['source_commit']):
        raise ValueError('Invalid source commit')
    check_digest(manifest['generator_sha256'])
    if not isinstance(manifest['helper_sha256'], dict) or set(manifest['helper_sha256']) != set(HELPERS):
        raise ValueError('Unknown or missing trusted-source helper receipt')
    for digest in manifest['helper_sha256'].values():
        check_digest(digest)
    if not isinstance(manifest['artifact_inputs'], dict) or set(manifest['artifact_inputs']) != {'jar_sha256', 'dist_manifest_sha256'}:
        raise ValueError('Invalid artifact input receipt')
    for digest in manifest['artifact_inputs'].values():
        check_digest(digest)
    if manifest['fixture_counts'] != {'accounts': 5, 'classes': 2, 'courses': 3, 'tables': 70}:
        raise ValueError('Unexpected synthetic fixture counts')
    fixtures = manifest['fixtures']
    if not isinstance(fixtures, dict) or set(fixtures) != {'database', 'public_media_key', 'private_media_key',
            'initial_upload_files', 'public_media_sha256', 'private_media_sha256', 'public_media_bytes', 'private_media_bytes'}:
        raise ValueError('Invalid media fixture receipt')
    if fixtures['database'] != 'teachingopen_dev' or fixtures['public_media_key'] != 'role-flow/cover.png' or fixtures['private_media_key'] != 'role-flow/lesson.mp4':
        raise ValueError('Unexpected synthetic media fixture')
    for name in ('public_media_sha256', 'private_media_sha256'):
        check_digest(fixtures[name])
    for name in ('initial_upload_files', 'public_media_bytes', 'private_media_bytes'):
        if type(fixtures[name]) is not int or fixtures[name] <= 0:
            raise ValueError('Invalid media fixture byte or file count')
    if manifest.get('mutable_directories') != MUTABLE_DIRECTORIES:
        raise ValueError('Unexpected runtime data boundary')
    data = checked_path(bundle / 'data', 'directory')
    if {child.name for child in data.iterdir()} != {PurePosixPath(name).name for name in MUTABLE_DIRECTORIES}:
        raise ValueError('Missing or unknown runtime data directory')
    for name in MUTABLE_DIRECTORIES:
        checked_path(bundle / name, 'directory')
    expected = checked_inventory(manifest.get('files'))
    required = {'app/app.jar', 'web/nginx.conf', 'config/credentials.json',
        'config/application-localtest.properties', 'config/mysql-root-password',
        'config/mysql-app-password', 'config/mysql-client.cnf', 'config/redis.conf',
        'init/01-schema.sql', 'init/02-fixtures.sql', 'init/03-phone-profile-registration.sql',
        'init/04-enable-phone-registration.sql', 'upgrade/01-phone-profile-registration.sql',
        'upgrade/02-enable-phone-registration.sql', 'upgrade/migration-manifest.json',
        'upgrade/registration_upgrade.py', 'compose.json'}
    if not required <= set(expected) or not any(n.startswith('web/dist/') for n in expected):
        raise ValueError('Missing required bundle input')
    if any(name not in required and not name.startswith('web/dist/') for name in expected):
        raise ValueError('Unexpected immutable input path')
    if any(name == 'manifest.json' or name == 'data' or name.startswith('data/') for name in expected):
        raise ValueError('Manifest cannot reinterpret runtime or self-hash boundaries')
    if immutable_inventory(bundle) != expected:
        raise ValueError('Immutable file missing, extra, or changed')
    upgrade = registration_tool()
    upgrade_manifest = upgrade.verify_migrations(bundle / 'upgrade')
    expected_upgrade = {'manifest_sha256': expected['upgrade/migration-manifest.json']['sha256'],
        'initialization_order': ['init/01-schema.sql', 'init/02-fixtures.sql',
            'init/03-phone-profile-registration.sql', 'init/04-enable-phone-registration.sql'],
        'existing_database_requires_explicit_backup_and_apply': True, 'automatic_apply': False, 'ddl_transactional': False}
    if manifest['database_upgrade'] != expected_upgrade:
        raise ValueError('Database upgrade manifest/order changed')
    for index, (source_name, name) in enumerate(upgrade.MIGRATIONS, 3):
        init_name = 'init/' + str(index).zfill(2) + '-' + name[3:]
        receipt = expected['upgrade/' + name]
        if (receipt != expected[init_name] or receipt['sha256'] != manifest['helper_sha256'][source_name]
                or receipt != {'bytes': upgrade_manifest['steps'][index - 3]['bytes'],
                    'sha256': upgrade_manifest['steps'][index - 3]['sha256']}):
            raise ValueError('Initialization/explicit migration SQL must match the frozen helper receipt')
    if expected['upgrade/registration_upgrade.py']['sha256'] != manifest['helper_sha256']['deploy/registration_upgrade.py']:
        raise ValueError('Upgrade runner differs from frozen helper receipt')
    for name in expected:
        if stat.S_IMODE((bundle / name).stat().st_mode) != expected_mode(name):
            raise ValueError('Unexpected file permissions: ' + name)
    expected_dirs = {p.as_posix() for name in expected for p in PurePosixPath(name).parents if p.as_posix() != '.'}
    for parent, dirs, _ in os.walk(bundle, followlinks=False):
        if Path(parent) == bundle:
            dirs[:] = [d for d in dirs if d != 'data']
        for name in dirs:
            path = checked_path(Path(parent) / name, 'directory')
            rel = path.relative_to(bundle).as_posix()
            if rel not in expected_dirs:
                raise ValueError('Unexpected immutable directory: ' + rel)
            mode = 0o755 if rel in ('web', 'web/dist', 'init') or rel.startswith('web/dist/') else 0o700
            if stat.S_IMODE(path.stat().st_mode) != mode:
                raise ValueError('Unexpected directory permissions: ' + rel)
    if manifest.get('images') != IMAGES or manifest.get('platform') != PLATFORM:
        raise ValueError('Unexpected official image pins')
    port = manifest.get('port')
    project = manifest.get('compose_project')
    if type(port) is not int or not 1024 <= port <= 65535 or not isinstance(project, str) or not re.fullmatch('teaching-candidate-[0-9a-f]{12}', project):
        raise ValueError('Unexpected Compose identity or port')
    if read_json(bundle / 'compose.json') != compose_config(project, port):
        raise ValueError('Compose configuration differs from the bounded contract')
    if expected.get('web/nginx.conf', {}).get('sha256') != NGINX_SHA256:
        raise ValueError('Nginx must be the exact reviewed #66 configuration')
    if expected.get('app/app.jar', {}).get('sha256') != manifest.get('artifact_inputs', {}).get('jar_sha256'):
        raise ValueError('JAR differs from the declared frozen input')
    return {'status': 'verified_immutable', 'bundle': str(bundle), 'source_commit': manifest['source_commit'],
        'manifest_sha256': sha256(manifest_path),
        'immutable_files': len(expected), 'dist_files': sum(n.startswith('web/dist/') for n in expected),
        'platform': PLATFORM, 'port': port, 'compose_project': project,
        'runtime_data_checked': False, 'services_started': False}


def create_bundle(source, jar, jar_sha256, dist_manifest, dist_manifest_sha256, output, port=18190, java_home=None):
    if type(port) is not int or not 1024 <= port <= 65535:
        raise ValueError('Port must be 1024..65535')
    check_digest(jar_sha256)
    check_digest(dist_manifest_sha256)
    source = checked_path(source, 'directory')
    jar, dist_manifest = checked_path(jar), checked_path(dist_manifest)
    output = checked_path(output, 'directory', missing=True)
    # Do not create the bundle inside inputs which would alter their inventories.
    for input_path in (source, jar.parent, dist_manifest.parent):
        if output == input_path or input_path in output.parents:
            raise ValueError('Output must be outside the source and artifact input directories')
    commit = git_commit(source)
    tracked = subprocess.run(['git', '-C', str(source), 'ls-files', '--error-unmatch', '--', *HELPERS], capture_output=True, text=True)
    if tracked.returncode or set(tracked.stdout.splitlines()) != set(HELPERS):
        raise ValueError('Every trusted helper input must be tracked by the frozen source commit')
    helper_hashes = {name: sha256(checked_path(source / name)) for name in HELPERS}
    if helper_hashes['web/nginx/default.conf'] != NGINX_SHA256:
        raise ValueError('Source Nginx differs from reviewed #66')
    if helper_hashes['api/dev/application-localtest.properties.template'] != TEMPLATE_SHA256:
        raise ValueError('Source localtest template differs from reviewed contract')
    if sha256(jar) != jar_sha256 or sha256(dist_manifest) != dist_manifest_sha256:
        raise ValueError('Frozen artifact input SHA256 mismatch')
    dist = checked_path(source / 'web/dist', 'directory')
    dist_files = checked_inventory(read_json(dist_manifest))
    if file_inventory(dist) != dist_files:
        raise ValueError('Frontend dist missing, extra, or changed relative to frozen manifest')
    extractor, fixture = load_source_helpers(source)
    schema = extractor.extract_schema((source / 'api/db/teachingopen2.8.sql').read_text(encoding='utf-8'))
    if len(re.findall(r'^CREATE TABLE ', schema, re.MULTILINE)) != 69:
        raise ValueError('Expected the reviewed 69-table schema')
    old_bytecode = sys.dont_write_bytecode
    try:
        sys.dont_write_bytecode = True
        model = fixture.schema_model(source=schema)
    finally:
        sys.dont_write_bytecode = old_bytecode
    assets, base = fixture.generated_assets(), fixture.base_records()
    # Synthetic-only opt-in switch. Formal data is produced by the distinct
    # launch entry point and is never read/replaced by this fixture generator.
    base['sys_config'] = [{'id': 'fixture_allow_registration', 'config_key': 'allowReg',
        'config_value': '0', 'config_enabled': 1}]
    credentials = {name: secrets.token_hex(20) for name in
        ('mysql_root_password', 'mysql_app_password', 'redis_password', 'test_user_password')}
    hashed = password_hashes(source, java_home, credentials, fixture.ACCOUNT_ROLES)
    for row in base['sys_user']:
        row.update(hashed[row['username']])
    records = fixture.expected_after(model, base, fixture.ui_records(assets))
    counts = {'accounts': len(records['sys_user']), 'classes': sum(r['id'].startswith('fixture_class_') for r in records['sys_depart']),
        'courses': len(records['teaching_course']), 'tables': len(model) + 1}
    if counts != {'accounts': 5, 'classes': 2, 'courses': 3, 'tables': 70}:
        raise ValueError('Unexpected synthetic fixture contract')
    sql = ['SET NAMES utf8mb4;', "SET SESSION sql_mode='STRICT_TRANS_TABLES,NO_ENGINE_SUBSTITUTION';", 'START TRANSACTION;']
    for table, rows in records.items():
        for row in rows:
            sql.append('INSERT INTO ' + fixture.ident(table) + ' (' + ','.join(fixture.ident(n) for n in row) +
                ') VALUES (' + ','.join(fixture.sql_value(v) for v in row.values()) + ');')
    sql = '\n'.join(sql + ['COMMIT;', ''])
    output.mkdir(mode=0o700)
    try:
        # Failure preserves an incomplete private directory, never overwrites it.
        write_file(output, 'app/app.jar', jar.read_bytes())
        for name in dist_files:
            write_file(output, 'web/dist/' + name, checked_path(dist / name).read_bytes(), 0o644)
        write_file(output, 'web/nginx.conf', (source / 'web/nginx/default.conf').read_bytes(), 0o644)
        write_file(output, 'init/01-schema.sql', schema, 0o444)
        write_file(output, 'init/02-fixtures.sql', sql, 0o444)
        upgrade = registration_tool(source)
        for index, (source_name, name) in enumerate(upgrade.MIGRATIONS, 3):
            contents = (source / source_name).read_bytes()
            write_file(output, 'init/' + str(index).zfill(2) + '-' + name[3:], contents, 0o444)
            write_file(output, 'upgrade/' + name, contents)
        write_file(output, 'upgrade/migration-manifest.json', json_bytes(upgrade.migration_manifest(source)))
        write_file(output, 'upgrade/registration_upgrade.py', (source / 'deploy/registration_upgrade.py').read_bytes())
        write_file(output, 'config/credentials.json', json_bytes(credentials))
        write_file(output, 'config/mysql-root-password', credentials['mysql_root_password'] + '\n', 0o444)
        write_file(output, 'config/mysql-app-password', credentials['mysql_app_password'] + '\n', 0o444)
        write_file(output, 'config/mysql-client.cnf', '[client]\nuser=root\npassword=' + credentials['mysql_root_password'] +
            '\nhost=127.0.0.1\nprotocol=tcp\n[mysql]\nlocal-infile=0\n')
        write_file(output, 'config/redis.conf', 'bind 0.0.0.0\nport 6379\nprotected-mode yes\ndir /data\nappendonly yes\nrequirepass ' + credentials['redis_password'] + '\n', 0o444)
        write_file(output, 'config/application-localtest.properties', application_config(
            (source / 'api/dev/application-localtest.properties.template').read_text(encoding='utf-8'), credentials, port))
        for name in MUTABLE_DIRECTORIES:
            (output / name).mkdir(parents=True, mode=0o700)
        (output / 'data').chmod(0o700)
        for suffix in ('a', 'b'):
            write_file(output, 'data/uploads/fixture-work-' + suffix + '.txt', 'synthetic work ' + suffix + '\n')
        for name, data in assets.items():
            write_file(output, 'data/uploads/role-flow/' + relative_path(name), data)
        project = 'teaching-candidate-' + secrets.token_hex(6)
        write_file(output, 'compose.json', json_bytes(compose_config(project, port)))
        # Public application bytes are readable by the official Nginx worker;
        # private root/config still prevent access by other host users.
        for parent, dirs, _ in os.walk(output / 'web'):
            Path(parent).chmod(0o755)
        (output / 'init').chmod(0o755)
        files = immutable_inventory(output)
        if files['app/app.jar']['sha256'] != jar_sha256 or file_inventory(output / 'web/dist') != dist_files:
            raise ValueError('Copied artifacts changed during packaging')
        if git_commit(source) != commit or any(sha256(checked_path(source / name)) != digest for name, digest in helper_hashes.items()):
            raise ValueError('Trusted source changed during packaging')
        if sha256(jar) != jar_sha256 or sha256(dist_manifest) != dist_manifest_sha256 or file_inventory(dist) != dist_files:
            raise ValueError('Artifact inputs changed during packaging')
        manifest = {'format': FORMAT, 'kind': 'teachingopen-linux-synthetic-candidate', 'source_commit': commit,
            'generator_sha256': sha256(Path(__file__)), 'helper_sha256': helper_hashes,
            'artifact_inputs': {'jar_sha256': jar_sha256, 'dist_manifest_sha256': dist_manifest_sha256},
            'files': files, 'mutable_directories': MUTABLE_DIRECTORIES, 'fixture_counts': counts,
            'fixtures': {'database': 'teachingopen_dev', 'public_media_key': 'role-flow/cover.png',
                'private_media_key': 'role-flow/lesson.mp4', 'initial_upload_files': len(assets) + 2,
                'public_media_sha256': hashlib.sha256(assets['cover.png']).hexdigest(),
                'private_media_sha256': hashlib.sha256(assets['lesson.mp4']).hexdigest(),
                'public_media_bytes': len(assets['cover.png']), 'private_media_bytes': len(assets['lesson.mp4'])},
            'images': IMAGES, 'platform': PLATFORM, 'port': port, 'compose_project': project}
        manifest['database_upgrade'] = {'manifest_sha256': files['upgrade/migration-manifest.json']['sha256'],
            'initialization_order': ['init/01-schema.sql', 'init/02-fixtures.sql',
                'init/03-phone-profile-registration.sql', 'init/04-enable-phone-registration.sql'],
            'existing_database_requires_explicit_backup_and_apply': True, 'automatic_apply': False, 'ddl_transactional': False}
        write_file(output, 'manifest.json', json_bytes(manifest))
        result = verify_bundle(output)
        result['status'] = 'created_immutable'
        result['fixture_counts'] = counts
        return result
    except Exception:
        # An absent manifest means incomplete; never claim a partial bundle ready.
        if (output / 'manifest.json').exists():
            (output / 'manifest.json').unlink()
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='action', required=True)
    create = commands.add_parser('create', help='Create a new private frozen bundle without starting services')
    for flag in ('source', 'jar', 'dist-manifest', 'output', 'java-home'):
        create.add_argument('--' + flag, type=Path, required=True)
    for flag in ('jar-sha256', 'dist-manifest-sha256'):
        create.add_argument('--' + flag, required=True)
    create.add_argument('--port', type=int, default=18190)
    verify = commands.add_parser('verify', help='Verify immutable bytes without reading runtime data')
    verify.add_argument('--bundle', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        values = vars(args)
        action = values.pop('action')
        result = create_bundle(**values) if action == 'create' else verify_bundle(args.bundle)
    except (ValueError, OSError, KeyError) as error:
        parser.exit(1, 'candidate_release: ' + str(error) + '\n')
    print(json_bytes(result), end='')


if __name__ == '__main__':
    main()
