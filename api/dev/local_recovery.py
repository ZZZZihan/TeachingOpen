"""Cold-application backup and fresh restore for local synthetic TeachingOpen data.

Not a production, online, cross-version or untrusted-SQL restore tool.
"""
import contextlib
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import select
import shutil
import socket
import stat
import subprocess
import time
from uuid import uuid4

from local_runtime import assert_app_config, assert_database, assert_mysql_owner, load_ports, mysql_command, validate_ports


SCHEMA_VERSION = 1


def private_write(path, data):
    if isinstance(data, str):
        data = data.encode()
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb') as out:
        out.write(data)


def local_path(path, new=False):
    path = Path(path).absolute()
    if path.is_symlink() or path.parent.name != '.devspace' or path.parent.resolve() != path.parent:
        raise ValueError('Use a non-symlink direct child of the local .devspace directory')
    if new and path.exists():
        raise ValueError('Destination already exists; existing data is never overwritten')
    if not new and (not path.is_dir() or path.stat().st_mode & 0o077):
        raise ValueError('Expected a private existing directory (mode 700)')
    return path


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def file_inventory(root):
    """Reject links and special files before any copy, including directory links."""
    if root.is_symlink() or not root.is_dir():
        raise ValueError('Expected an ordinary directory')
    result = {}
    for directory, dirs, files in os.walk(root, followlinks=False):
        for name in dirs + files:
            item = Path(directory) / name
            mode = item.lstat().st_mode
            if stat.S_ISLNK(mode) or not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
                raise ValueError('Links and special files are not supported')
            if stat.S_ISREG(mode):
                result[str(item.relative_to(root))] = {'sha256': sha256(item), 'bytes': item.stat().st_size}
    return dict(sorted(result.items()))


def command(runtime, args, **kwargs):
    result = subprocess.run(args, capture_output=True, timeout=120, **kwargs)
    if result.returncode:
        log = runtime / 'logs' / ('recovery-error-' + uuid4().hex[:12] + '.log')
        data = result.stderr.encode() if isinstance(result.stderr, str) else result.stderr
        private_write(log, data or b'Command failed without stderr\n')
        raise RuntimeError('Recovery command failed; private diagnostic: ' + str(log))
    return result.stdout


def sql(runtime, query):
    return command(runtime, mysql_command(runtime) + ['--raw', '-e', query], text=True).rstrip('\n')


def quote(name):
    return '`' + name.replace('`', '``') + '`'


def database_inventory(runtime):
    # This tool backs up the actual synthetic base-table schema. Fail explicitly
    # if custom objects need a definer/event policy instead of silently omitting them.
    unsupported = sql(runtime, "SELECT (SELECT COUNT(*) FROM information_schema.views WHERE TABLE_SCHEMA='teachingopen_dev') + (SELECT COUNT(*) FROM information_schema.triggers WHERE TRIGGER_SCHEMA='teachingopen_dev') + (SELECT COUNT(*) FROM information_schema.routines WHERE ROUTINE_SCHEMA='teachingopen_dev') + (SELECT COUNT(*) FROM information_schema.events WHERE EVENT_SCHEMA='teachingopen_dev')")
    if unsupported != '0':
        raise ValueError('Custom views/triggers/routines/events need a separate restore policy')
    tables = sql(runtime, "SELECT TABLE_NAME FROM information_schema.tables WHERE TABLE_SCHEMA='teachingopen_dev' ORDER BY TABLE_NAME").splitlines()
    result = {}
    for name in tables:
        table = 'teachingopen_dev.' + quote(name)
        columns = sql(runtime, "SHOW COLUMNS FROM " + table).splitlines()
        names = [line.split('\t')[0] for line in columns]
        expression = ','.join("IFNULL(HEX(CAST(" + quote(n) + " AS BINARY)),'~')" for n in names)
        # Prefix every row so even one all-empty row survives line splitting.
        rows = sql(runtime, "SELECT 'ROW'," + expression + ' FROM ' + table).splitlines()
        definition = sql(runtime, 'SHOW CREATE TABLE ' + table)
        result[name] = {'rows': len(rows), 'rows_sha256': hashlib.sha256(('\n'.join(sorted(rows)) + ('\n' if rows else '')).encode()).hexdigest(), 'schema_sha256': hashlib.sha256(definition.encode()).hexdigest()}
    return result


