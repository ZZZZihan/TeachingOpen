#!/usr/bin/env python3
"""Verify and explicitly apply the registration upgrade after a fresh private backup.

This tool never starts services. MySQL connection settings belong in a private
option file. The caller must stop application/admin writes for the whole window.
DDL is not transactional; failures require inspection or backup restoration.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
from datetime import datetime, timezone

MIGRATIONS = (
    ('api/db/phone-profile-registration.sql', '01-phone-profile-registration.sql'),
    ('api/db/enable-phone-registration.sql', '02-enable-phone-registration.sql'),
)
MANIFEST = 'migration-manifest.json'


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def ordinary(path, directory=False):
    path = Path(os.path.abspath(path))
    for item in [*reversed(path.parents), path]:
        info = item.lstat()
        expected = stat.S_ISDIR if directory or item != path else stat.S_ISREG
        if not expected(info.st_mode) or stat.S_ISLNK(info.st_mode):
            raise ValueError('Ordinary path required: ' + str(item))
    return path


def private_file(path):
    path = ordinary(path)
    if stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise ValueError('MySQL option file must be private')
    return path


def migration_manifest(source):
    source = ordinary(source, directory=True)
    return {'format': 1, 'kind': 'teachingopen-registration-upgrade',
        'automatic_apply': False, 'ddl_transactional': False,
        'initialization_order': ['schema', 'data', *[name for _, name in MIGRATIONS]],
        'existing_database_order': [name for _, name in MIGRATIONS],
        'steps': [{'source': source_name, 'file': name,
            'bytes': ordinary(source / source_name).stat().st_size,
            'sha256': sha256(source / source_name)} for source_name, name in MIGRATIONS]}


def verify_migrations(directory, manifest_sha256=None):
    directory = ordinary(directory, directory=True)
    manifest_path = ordinary(directory / MANIFEST)
    if manifest_sha256 is not None:
        if not re.fullmatch('[0-9a-f]{64}', manifest_sha256) or sha256(manifest_path) != manifest_sha256:
            raise ValueError('Migration manifest SHA256 mismatch')
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate migration manifest key')
            result[key] = value
        return result
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'), object_pairs_hook=unique)
    expected = {'format', 'kind', 'automatic_apply', 'ddl_transactional',
        'initialization_order', 'existing_database_order', 'steps'}
    names = [name for _, name in MIGRATIONS]
    if not isinstance(manifest, dict) or set(manifest) != expected or type(manifest['format']) is not int or manifest['format'] != 1:
        raise ValueError('Invalid migration manifest')
    if (manifest['kind'] != 'teachingopen-registration-upgrade' or manifest['automatic_apply'] is not False
            or manifest['ddl_transactional'] is not False or manifest['initialization_order'] != ['schema', 'data', *names]
            or manifest['existing_database_order'] != names or not isinstance(manifest['steps'], list)
            or len(manifest['steps']) != len(MIGRATIONS)):
        raise ValueError('Migration order or execution boundary changed')
    for (source_name, name), step in zip(MIGRATIONS, manifest['steps']):
        if (not isinstance(step, dict) or set(step) != {'source', 'file', 'bytes', 'sha256'}
                or step['source'] != source_name or step['file'] != name
                or type(step['bytes']) is not int or step['bytes'] <= 0
                or not isinstance(step['sha256'], str) or not re.fullmatch('[0-9a-f]{64}', step['sha256'])):
            raise ValueError('Invalid ordered migration receipt')
        sql = ordinary(directory / name)
        if sql.stat().st_size != step['bytes'] or sha256(sql) != step['sha256']:
            raise ValueError('Migration SQL missing or changed: ' + name)
    return manifest


def mysql_command(client, option_file, database):
    if not re.fullmatch('[A-Za-z0-9_]+', database):
        raise ValueError('Explicit simple database name required')
    return [str(ordinary(client)), '--defaults-extra-file=' + str(private_file(option_file)),
        '--default-character-set=utf8mb4', '--batch', '--skip-column-names', database]


def run_mysql(command, sql):
    result = subprocess.run(command, input=sql.encode('utf-8'), capture_output=True, timeout=300)
    if result.returncode:
        # Do not expose SQL diagnostics: an unexpected database error can carry PII.
        raise RuntimeError('MySQL rejected migration/preflight; inspect the target privately before retrying')


def preflight(directory, client, option_file, database, manifest_sha256):
    manifest = verify_migrations(directory, manifest_sha256)
    command = mysql_command(client, option_file, database)
    # The first SQL validates existing columns, indexes, roles and config, but
    # skips user/table changes. It creates/removes only its reserved procedure.
    run_mysql(command, 'SET @teachingopen_registration_preflight_only = 1;\n' +
        (Path(directory) / MIGRATIONS[0][1]).read_text(encoding='utf-8'))
    return manifest


def apply_upgrade(directory, client, mysqldump, option_file, database, manifest_sha256,
                  backup, maintenance_confirmed=False, restore_check_confirmed=False):
    if not maintenance_confirmed or not restore_check_confirmed:
        raise ValueError('Confirm stopped writes and an independently tested backup restore before applying DDL')
    # Reject an invalid dump binary/output before making even the short-lived
    # procedure used by preflight. No executable is started by verification.
    dump_binary = ordinary(mysqldump)
    backup = Path(os.path.abspath(backup))
    parent = ordinary(backup.parent, directory=True)
    if stat.S_IMODE(parent.stat().st_mode) & 0o077:
        raise ValueError('Backup parent must already be private (0700)')
    if backup.exists() or backup.is_symlink() or Path(str(backup) + '.receipt.json').exists():
        raise ValueError('Backup/receipt output must be new; existing files are preserved')
    manifest = preflight(directory, client, option_file, database, manifest_sha256)
    fd = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, 'wb') as out:
            result = subprocess.run([str(dump_binary), '--defaults-extra-file=' + str(private_file(option_file)),
                '--single-transaction', '--quick', '--routines', '--events', '--triggers', '--hex-blob',
                '--no-tablespaces', '--set-gtid-purged=OFF', '--default-character-set=utf8mb4', database],
                stdout=out, stderr=subprocess.PIPE, timeout=600)
        if result.returncode or backup.stat().st_size == 0:
            raise RuntimeError('Fresh backup failed; migration has not been applied; incomplete backup preserved')
        receipt = {'format': 1, 'database': database, 'backup_sha256': sha256(backup),
            'backup_bytes': backup.stat().st_size, 'migration_manifest_sha256': manifest_sha256,
            'created_at': datetime.now(timezone.utc).isoformat(), 'status': 'backup_complete_upgrade_pending',
            'ddl_transactional': False, 'maintenance_confirmed': True, 'restore_check_confirmed': True,
            'completed_steps': []}
        receipt_path = Path(str(backup) + '.receipt.json')
        with os.fdopen(os.open(receipt_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600), 'w') as out:
            json.dump(receipt, out, indent=2); out.write('\n')
        # Reverify after backup, before any profile/column change.
        verify_migrations(directory, manifest_sha256)
        command = mysql_command(client, option_file, database)
        for step in manifest['steps']:
            receipt['status'] = 'applying_' + step['file']
            receipt_path.write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
            try:
                run_mysql(command, 'SET @teachingopen_registration_preflight_only = 0;\n' +
                    (Path(directory) / step['file']).read_text(encoding='utf-8'))
            except Exception:
                receipt['status'] = 'upgrade_failed_inspect_partial_ddl'
                receipt['failed_step'] = step['file']
                receipt_path.write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
                raise
            receipt['completed_steps'].append(step['file'])
        receipt['status'] = 'upgrade_applied'
        receipt_path.write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
        return {'status': 'upgrade_applied', 'database': database, 'backup_sha256': receipt['backup_sha256'],
            'manifest_sha256': manifest_sha256, 'services_started': False, 'ddl_transactional': False}
    except Exception:
        # Any partial DDL remains explicit. No guessed rollback or data deletion.
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('verify', 'preflight', 'apply'))
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--manifest-sha256', required=True,
        help='Expected receipt hash from the approved outer release manifest')
    parser.add_argument('--mysql', type=Path)
    parser.add_argument('--defaults-extra-file', type=Path)
    parser.add_argument('--database')
    parser.add_argument('--mysqldump', type=Path)
    parser.add_argument('--backup', type=Path)
    parser.add_argument('--maintenance-confirmed', action='store_true')
    parser.add_argument('--restore-check-confirmed', action='store_true')
    args = parser.parse_args(argv)
    try:
        if args.action == 'verify':
            verify_migrations(args.directory, args.manifest_sha256)
            result = {'status': 'verified_migrations', 'manifest_sha256': args.manifest_sha256, 'services_started': False}
        else:
            if any(value is None for value in (args.mysql, args.defaults_extra_file, args.database)):
                raise ValueError('Target MySQL binary, private option file and database are required')
            if args.action == 'preflight':
                preflight(args.directory, args.mysql, args.defaults_extra_file, args.database, args.manifest_sha256)
                result = {'status': 'preflight_passed', 'database': args.database, 'user_data_changed': False,
                    'reserved_procedure_created_and_removed': True, 'services_started': False}
            else:
                if args.mysqldump is None or args.backup is None:
                    raise ValueError('Apply requires mysqldump and a new private backup path')
                result = apply_upgrade(args.directory, args.mysql, args.mysqldump, args.defaults_extra_file,
                    args.database, args.manifest_sha256, args.backup, args.maintenance_confirmed, args.restore_check_confirmed)
    except (ValueError, OSError, RuntimeError, subprocess.TimeoutExpired) as error:
        parser.exit(1, 'registration_upgrade: ' + str(error) + '\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
