#!/usr/bin/env python3
"""Private online MySQL + uploads snapshots; restore only into a new restricted DB.

No production imports, service restarts, Redis/session restore, or schema changes.
The source database must use InnoDB. Avoid DDL during an online backup.
"""
import argparse
from datetime import datetime, timedelta, timezone
import fcntl
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import stat
import subprocess
import tempfile

KIND = 'teachingopen-online-backup-v1'
NAME = re.compile(r'^\d{8}T\d{6}Z-[0-9a-f]{8}$')


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def ordinary(path, directory=False, private=False):
    path = Path(os.path.abspath(path))
    for part in [*reversed(path.parents), path]:
        mode = part.lstat().st_mode
        expected = stat.S_ISDIR if directory or part != path else stat.S_ISREG
        if stat.S_ISLNK(mode) or not expected(mode):
            raise ValueError('Non-ordinary path')
    if private and path.stat().st_mode & 0o077:
        raise ValueError('Private path must not allow group/other access')
    return path


def write_json(path, value):
    temporary = path.with_name(path.name + '.new')
    with temporary.open('w') as out:
        json.dump(value, out, ensure_ascii=False, indent=2)
        out.write('\n')
        out.flush()
        os.fsync(out.fileno())
    os.replace(temporary, path)


def run(args, **kwargs):
    result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            timeout=1800, **kwargs)
    if result.returncode:
        # SQL/server diagnostics can contain account details. Never print them.
        raise RuntimeError(Path(args[0]).name + ' failed; exit=' + str(result.returncode))
    return result.stdout


def mysql(c, sql, database=None, option=None):
    args = [c['mysql'], '--defaults-extra-file=' + str(option or c['mysql_options']),
            '--default-character-set=utf8mb4', '--batch', '--skip-column-names',
            '--binary-mode', '--local-infile=0']
    if database:
        if not re.fullmatch('[A-Za-z0-9_]+', database):
            raise ValueError('Invalid database identifier')
        args.append(database)
    return run(args, input=sql.encode()).decode().strip()


def health(c, database):
    counts = {}
    for table in ('sys_user', 'sys_user_role', 'teaching_registration_profile',
                  'teaching_course', 'teaching_course_unit', 'sys_file'):
        counts[table] = int(mysql(c, 'SELECT COUNT(*) FROM `' + table + '`', database))
    checks = {
        'profiles_have_users': "SELECT COUNT(*) FROM teaching_registration_profile p LEFT JOIN sys_user u ON u.id=p.user_id WHERE u.id IS NULL",
        'profiles_have_roles': "SELECT COUNT(*) FROM teaching_registration_profile p LEFT JOIN sys_user_role r ON r.user_id=p.user_id WHERE r.id IS NULL",
        'valid_identity': "SELECT COUNT(*) FROM teaching_registration_profile WHERE BINARY identity NOT IN (BINARY 'student',BINARY 'teacher')",
        'profile_required_fields': "SELECT COUNT(*) FROM teaching_registration_profile p JOIN sys_user u ON u.id=p.user_id WHERE COALESCE(u.phone,'')='' OR COALESCE(u.realname,'')='' OR COALESCE(u.school,'')='' OR COALESCE(u.password,'')='' OR COALESCE(u.salt,'')=''",
    }
    for name, sql in checks.items():
        if mysql(c, sql, database) != '0':
            raise RuntimeError('Registration integrity failed: ' + name)
    if mysql(c, "SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='sys_user' AND column_name IN ('realname','school') AND character_set_name='utf8mb4'", database) != '2':
        raise RuntimeError('Registration character sets are incompatible')
    return {'counts': counts, 'checks': list(checks) + ['name_school_utf8mb4']}


