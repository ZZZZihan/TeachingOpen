#!/usr/bin/env python3
"""Prepare a private, fresh-database launch seed without executing source SQL.

The source acquisition and reviewed 69-table parser are shared with
production_fixture. This tool creates files only; it never connects to a DB.
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
from decimal import Decimal

import production_fixture as fixture

FORMAT = 1
KIND = 'teachingopen-private-launch-data'
HERE = Path(__file__).resolve().parent
POLICY_TABLES = frozenset('''sys_check_rule sys_config sys_dict sys_dict_item
sys_fill_rule sys_permission sys_permission_data_rule sys_role sys_role_permission
sys_user sys_user_depart sys_user_role sys_depart teaching_course
teaching_course_unit teaching_menu'''.split())
# These are site settings, not environment credentials or data-source connections.
CONFIG_KEYS = frozenset('''_address brandName footer _phone _defaultRole logo
allowReg _linkman _defaultDepart brandDesc banner bannerLinks _indexHtml customJS
_workShareHtml logo2 homeBgColor homeBgRepeat file_homeBg _homeHtml customCss
avatar allowComment'''.split())
BRAND_KEYS = frozenset({'logo', 'banner', 'logo2'})
HASH = re.compile('[0-9a-f]{64}')
COMMIT = re.compile('[0-9a-f]{40}')


def identifiers(value):
    return [item for item in str(value or '').split(',') if item]


def is_flag(value, number):
    return str(value) == str(number)


def keyed(rows, column='id'):
    result = {row[column]: row for row in rows}
    if len(result) != len(rows) or None in result or '' in result:
        raise ValueError('Missing or duplicate identifiers in retained definitions')
    return result


def admin_permission_set(rows, admin_id):
    roles = {row['role_id'] for row in rows['sys_user_role'] if row['user_id'] == admin_id}
    permissions = keyed(rows['sys_permission'])
    return {row['permission_id'] for row in rows['sys_role_permission']
            if row['role_id'] in roles and row['permission_id'] in permissions}


def select_rows(source):
    """Retain one effective admin, system definitions and courses; clear history."""
    rows = copy.deepcopy(source)
    roles = keyed(rows['sys_role'])
    role_codes = keyed(rows['sys_role'], 'role_code')
    if not {'admin', 'dev', 'student', 'teacher'} <= set(role_codes):
        raise ValueError('Required administrator and registration role definitions are missing')
    users = keyed(rows['sys_user'])
    keyed(rows['sys_user'], 'username')
    admin_ids = {row['user_id'] for row in rows['sys_user_role']
                 if row['role_id'] in roles and roles[row['role_id']]['role_code'] == 'admin'}
    admins = [row for row in users.values() if row['id'] in admin_ids
              and is_flag(row['status'], 1) and is_flag(row['del_flag'], 0)]
    if len(admins) != 1:
        raise ValueError('Exactly one effective, undeleted admin-role account is required')
    admin = admins[0]
    if not admin['username'] or not admin['password'] or not admin['salt']:
        raise ValueError('The retained administrator must have original login credentials')
    original_admin = copy.deepcopy(admin)
    effective_permissions = admin_permission_set(rows, admin['id'])
    user_roles = [row for row in rows['sys_user_role'] if row['user_id'] == admin['id']]
    if any(row['role_id'] not in roles for row in user_roles):
        raise ValueError('The retained administrator has an unknown role definition')
    codes = {roles[row['role_id']]['role_code'] for row in user_roles}
    if codes != {'admin', 'dev'} or len(user_roles) != 2:
        raise ValueError('The reviewed administrator must retain exactly admin and dev roles')

    departments = keyed(rows['sys_depart'])
    # In this application org_type=2 means a historical classroom. Preserve only
    # the administrator's non-class organization and its existing root ancestors.
    matches = [row for row in departments.values() if row['org_code'] == admin['org_code']
               and is_flag(row['org_type'], 1) and not is_flag(row['del_flag'], 1)]
    if len(matches) != 1:
        raise ValueError('Administrator organization requires one existing non-class root')
    retained_depart_ids = {matches[0]['id']}
    managed = identifiers(admin['depart_ids'])
    retained_depart_ids.update(value for value in managed if value in departments
                              and is_flag(departments[value]['org_type'], 1)
                              and not is_flag(departments[value]['del_flag'], 1))
    for identity in list(retained_depart_ids):
        seen = set()
        current = identity
        while current:
            if current in seen or current not in departments:
                raise ValueError('Administrator organization has a missing or cyclic ancestor')
            seen.add(current)
            depart = departments[current]
            if not is_flag(depart['org_type'], 1) or is_flag(depart['del_flag'], 1):
                raise ValueError('Administrator organization includes a historical classroom')
            retained_depart_ids.add(current)
            current = depart['parent_id']
    kept_managed = [value for value in managed if value in retained_depart_ids]
    admin['depart_ids'] = ','.join(kept_managed)
    rows['sys_user'] = [admin]
    rows['sys_user_role'] = user_roles
    rows['sys_depart'] = [row for row in rows['sys_depart'] if row['id'] in retained_depart_ids]
    rows['sys_user_depart'] = [row for row in rows['sys_user_depart']
                               if row['user_id'] == admin['id'] and row['dep_id'] in retained_depart_ids]

    permissions = keyed(rows['sys_permission'])
    rule_ids = {row['id'] for row in rows['sys_permission_data_rule']
                if row['permission_id'] in permissions}
    removed_permission_links = 0
    rows['sys_permission_data_rule'] = [row for row in rows['sys_permission_data_rule']
                                        if row['id'] in rule_ids]
    permission_links = []
    for row in rows['sys_role_permission']:
        if row['role_id'] not in roles or row['permission_id'] not in permissions:
            removed_permission_links += 1
            continue
        if any(value not in rule_ids for value in identifiers(row['data_rule_ids'])):
            raise ValueError('A retained permission association has an unknown data rule')
        permission_links.append(row)
    rows['sys_role_permission'] = permission_links
    if effective_permissions != admin_permission_set(rows, admin['id']):
        raise ValueError('Administrator effective permission set changed')

    dictionary_ids = set(keyed(rows['sys_dict']))
    rows['sys_dict_item'] = [row for row in rows['sys_dict_item'] if row['dict_id'] in dictionary_ids]

    configs = keyed(rows['sys_config'], 'config_key')
    if set(configs) - CONFIG_KEYS:
        raise ValueError('Unreviewed site config needs a separate environment/credential policy')
    if 'allowReg' not in configs or not is_flag(configs['allowReg']['config_enabled'], 1):
        raise ValueError('Registration requires one enabled allowReg config row')
    default_depart_cleared = bool(configs.get('_defaultDepart', {}).get('config_value'))
    default_role_cleared = bool(configs.get('_defaultRole', {}).get('config_value'))
    if '_defaultDepart' in configs:
        configs['_defaultDepart']['config_value'] = ''
    # No implicit registration assignment to historical roles or classrooms.
    if configs.get('_defaultRole', {}).get('config_value'):
        configs['_defaultRole']['config_value'] = ''
    for key in ('avatar', 'file_homeBg'):
        if configs.get(key, {}).get('config_value'):
            raise ValueError('Non-brand site asset needs an explicit whitelist review')
    course_ids = set(keyed(rows['teaching_course']))
    if any(row['course_id'] not in course_ids for row in rows['teaching_course_unit']):
        raise ValueError('Course unit references a missing real course')
    if any(is_flag(row['del_flag'], 1) for table in ('teaching_course', 'teaching_course_unit') for row in rows[table]):
        raise ValueError('Deleted course content requires separate selection review')
    # Do not turn restricted courses into public courses when removing classes.
    for course in rows['teaching_course']:
        if any(value not in retained_depart_ids for value in identifiers(course['depart_ids'])):
            raise ValueError('Course has a historical organization restriction; review access before removing it')
        if is_flag(course['show_home'], 1) and not is_flag(course['is_shared'], 1):
            raise ValueError('A homepage course would become inaccessible after class cleanup')

    for table in rows:
        if table not in POLICY_TABLES:
            rows[table] = []
    actor_changes = 0
    org_changes = 0
    org_codes = {row['org_code'] for row in rows['sys_depart']}
    for table, data in rows.items():
        for row in data:
            for column in ('create_by', 'update_by'):
                if row.get(column) and row[column] not in {admin['username'], admin['id']}:
                    row[column] = admin['username']
                    actor_changes += 1
            if row.get('sys_org_code') and row['sys_org_code'] not in org_codes:
                row['sys_org_code'] = None
                org_changes += 1
    # Login/account values are preserved, except directed cleanup of obsolete
    # responsible-department IDs and audit actors. Do not reset password or salt.
    for column in ('id', 'username', 'realname', 'password', 'salt', 'status', 'del_flag', 'org_code'):
        if admin[column] != original_admin[column]:
            raise ValueError('An original administrator login field changed')
    result = {
        'administrator_login_preserved': True,
        'administrator_effective_permissions_preserved': True,
        'administrator_effective_permission_count': len(effective_permissions),
        'administrator_role_count': len(user_roles),
        'removed_admin_managed_department_references': len(managed) - len(kept_managed),
        'cleared_legacy_registration_department': default_depart_cleared,
        'cleared_legacy_registration_role': default_role_cleared,
        'removed_orphan_role_permission_rows': removed_permission_links,
        'removed_orphan_permission_data_rule_rows': len(source['sys_permission_data_rule']) - len(rule_ids),
        'removed_orphan_dictionary_item_rows': len(source['sys_dict_item']) - len(rows['sys_dict_item']),
        'audit_actor_fields_mapped_to_administrator': actor_changes,
        'obsolete_org_metadata_fields_cleared': org_changes,
        'permission_definitions_with_missing_parent': sum(bool(row['parent_id']) and row['parent_id'] not in permissions for row in rows['sys_permission']),
        'course_visibility_and_sharing_preserved': True,
    }
    validate_rows(rows)
    return rows, result


def validate_rows(rows):
    """Check launch semantics independently after serializing and parsing seed SQL."""
    if set(rows) != set(json.loads(fixture.SCHEMA_PROFILE.read_text())):
        raise ValueError('Launch data must contain exactly the reviewed 69 base tables')
    if any(data for table, data in rows.items() if table not in POLICY_TABLES):
        raise ValueError('Historical, demonstration, file, scheduler or session rows survived')
    if len(rows['sys_user']) != 1:
        raise ValueError('Launch data must contain one account only')
    admin = rows['sys_user'][0]
    roles = keyed(rows['sys_role'])
    role_codes = keyed(rows['sys_role'], 'role_code')
    if not {'admin', 'dev', 'student', 'teacher'} <= set(role_codes):
        raise ValueError('Required system and registration roles are missing')
    if not is_flag(admin['status'], 1) or not is_flag(admin['del_flag'], 0):
        raise ValueError('Launch administrator is not effective')
    if not all(admin.get(key) for key in ('id', 'username', 'password', 'salt')):
        raise ValueError('Launch administrator login is incomplete')
    if any(row['user_id'] != admin['id'] or row['role_id'] not in roles for row in rows['sys_user_role']):
        raise ValueError('Historical user or unknown role association survived')
    if len(rows['sys_user_role']) != 2 or {roles[row['role_id']]['role_code'] for row in rows['sys_user_role']} != {'admin', 'dev'}:
        raise ValueError('Launch administrator roles differ from the reviewed roles')
    deps = keyed(rows['sys_depart'])
    if any(not is_flag(row['org_type'], 1) or is_flag(row['del_flag'], 1) for row in deps.values()):
        raise ValueError('Historical classroom survived')
    if sum(row['org_code'] == admin['org_code'] for row in deps.values()) != 1:
        raise ValueError('Administrator organization is missing or ambiguous')
    if any(value not in deps for value in identifiers(admin['depart_ids'])):
        raise ValueError('Administrator has an orphan responsible-department reference')
    if any(row['user_id'] != admin['id'] or row['dep_id'] not in deps for row in rows['sys_user_depart']):
        raise ValueError('Historical classroom membership survived')
    perms = keyed(rows['sys_permission'])
    rules = keyed(rows['sys_permission_data_rule'])
    if any(row['permission_id'] not in perms for row in rules.values()):
        raise ValueError('Orphan permission data rule survived')
    if any(row['role_id'] not in roles or row['permission_id'] not in perms
           or any(value not in rules for value in identifiers(row['data_rule_ids'])) for row in rows['sys_role_permission']):
        raise ValueError('Orphan permission association survived')
    dictionary_ids = set(keyed(rows['sys_dict']))
    if any(row['dict_id'] not in dictionary_ids for row in rows['sys_dict_item']):
        raise ValueError('Orphan dictionary item survived')
    config = keyed(rows['sys_config'], 'config_key')
    if set(config) - CONFIG_KEYS or 'allowReg' not in config or not is_flag(config['allowReg']['config_enabled'], 1):
        raise ValueError('Registration or site config differs from the reviewed scope')
    if any(config.get(key, {}).get('config_value') for key in ('_defaultDepart', '_defaultRole', 'avatar', 'file_homeBg')):
        raise ValueError('Unreviewed historical assignment or extra site asset survived')
    courses = keyed(rows['teaching_course'])
    if any(row['course_id'] not in courses for row in rows['teaching_course_unit']):
        raise ValueError('Orphan real course unit survived')
    if any(is_flag(row['show_home'], 1) and not is_flag(row['is_shared'], 1) for row in courses.values()):
        raise ValueError('Homepage course would require removed historical class membership')


def resource_scopes(rows):
    references = fixture.resource_inventory(rows)
    if references['unsafe_references']:
        raise ValueError('A real course contains an unsafe resource reference')
    brand = set()
    for row in rows['sys_config']:
        if row['config_key'] in BRAND_KEYS and row['config_value']:
            for value in fixture.reference_candidates(row['config_value']):
                brand.add(fixture.safe_relative(value))
    return {'course_assets': references['paths'], 'system_brand_assets': sorted(brand)}, references['external_references']


def literal(value):
    """Emit scalar dump literals accepted by the existing bounded parser."""
    if value is None:
        return 'NULL'
    if isinstance(value, (int, Decimal)):
        return str(value)
    if isinstance(value, bytes):
        return '0x' + value.hex()
    escapes = {'\\': '\\\\', "'": "\\'", '\0': '\\0', '\b': '\\b', '\n': '\\n', '\r': '\\r', '\t': '\\t', '\x1a': '\\Z'}
    return "'" + ''.join(escapes.get(char, char) for char in str(value)) + "'"


def emit_seed(ddl, rows):
    # CREATE fails for an existing table: this seed is deliberately not a reset
    # or incremental migration. Session directives are allowlisted by the parser.
    output = ["-- Private TeachingOpen launch seed. Import into a NEW empty database only.",
              "/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;",
              '/*!40101 SET NAMES utf8mb4 */;', '/*!40014 SET FOREIGN_KEY_CHECKS=0 */;']
    output.extend(fixture.render_ddl(tokens) + ';' for tokens in ddl.values())
    for table, data in rows.items():
        output.extend('INSERT INTO `' + table + '` VALUES (' + ','.join(literal(value) for value in row.values()) + ');' for row in data)
    output.append('/*!40014 SET FOREIGN_KEY_CHECKS=1 */;')
    output.append('/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;')
    return '\n'.join(output) + '\n'


def ordinary_path(path):
    path = Path(path).absolute()
    for parent in (path, *path.parents):
        if parent.is_symlink():
            raise ValueError('Symlinks in source or package paths are forbidden')
    return path


def private_tree(path):
    path = ordinary_path(path)
    if not path.is_dir() or stat.S_IMODE(path.stat().st_mode) != 0o700:
        raise ValueError('Package directory must be private (mode 700)')
    found = set()
    for directory, dirs, files in os.walk(path, followlinks=False):
        for name in dirs + files:
            item = Path(directory) / name
            mode = item.lstat().st_mode
            expected_mode = 0o700 if stat.S_ISDIR(mode) else 0o600
            if stat.S_ISLNK(mode) or not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)) or stat.S_IMODE(mode) != expected_mode:
                raise ValueError('Package contains links, special files or non-private permissions')
            if stat.S_ISREG(mode):
                found.add(item.relative_to(path).as_posix())
    return found


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode()


def prepare(source, output, source_commit):
    source, output = ordinary_path(source), ordinary_path(output)
    if not COMMIT.fullmatch(source_commit):
        raise ValueError('Bind the package to an exact 40-character candidate source commit')
    if output.exists():
        raise ValueError('Destination already exists; no private package is overwritten')
    if output == source or source in output.parents or output in source.parents:
        raise ValueError('Output must be independent of the read-only acquisition source')
    dump = fixture.read_private(source / 'teachingopen.sql')
    source_metadata = fixture.read_private(source / 'source-manifest.json')
    metadata = json.loads(source_metadata)
    digest = hashlib.sha256(dump).hexdigest()
    if metadata.get('sha256') != digest or metadata.get('bytes') != len(dump):
        raise ValueError('Source SQL differs from its private acquisition manifest')
    ddl, original_rows = fixture.parse_dump(dump.decode('utf-8'))
    rows, changes = select_rows(original_rows)
    scopes, external = resource_scopes(rows)
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    ordinary_path(output.parent)
    output.mkdir(mode=0o700)
    (output / 'mysql').mkdir(mode=0o700)
    (output / 'uploads').mkdir(mode=0o700)
    # Existing copy_assets checks source hash/size, whitelist, every path component,
    # destination hash and free space. It copies bytes, never links source files.
    assets = fixture.copy_assets(source, output, {'paths': sorted(set().union(*map(set, scopes.values())))})
    changes['normalized_app_static_references'] = fixture.normalize_resources(rows, set(assets['files']))
    final_scopes, final_external = resource_scopes(rows)
    if scopes != final_scopes or external != final_external:
        raise ValueError('Course asset references changed during static-route relocation')
    seed = emit_seed(ddl, rows)
    parsed_ddl, parsed_rows = fixture.parse_dump(seed)
    if parsed_ddl != ddl or parsed_rows != rows:
        raise ValueError('Generated seed failed safe scalar roundtrip')
    validate_rows(parsed_rows)
    fixture.private_write(output / 'mysql/seed.sql', seed)
    private_assets = {'files': assets['files'], 'scopes': scopes}
    fixture.private_write(output / 'assets-manifest.json', json_bytes(private_assets))
    counts = {'source': {table: len(data) for table, data in original_rows.items()},
              'retained': {table: len(data) for table, data in rows.items()}}
    scope_counts = {name: {'count': len(paths), 'bytes': sum(assets['files'][item]['bytes'] for item in paths)} for name, paths in scopes.items()}
    # All identifiers, original logins, hashes/salts and resource names stay in
    # mode-600 private files. The portable manifest contains only hashes/counts.
    manifest = {
        'format': FORMAT, 'kind': KIND, 'complete': True, 'source_commit': source_commit,
        'source_sha256': digest, 'source_bytes': len(dump),
        'source_manifest_sha256': hashlib.sha256(source_metadata).hexdigest(),
        'source_assets_manifest_sha256': assets['source_manifest_sha256'],
        'schema_policy_sha256': fixture.sha256(fixture.SCHEMA_PROFILE),
        'parser_sha256': fixture.sha256(Path(fixture.__file__)),
        'generator_sha256': fixture.sha256(Path(__file__)),
        'counts': counts, 'changes': changes,
        'assets': {'count': assets['count'], 'bytes': assets['bytes'], **scope_counts,
                   'external_references': external, 'student_files_copied': False},
        'initial_state': {'registered_students': 0, 'registered_teachers': 0,
                          'registration_profiles': 0, 'homepage_courses': sum(is_flag(row['show_home'], 1) for row in rows['teaching_course']),
                          'hidden_courses': sum(is_flag(row['show_home'], 0) for row in rows['teaching_course'])},
        'private_files': {name: fixture.sha256(output / name) for name in ('mysql/seed.sql', 'assets-manifest.json')},
        'database_imported': False, 'production_modified': False,
    }
    if fixture.sha256(source / 'teachingopen.sql') != digest or fixture.sha256(source / 'source-manifest.json') != manifest['source_manifest_sha256'] or fixture.sha256(source / 'assets-manifest.json') != assets['source_manifest_sha256']:
        raise ValueError('Source acquisition changed during preparation')
    fixture.private_write(output / 'manifest.json', json_bytes(manifest))
    return verify(output)


def verify(package):
    package = ordinary_path(package)
    found = private_tree(package)
    manifest = json.loads(fixture.read_private(package / 'manifest.json'))
    if manifest.get('format') != FORMAT or manifest.get('kind') != KIND or manifest.get('complete') is not True:
        raise ValueError('Incomplete or unsupported private launch package')
    if not COMMIT.fullmatch(manifest.get('source_commit', '')):
        raise ValueError('Package lacks an exact candidate source commit')
    for key in ('source_sha256', 'source_manifest_sha256', 'source_assets_manifest_sha256', 'generator_sha256', 'parser_sha256', 'schema_policy_sha256'):
        if not isinstance(manifest.get(key), str) or not HASH.fullmatch(manifest[key]):
            raise ValueError('Package lacks a valid source/policy hash binding')
    if (manifest['schema_policy_sha256'] != fixture.sha256(fixture.SCHEMA_PROFILE)
            or manifest['generator_sha256'] != fixture.sha256(Path(__file__))
            or manifest['parser_sha256'] != fixture.sha256(Path(fixture.__file__))):
        raise ValueError('Package was produced by a different reviewed schema or generator')
    if set(manifest.get('private_files', {})) != {'mysql/seed.sql', 'assets-manifest.json'}:
        raise ValueError('Package private file list escaped the reviewed scope')
    for name, digest in manifest['private_files'].items():
        if not isinstance(digest, str) or not HASH.fullmatch(digest) or fixture.sha256(package / name) != digest:
            raise ValueError('Private launch file differs from its manifest')
    ddl, rows = fixture.parse_dump(fixture.read_private(package / 'mysql/seed.sql').decode('utf-8'))
    validate_rows(rows)
    if manifest['counts']['retained'] != {table: len(data) for table, data in rows.items()}:
        raise ValueError('Seed row counts differ from launch manifest')
    assets = json.loads(fixture.read_private(package / 'assets-manifest.json'))
    scopes, external = resource_scopes(rows)
    if assets.get('scopes') != scopes or set(assets.get('files', {})) != set().union(*map(set, scopes.values())):
        raise ValueError('Copied assets escaped the exact course and system-brand white lists')
    expected = {'manifest.json', 'mysql/seed.sql', 'assets-manifest.json'} | {'uploads/' + relative for relative in assets['files']}
    if found != expected:
        raise ValueError('Missing or extra private package file, including unreferenced uploads')
    for relative, record in assets['files'].items():
        if not isinstance(record, dict) or set(record) != {'bytes', 'sha256'} or type(record['bytes']) is not int or record['bytes'] < 0 or not isinstance(record['sha256'], str) or not HASH.fullmatch(record['sha256']):
            raise ValueError('Invalid package asset hash/size record')
        item = fixture.ordinary_asset(package / 'uploads', relative)
        if item.stat().st_size != record['bytes'] or fixture.sha256(item) != record['sha256']:
            raise ValueError('Private package asset differs from the source-bound manifest')
    expected_assets = {'count': len(assets['files']), 'bytes': sum(record['bytes'] for record in assets['files'].values()),
                       'external_references': external, 'student_files_copied': False}
    expected_assets.update({name: {'count': len(paths), 'bytes': sum(assets['files'][item]['bytes'] for item in paths)} for name, paths in scopes.items()})
    if manifest['assets'] != expected_assets:
        raise ValueError('Aggregate asset evidence differs from private assets')
    initial = {'registered_students': 0, 'registered_teachers': 0, 'registration_profiles': 0,
               'homepage_courses': sum(is_flag(row['show_home'], 1) for row in rows['teaching_course']),
               'hidden_courses': sum(is_flag(row['show_home'], 0) for row in rows['teaching_course'])}
    if manifest['initial_state'] != initial or manifest.get('database_imported') is not False or manifest.get('production_modified') is not False:
        raise ValueError('Launch initial-state evidence was changed')
    return {'verified': True, 'package': str(package), 'manifest_sha256': fixture.sha256(package / 'manifest.json'),
            'tables': len(ddl), 'accounts': 1, 'administrator_roles': 2,
            'courses': len(rows['teaching_course']), 'units': len(rows['teaching_course_unit']),
            'assets': expected_assets, 'initial_state': initial,
            'database_imported': False, 'production_modified': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='action', required=True)
    create = commands.add_parser('prepare')
    create.add_argument('--source', type=Path, required=True, help='Original private acquisition directory')
    create.add_argument('--output', type=Path, help='New private package; default: SOURCE/../artifacts/launch-data-20261009')
    create.add_argument('--source-commit', required=True, help='Exact reviewed application candidate commit')
    check = commands.add_parser('verify')
    check.add_argument('--package', type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.action == 'prepare':
            output = args.output or args.source.parent / 'artifacts/launch-data-20261009'
            result = prepare(args.source, output, args.source_commit)
        else:
            result = verify(args.package)
    except (ValueError, OSError, KeyError, TypeError, UnicodeError, json.JSONDecodeError):
        # Parser errors and file paths can contain private values. The operator
        # receives no raw exception, source values or accidental account output.
        print('Launch data preparation/verification failed; no existing source or database was changed.', file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == '__main__':
    sys.exit(main())