def assert_stopped(runtime):
    """Require a closed application listener and no live recorded application PID."""
    assert_app_config(runtime)
    assert_database(runtime)
    with socket.socket() as probe:
        probe.settimeout(0.5)
        if probe.connect_ex(('127.0.0.1', load_ports(runtime)['backend'])) == 0:
            raise RuntimeError('Stop the task backend before taking a database/attachment snapshot')
    pid_file = runtime / 'backend.pid'
    if pid_file.exists():
        pid = int(pid_file.read_text().strip())
        status = subprocess.run(['ps', '-p', str(pid), '-o', 'stat='], capture_output=True, text=True)
        if status.returncode == 0 and status.stdout.strip() and not status.stdout.strip().startswith('Z'):
            raise RuntimeError('Recorded backend PID is still live; wait for clean shutdown')


@contextlib.contextmanager
def database_read_lock(runtime):
    """Keep a MySQL global read lock until database and attachment capture finish."""
    process = subprocess.Popen(mysql_command(runtime) + ['--unbuffered'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        process.stdin.write("FLUSH TABLES WITH READ LOCK; SELECT 'RECOVERY_LOCK_READY';\n")
        process.stdin.flush()
        ready, _, _ = select.select([process.stdout], [], [], 15)
        if not ready or process.stdout.readline().strip() != 'RECOVERY_LOCK_READY':
            raise RuntimeError('Could not establish the local snapshot read lock')
        yield
    finally:
        if process.poll() is None:
            try:
                process.stdin.write('UNLOCK TABLES;\nquit\n'); process.stdin.flush()
                process.communicate(timeout=5)
            except (BrokenPipeError, subprocess.TimeoutExpired):
                process.terminate(); process.communicate(timeout=5)
        else:
            process.communicate()


def create_snapshot(runtime, destination):
    runtime, destination = local_path(runtime), local_path(destination, new=True)
    assert_stopped(runtime)
    file_inventory(runtime / 'uploads')
    destination.mkdir(mode=0o700)
    with database_read_lock(runtime):
        before = database_inventory(runtime)
        files = file_inventory(runtime / 'uploads')
        dump = runtime / 'tools/mysql-8.4.6-macos15-arm64/bin/mysqldump'
        args = [str(dump), '--defaults-extra-file=' + str(runtime / 'config/mysql-admin-client.cnf'), '--single-transaction', '--skip-lock-tables', '--set-gtid-purged=OFF', '--no-tablespaces', '--hex-blob', '--default-character-set=utf8mb4', '--skip-comments', 'teachingopen_dev']
        private_write(destination / 'database.sql', command(runtime, args))
        shutil.copytree(runtime / 'uploads', destination / 'uploads')
        fixture_password = json.loads((runtime / 'config/credentials.json').read_text())['test_user_password']
        private_write(destination / 'fixture-login.json', json.dumps({'test_user_password': fixture_password}) + '\n')
        if database_inventory(runtime) != before or file_inventory(runtime / 'uploads') != files or file_inventory(destination / 'uploads') != files:
            raise RuntimeError('Source changed during snapshot; incomplete directory retained, no valid manifest')
        assert_stopped(runtime)
    payload = file_inventory(destination)
    manifest = {'format': SCHEMA_VERSION, 'kind': 'teachingopen-local-synthetic', 'database': before, 'uploads': files, 'payload': payload, 'source_ports': load_ports(runtime), 'created_unix': int(time.time()), 'redis': 'excluded; fresh login required', 'complete': True}
    private_write(destination / 'manifest.json', json.dumps(manifest, indent=2) + '\n')
    return {'tables': len(before), 'rows': sum(x['rows'] for x in before.values()), 'files': len(files), 'snapshot': str(destination), 'manifest_sha256': sha256(destination / 'manifest.json')}


def inspect_snapshot(snapshot):
    snapshot = local_path(snapshot)
    inventory = file_inventory(snapshot)
    if 'manifest.json' not in inventory:
        raise ValueError('Snapshot is incomplete: manifest missing')
    manifest = json.loads((snapshot / 'manifest.json').read_text())
    if manifest.get('format') != SCHEMA_VERSION or manifest.get('kind') != 'teachingopen-local-synthetic' or manifest.get('complete') is not True:
        raise ValueError('Unsupported or incomplete snapshot manifest')
    inventory.pop('manifest.json')
    if inventory != manifest.get('payload'):
        raise ValueError('Snapshot bytes differ from its manifest')
    if not {'database.sql', 'fixture-login.json'} <= set(inventory) or any(n not in {'database.sql', 'fixture-login.json'} and not n.startswith('uploads/') for n in inventory):
        raise ValueError('Unexpected snapshot payload layout')
    if file_inventory(snapshot / 'uploads') != manifest.get('uploads'):
        raise ValueError('Attachment manifest mismatch')
    validate_ports(manifest.get('source_ports', {}))
    database = manifest.get('database')
    if not isinstance(database, dict) or not database:
        raise ValueError('Missing database inventory')
    for name, record in database.items():
        if (not isinstance(name, str) or not isinstance(record, dict)
                or type(record.get('rows')) is not int or record['rows'] < 0
                or any(not isinstance(record.get(key), str) or not re.fullmatch('[0-9a-f]{64}', record[key])
                       for key in ('rows_sha256', 'schema_sha256'))):
            raise ValueError('Invalid database inventory')
    password = json.loads((snapshot / 'fixture-login.json').read_text())
    if (not isinstance(password, dict) or set(password) != {'test_user_password'}
            or not isinstance(password['test_user_password'], str)
            or not re.fullmatch('[0-9a-f]{40}', password['test_user_password'])):
        raise ValueError('Invalid synthetic fixture login metadata')
    return manifest


def restore_snapshot(snapshot, runtime, tools, ports):
    snapshot, runtime = local_path(snapshot), local_path(runtime, new=True)
    manifest = inspect_snapshot(snapshot)
    validate_ports(ports)
    if set(ports.values()) & set(manifest['source_ports'].values()):
        raise ValueError('Restore must use ports distinct from the source runtime')
    spec = importlib.util.spec_from_file_location('prepare_local_recovery', Path(__file__).with_name('prepare-local.py'))
    prepare = importlib.util.module_from_spec(spec); spec.loader.exec_module(prepare)
    prepare.prepare(runtime, Path(tools).resolve(), ports, seed_fixtures=False)
    # prepare created an empty schema and no app process. No existing target is accepted.
    assert_app_config(runtime)
    assert_database(runtime, empty=True)
    assert_mysql_owner(runtime)
    credentials = json.loads((runtime / 'config/credentials.json').read_text())
    app_client = runtime / 'config/recovery-app-client.cnf'
    private_write(app_client, '[client]\nuser=teaching_dev\nhost=127.0.0.1\nprotocol=tcp\nport=' + str(ports['mysql']) + '\npassword=' + credentials['mysql_app_password'] + '\n')
    client = [str(runtime / 'tools/mysql-8.4.6-macos15-arm64/bin/mysql'), '--defaults-extra-file=' + str(app_client), '--local-infile=0', '--binary-mode', '--default-character-set=utf8mb4']
    # Use the newly created database-scoped account, not server root, for SQL import.
    payload = b'DROP DATABASE teachingopen_dev; CREATE DATABASE teachingopen_dev CHARACTER SET utf8mb4; USE teachingopen_dev;\n' + (snapshot / 'database.sql').read_bytes()
    command(runtime, client, input=payload)
    shutil.rmtree(runtime / 'uploads')
    shutil.copytree(snapshot / 'uploads', runtime / 'uploads')
    # Preserve source fixture account passwords; rotate target infrastructure credentials.
    credentials['test_user_password'] = json.loads((snapshot / 'fixture-login.json').read_text())['test_user_password']
    (runtime / 'config/credentials.json').write_text(json.dumps(credentials, indent=2) + '\n')
    assert_database(runtime)
    actual = database_inventory(runtime)
    files = file_inventory(runtime / 'uploads')
    if inspect_snapshot(snapshot) != manifest or actual != manifest['database'] or files != manifest['uploads']:
        raise RuntimeError('Restored data differs from snapshot; target retained for diagnosis, do not start app')
    result = {'snapshot_manifest_sha256': sha256(snapshot / 'manifest.json'), 'database_equal': True, 'attachments_equal': True, 'tables': len(actual), 'rows': sum(x['rows'] for x in actual.values()), 'files': len(files), 'runtime': str(runtime), 'ports': ports, 'redis_sessions_restored': False, 'business_read_verified': False}
    private_write(runtime / 'restore-result.json', json.dumps(result, indent=2) + '\n')
    return result