def restore_check(c, snapshot):
    receipt = json.loads(ordinary(snapshot / 'receipt.json', private=True).read_text())
    if receipt['kind'] != KIND or digest(snapshot / 'database.sql.gz') != receipt['database_sha256']:
        raise ValueError('Invalid backup receipt or database checksum')
    # Separate restricted user: even an unexpected USE/DEFINER in SQL cannot
    # change the production database. The generated name never comes from SQL.
    suffix = secrets.token_hex(8)
    database, user = 'teachingopen_restore_' + suffix, 'to_verify_' + suffix
    password = secrets.token_hex(24)
    created_db = created_user = False
    try:
        mysql(c, 'CREATE DATABASE `' + database + '` CHARACTER SET utf8mb4')
        created_db = True
        mysql(c, "CREATE USER '" + user + "'@'localhost' IDENTIFIED BY '" + password + "'")
        created_user = True
        mysql(c, "GRANT ALL ON `" + database + "`.* TO '" + user + "'@'localhost'")
        with tempfile.TemporaryDirectory(prefix='to-restore-') as temp:
            options = Path(temp) / 'client.cnf'
            options.write_text('[client]\nuser=' + user + '\npassword=' + password +
                               '\nprotocol=socket\nsocket=' + c['mysql_socket'] + '\n')
            options.chmod(0o600)
            raw = Path(temp) / 'database.sql'
            with gzip.open(snapshot / 'database.sql.gz', 'rb') as source, raw.open('wb') as target:
                shutil.copyfileobj(source, target)
            with raw.open('rb') as stream:
                run([c['mysql'], '--defaults-extra-file=' + str(options),
                     '--default-character-set=utf8mb4', '--binary-mode', '--local-infile=0', database], stdin=stream)
            result = health(c, database)
            result.update({'checked_at': datetime.now(timezone.utc).isoformat(), 'status': 'passed',
                           'database_sha256': receipt['database_sha256'], 'restricted_restore_user': True})
        return result
    finally:
        # Only this invocation's successfully created, random namespace.
        try:
            if created_db:
                mysql(c, 'DROP DATABASE `' + database + '`')
        finally:
            if created_user:
                mysql(c, "DROP USER '" + user + "'@'localhost'")


def snapshots(root):
    found = []
    for p in root.iterdir():
        if NAME.fullmatch(p.name) and p.is_dir() and not p.is_symlink():
            receipt = p / 'receipt.json'
            if receipt.is_file() and not receipt.is_symlink():
                data = json.loads(receipt.read_text())
                if data.get('kind') == KIND and data.get('status') == 'complete':
                    found.append(p)
    return sorted(found)


def expired(items, now):
    keep, daily = set(), {}
    for p in items:
        when = datetime.strptime(p.name[:16], '%Y%m%dT%H%M%SZ').replace(tzinfo=timezone.utc)
        age = now - when
        if age <= timedelta(days=7):
            keep.add(p)
        if age <= timedelta(days=30):
            daily[when.date()] = p
    keep.update(daily.values())
    # Always keep the latest two completed backups, even after a long outage.
    keep.update(items[-2:])
    return [p for p in items if p not in keep]


def backup(c, root):
    source_db = c['database']
    if not re.fullmatch('[A-Za-z0-9_]+', source_db):
        raise ValueError('Invalid source database')
    if mysql(c, "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=DATABASE() AND table_type='BASE TABLE' AND engine<>'InnoDB'", source_db) != '0':
        raise RuntimeError('Online backup requires InnoDB tables')
    if shutil.disk_usage(root).free < c.get('minimum_free_bytes', 4 * 1024**3):
        raise RuntimeError('Insufficient backup disk headroom')
    previous = snapshots(root)
    snapshot_name = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ-') + secrets.token_hex(4)
    stage = root / ('.partial-' + snapshot_name)
    stage.mkdir(mode=0o700)
    dump = stage / 'database.sql'
    try:
        with dump.open('xb') as out:
            p = subprocess.run([c['mysqldump'], '--defaults-extra-file=' + c['mysql_options'],
                '--single-transaction', '--quick', '--skip-lock-tables', '--no-tablespaces',
                '--set-gtid-purged=OFF', '--routines', '--events', '--triggers', '--hex-blob',
                '--default-character-set=utf8mb4', source_db], stdout=out, stderr=subprocess.PIPE, timeout=1800)
        if p.returncode or dump.stat().st_size == 0:
            raise RuntimeError('Database export failed; partial backup is not complete')
        with dump.open('rb') as source, gzip.open(stage / 'database.sql.gz', 'wb', compresslevel=6) as out:
            shutil.copyfileobj(source, out)
        dump.unlink()
        uploads = ordinary(c['uploads'], directory=True)
        target = stage / 'uploads'
        target.mkdir(mode=0o700)
        for p in uploads.rglob('*'):
            if p.is_symlink() or not (p.is_file() or p.is_dir()):
                raise ValueError('Uploads contain non-ordinary paths')
        command = [c.get('rsync', '/usr/bin/rsync'), '-rlt', '--checksum', '--chmod=Du=rwx,Dgo=,Fu=rw,Fgo=']
        if previous:
            command += ['--link-dest=' + str(previous[-1] / 'uploads')]
        run(command + [str(uploads) + '/', str(target) + '/'])
        files = {str(p.relative_to(target)): {'bytes': p.stat().st_size, 'sha256': digest(p)}
                 for p in sorted(target.rglob('*')) if p.is_file()}
        write_json(stage / 'uploads.json', files)
        config_dir = stage / 'configuration'
        config_dir.mkdir(mode=0o700)
        for name, path in c.get('configuration_files', {}).items():
            if Path(name).name != name:
                raise ValueError('Invalid config filename')
            shutil.copyfile(ordinary(path), config_dir / name)
            (config_dir / name).chmod(0o600)
        receipt = {'kind': KIND, 'status': 'complete', 'created_at': datetime.now(timezone.utc).isoformat(),
                   'source_database': source_db, 'database_sha256': digest(stage / 'database.sql.gz'),
                   'database_bytes': (stage / 'database.sql.gz').stat().st_size,
                   'uploads_manifest_sha256': digest(stage / 'uploads.json'),
                   'upload_files': len(files), 'upload_bytes': sum(x['bytes'] for x in files.values()),
                   'configuration_sha256': {p.name: digest(p) for p in config_dir.iterdir()},
                   'application_sha256': digest(c['application']),
                   'redis_sessions_included': False, 'cross_store_atomic': False}
        write_json(stage / 'receipt.json', receipt)
        # Every completed snapshot has actually restored, not just decompressed.
        write_json(stage / 'restore-check.json', restore_check(c, stage))
        final = root / snapshot_name
        stage.rename(final)
        write_json(root / 'latest.json', {'snapshot': snapshot_name, **receipt})
        for item in expired(snapshots(root), datetime.now(timezone.utc)):
            shutil.rmtree(item)
        return {'status': 'complete', 'snapshot': snapshot_name, 'restore_check': 'passed',
                'database_bytes': receipt['database_bytes'], 'upload_files': len(files)}
    except Exception:
        # Leave evidence/partial files private, but never publish or prune.
        raise


def verify(c, root):
    items = snapshots(root)
    if not items:
        raise RuntimeError('No completed snapshot')
    target = items[-1]
    receipt = json.loads((target / 'receipt.json').read_text())
    if digest(target / 'uploads.json') != receipt['uploads_manifest_sha256']:
        raise ValueError('Upload manifest changed')
    files = json.loads((target / 'uploads.json').read_text())
    actual = {str(p.relative_to(target / 'uploads')) for p in (target / 'uploads').rglob('*') if p.is_file()}
    if actual != set(files):
        raise ValueError('Upload file set changed')
    for name, info in files.items():
        p = ordinary(target / 'uploads' / name)
        if p.stat().st_size != info['bytes'] or digest(p) != info['sha256']:
            raise ValueError('Upload checksum mismatch')
    for name, expected in receipt['configuration_sha256'].items():
        if digest(ordinary(target / 'configuration' / name, private=True)) != expected:
            raise ValueError('Configuration checksum mismatch')
    result = restore_check(c, target)
    write_json(target / 'restore-check.json', result)
    write_json(root / 'last-verification.json', {'snapshot': target.name, **result})
    return {'snapshot': target.name, **result}


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('backup', 'verify'))
    parser.add_argument('--config', required=True, type=Path)
    args = parser.parse_args()
    c = json.loads(ordinary(args.config, private=True).read_text())
    ordinary(c['mysql_options'], private=True)
    root = Path(c['destination'])
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    ordinary(root, directory=True, private=True)
    with (root / '.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = backup(c, root) if args.action == 'backup' else verify(c, root)
            write_json(root / ('last-' + args.action + '.json'), result)
            print(json.dumps(result, ensure_ascii=False))
        except Exception as error:
            result = {'status': 'failed', 'action': args.action,
                      'at': datetime.now(timezone.utc).isoformat(), 'error_type': type(error).__name__}
            write_json(root / ('last-' + args.action + '.json'), result)
            print(json.dumps(result))
            raise SystemExit(1)


if __name__ == '__main__':
    main()
