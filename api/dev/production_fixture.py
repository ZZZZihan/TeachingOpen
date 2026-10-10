"""Private, reviewed-schema production copies for isolated local comparison.

Parse mysqldump literals in Python; never execute source SQL. This is a bounded
format importer, not a general SQL parser, anonymizer, or production restore.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import shutil
import socket
import subprocess
from decimal import Decimal
from urllib.parse import unquote, urlsplit

from local_recovery import (command, database_inventory, local_path, private_write,
                            sha256, sql)
from local_runtime import assert_app_config, assert_mysql_owner, load_ports, validate_ports

FORMAT = 1
KIND = 'teachingopen-private-production-fixture'
HERE = Path(__file__).resolve().parent
SCHEMA_PROFILE = HERE / 'production-fixture-schema.json'
RETAIN = frozenset('''sys_category sys_depart sys_depart_permission sys_depart_role
sys_depart_role_permission sys_depart_role_user sys_dict sys_dict_item sys_file
sys_permission sys_role sys_role_permission sys_user sys_user_depart sys_user_role
teaching_additional_work teaching_course teaching_course_dept teaching_course_unit
teaching_menu teaching_student teaching_work teaching_work_correct'''.split())
USER_CLEAR = frozenset('''avatar birthday sex email phone third_id third_type
work_no post school telephone'''.split())
DEPART_CLEAR = frozenset('''depart_name_en depart_name_abbr description mobile fax
address memo'''.split())
CONTENT_COLUMNS = {
    'teaching_course': {'course_name', 'course_desc'},
    'teaching_course_unit': {'unit_name', 'unit_intro', 'media_content', 'course_work'},
    'teaching_additional_work': {'work_name', 'work_desc'},
}
RESOURCE_COLUMNS = {
    'teaching_course': {'course_icon', 'course_cover', 'course_map', 'course_desc'},
    'teaching_course_unit': {'unit_cover', 'course_video', 'course_case', 'course_ppt',
                             'course_work', 'course_work_answer', 'course_plan', 'media_content', 'unit_intro'},
    'teaching_additional_work': {'work_cover', 'work_url', 'work_document_url', 'work_desc'},
}
RESOURCE_TEXT_COLUMNS = frozenset({'course_desc', 'unit_intro', 'media_content', 'work_desc'})
URL_KEYS = frozenset({'url', 'src', 'path', 'file', 'filepath', 'poster', 'cover'})
DDL_WORDS = frozenset('''CREATE TABLE VARCHAR CHAR INT INTEGER TINYINT SMALLINT BIGINT
DECIMAL DOUBLE FLOAT DATE DATETIME TIMESTAMP TEXT LONGTEXT TINYTEXT BLOB LONGBLOB
NOT NULL DEFAULT CHARACTER SET COLLATE COMMENT PRIMARY KEY UNIQUE USING BTREE HASH
UNSIGNED ZEROFILL AUTO_INCREMENT CONSTRAINT FOREIGN REFERENCES ENGINE INNODB CHARSET
ROW_FORMAT DYNAMIC COMPACT REDUNDANT FIXED'''.split())
CHARSETS = frozenset('utf8 utf8mb3 utf8mb4 utf8_general_ci utf8mb3_general_ci '
                     'utf8mb4_general_ci utf8mb4_unicode_ci utf8mb4_0900_ai_ci'.split())
ESCAPES = {'0': '\0', 'b': '\b', 'n': '\n', 'r': '\r', 't': '\t', 'Z': '\x1a',
           "'": "'", '"': '"', '\\': '\\'}
NUMBER = re.compile(r'(?:0x[0-9A-Fa-f]+|[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)')
WORD = re.compile('[A-Za-z_][A-Za-z0-9_]*')


def read_private(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o077:
        raise ValueError('Source and metadata must be ordinary private files (mode 600)')
    return path.read_bytes()


def safe_directive(body):
    """Accept and discard only mysqldump session settings and key toggles."""
    body = re.sub(r'^\d{5,6}\s+', '', body.strip())
    if re.fullmatch(r'ALTER TABLE `[A-Za-z][A-Za-z0-9_]*` (?:DISABLE|ENABLE) KEYS', body):
        return
    # These tokens are never sent to MySQL. Restrict both names and RHS anyway.
    if body.startswith('SET '):
        assignments = body[4:].split(',')
        names = {'CHARACTER_SET_CLIENT', 'CHARACTER_SET_RESULTS', 'COLLATION_CONNECTION',
                 'TIME_ZONE', 'UNIQUE_CHECKS', 'FOREIGN_KEY_CHECKS', 'SQL_MODE', 'SQL_NOTES'}
        for assignment in assignments:
            if re.fullmatch(r'NAMES (?:utf8mb4|utf8)', assignment.strip(), re.I):
                continue
            match = re.fullmatch(r'(@?(?:OLD_)?[A-Za-z_]+)\s*=\s*(.+)', assignment.strip())
            if not match:
                break
            left, right = match.groups()
            left = left.lstrip('@').upper().removeprefix('OLD_')
            if left != 'SAVED_CS_CLIENT' and left not in names:
                break
            reference = right.lstrip('@').upper().removeprefix('OLD_')
            if (right in {'0', '1', 'utf8mb4', 'utf8', "'+00:00'", "'NO_AUTO_VALUE_ON_ZERO'"}
                    or (right.startswith('@') and (reference in names or reference == 'SAVED_CS_CLIENT'))):
                continue
            break
        else:
            return
    raise ValueError('Unsupported executable comment; source SQL was not executed')


def lex(text):
    """Tokenize quoted literals, identifiers and comments without SQL execution."""
    result, i = [], 0
    while i < len(text):
        ch = text[i]
        if ch.isspace():
            i += 1; continue
        if text.startswith('--', i) and (i + 2 == len(text) or text[i + 2].isspace()):
            end = text.find('\n', i); i = len(text) if end < 0 else end + 1; continue
        if ch == '#':
            end = text.find('\n', i); i = len(text) if end < 0 else end + 1; continue
        if text.startswith('/*', i):
            end = text.find('*/', i + 2)
            if end < 0:
                raise ValueError('Unterminated SQL comment')
            if text.startswith('/*!', i):
                safe_directive(text[i + 3:end])
            i = end + 2; continue
        if ch in "'`":
            quote, value = ch, []
            i += 1
            while i < len(text):
                if text[i] == quote:
                    if i + 1 < len(text) and text[i + 1] == quote:
                        value.append(quote); i += 2; continue
                    i += 1; break
                if quote == "'" and text[i] == '\\':
                    i += 1
                    if i >= len(text):
                        raise ValueError('Unterminated escaped SQL literal')
                    # MySQL retains backslash for LIKE wildcards.
                    value.append(ESCAPES.get(text[i], '\\' + text[i] if text[i] in '%_' else text[i]))
                else:
                    value.append(text[i])
                i += 1
            else:
                raise ValueError('Unterminated quoted SQL value')
            value = ''.join(value)
            if quote == '`' and not re.fullmatch('[A-Za-z][A-Za-z0-9_]*', value):
                raise ValueError('Qualified or unsupported SQL identifier')
            result.append(('id' if quote == '`' else 'str', value)); continue
        number = NUMBER.match(text, i)
        if number:
            value = number.group(); result.append(('hex' if value.startswith('0x') else 'num', value)); i += len(value); continue
        word = WORD.match(text, i)
        if word:
            value = word.group(); result.append(('word', value)); i += len(value); continue
        if ch in '(),;=':
            result.append(('sym', ch)); i += 1; continue
        raise ValueError('Unsupported SQL token; no original data is printed')
    return result


def statements(tokens):
    current = []
    for token in tokens:
        if token == ('sym', ';'):
            if current:
                yield current
            current = []
        else:
            current.append(token)
    if current:
        raise ValueError('Source SQL requires a final statement terminator')


def split_groups(tokens):
    depth, groups, current = 0, [], []
    for token in tokens:
        if token == ('sym', '('):
            depth += 1
        elif token == ('sym', ')'):
            depth -= 1
        if depth < 0:
            raise ValueError('Unbalanced SQL parentheses')
        if token == ('sym', ',') and depth == 0:
            groups.append(current); current = []
        else:
            current.append(token)
    if depth:
        raise ValueError('Unbalanced SQL parentheses')
    groups.append(current)
    return groups


def schema_columns(tokens):
    if tokens[:2] != [('word', 'CREATE'), ('word', 'TABLE')] or tokens[2][0] != 'id' or tokens[3] != ('sym', '('):
        raise ValueError('Only unqualified CREATE TABLE is supported')
    depth, end = 1, 4
    while end < len(tokens) and depth:
        if tokens[end] == ('sym', '('): depth += 1
        if tokens[end] == ('sym', ')'): depth -= 1
        end += 1
    if depth:
        raise ValueError('Invalid table definition')
    columns = []
    for group in split_groups(tokens[4:end - 1]):
        if group and group[0][0] == 'id':
            if len(group) < 2 or group[1][0] != 'word':
                raise ValueError('Invalid column definition')
            data_type = group[1][1].lower()
            j, size = 2, []
            if j < len(group) and group[j] == ('sym', '('):
                j += 1
                while j < len(group) and group[j] != ('sym', ')'):
                    size.append(group[j][1]); j += 1
                if j == len(group): raise ValueError('Invalid column size')
            # Integer display widths changed between MySQL releases; not storage.
            if data_type not in {'int', 'integer', 'tinyint', 'smallint', 'bigint'}:
                data_type += '(' + ''.join(size) + ')' if size else ''
            columns.append([group[0][1], data_type])
    return tokens[2][1], columns


def validate_ddl(tokens, profile):
    name, columns = schema_columns(tokens)
    if name not in profile or columns != profile[name]:
        raise ValueError('Unknown table, changed column order/type, or unreviewed column: ' + name)
    for kind, value in tokens:
        if kind == 'word' and value.upper() not in DDL_WORDS and value.lower() not in CHARSETS:
            raise ValueError('Unreviewed DDL keyword in table: ' + name)
        if kind == 'hex' or (kind == 'sym' and value not in '(),='):
            raise ValueError('Unsupported DDL syntax in table: ' + name)
    if [('word', 'ENGINE'), ('sym', '='), ('word', 'InnoDB')] != tokens[tokens.index(('word', 'ENGINE')):tokens.index(('word', 'ENGINE')) + 3]:
        raise ValueError('Only InnoDB base tables are supported')
    for i, token in enumerate(tokens):
        if token == ('word', 'REFERENCES') and (i + 1 == len(tokens) or tokens[i + 1][0] != 'id' or tokens[i + 1][1] not in profile):
            raise ValueError('Foreign key escaped reviewed tables')
    # Strip cosmetic comments; schema comments can contain operator identifiers.
    clean, i = [], 0
    while i < len(tokens):
        if tokens[i] == ('word', 'COMMENT'):
            i += 1
            if i < len(tokens) and tokens[i] == ('sym', '='): i += 1
            if i >= len(tokens) or tokens[i][0] != 'str': raise ValueError('Invalid schema comment')
            i += 1; continue
        clean.append(tokens[i]); i += 1
    return name, clean


def literal(token):
    kind, value = token
    if kind == 'str': return value
    if kind == 'word' and value.upper() == 'NULL': return None
    if kind == 'num': return Decimal(value)
    if kind == 'hex':
        if len(value[2:]) % 2: raise ValueError('Odd binary literal')
        return bytes.fromhex(value[2:])
    raise ValueError('INSERT expressions are forbidden; only scalar dump literals are supported')


def parse_dump(data, profile=None):
    profile = profile or json.loads(SCHEMA_PROFILE.read_text())
    ddl, rows = {}, {name: [] for name in profile}
    for tokens in statements(lex(data)):
        head = [value.upper() for kind, value in tokens[:3]]
        if head[:2] == ['CREATE', 'TABLE']:
            name, definition = validate_ddl(tokens, profile)
            if name in ddl: raise ValueError('Duplicate table definition')
            ddl[name] = definition
        elif head[:2] == ['INSERT', 'INTO']:
            if len(tokens) < 6 or tokens[2][0] != 'id' or tokens[3] != ('word', 'VALUES'):
                raise ValueError('Only literal full-row INSERT INTO reviewed table VALUES is supported')
            name = tokens[2][1]
            if name not in ddl: raise ValueError('INSERT lacks a preceding reviewed table definition')
            names = [column[0] for column in profile[name]]
            for group in split_groups(tokens[4:]):
                if group[0] != ('sym', '(') or group[-1] != ('sym', ')'):
                    raise ValueError('Invalid INSERT row')
                values = split_groups(group[1:-1])
                if len(values) != len(names) or any(len(value) != 1 for value in values):
                    raise ValueError('INSERT expression or incorrect column count')
                rows[name].append(dict(zip(names, (literal(value[0]) for value in values))))
        elif (len(tokens) == 5 and head[:3] == ['DROP', 'TABLE', 'IF']
              and tokens[3] == ('word', 'EXISTS') and tokens[4][0] == 'id' and tokens[4][1] in profile):
            pass
        elif (len(tokens) == 4 and head[:2] == ['LOCK', 'TABLES'] and tokens[2][0] == 'id'
              and tokens[2][1] in profile and tokens[3] == ('word', 'WRITE')):
            pass
        elif tokens == [('word', 'UNLOCK'), ('word', 'TABLES')]:
            pass
        else:
            raise ValueError('Unsupported or cross-database SQL statement; source SQL was not executed')
    if set(ddl) != set(profile):
        raise ValueError('Source does not contain all 69 reviewed base-table definitions')
    return ddl, rows


def sql_value(value):
    if value is None: return 'NULL'
    if isinstance(value, (int, Decimal)): return str(value)
    if isinstance(value, bytes): return "X'" + value.hex() + "'"
    # Hex transport prevents credentials/text from becoming SQL syntax or commands.
    return "CONVERT(X'" + str(value).encode('utf-8').hex() + "' USING utf8mb4)"


def render_ddl(tokens):
    values = []
    for kind, value in tokens:
        if kind == 'id': value = '`' + value + '`'
        if kind == 'str':
            value = "'" + value.replace('\\', '\\\\').replace("'", "''").replace('\0', '\\0').replace('\n', '\\n').replace('\r', '\\r') + "'"
        values.append(value)
    return ' '.join(values)


def emit_sql(ddl, rows):
    out = ["SET SESSION sql_mode='NO_AUTO_VALUE_ON_ZERO';", 'SET FOREIGN_KEY_CHECKS=0;', 'SET NAMES utf8mb4;']
    for name in ddl:
        out.append('DROP TABLE IF EXISTS `' + name + '`;')
    for name, definition in ddl.items():
        out.append(render_ddl(definition) + ';')
    for name, data in rows.items():
        if data:
            columns = ','.join('`' + column + '`' for column in data[0])
            for row in data:
                out.append('INSERT INTO `' + name + '` (' + columns + ') VALUES (' + ','.join(sql_value(v) for v in row.values()) + ');')
    out.append('SET FOREIGN_KEY_CHECKS=1;')
    return '\n'.join(out) + '\n'


def password_hash(runtime, name, password, salt):
    java = runtime / 'tools/zulu8.96.0.205-ca-jdk8.0.504-macosx_aarch64/Contents/Home/bin/java'
    hashed = command(runtime, [str(java), '-cp', str(runtime / 'fixture-classes'), 'FixturePassword'],
                     input=name + '\n' + password + '\n' + salt + '\n', text=True).strip()
    if not re.fullmatch('[0-9a-f]{16,}', hashed):
        raise RuntimeError('Local password helper did not produce a valid credential')
    return hashed


def compile_password_helper(runtime):
    java = runtime / 'tools/zulu8.96.0.205-ca-jdk8.0.504-macosx_aarch64/Contents/Home/bin/javac'
    (runtime / 'fixture-classes').mkdir(mode=0o700)
    # PasswordUtil uses JDK APIs only; no build cache or foreign compiled classes.
    command(runtime, [str(java), '-d', str(runtime / 'fixture-classes'), str(HERE / 'FixturePassword.java'),
                      str(HERE.parent / 'jeecg-boot-base-common/src/main/java/org/jeecg/common/util/PasswordUtil.java')])


def sanitize(rows, hasher, password):
    original_counts = {table: len(data) for table, data in rows.items()}
    users = sorted(rows['sys_user'], key=lambda row: str(row['id']))
    aliases = {str(row['username']): 'snapshot_user_%03d' % (i + 1) for i, row in enumerate(users)}
    ids = {str(row['id']): 'snapshot_user_%03d' % (i + 1) for i, row in enumerate(users)}
    missing_users = sorted({str(row['user_id']) for table, data in rows.items() if table in RETAIN
                            for row in data if row.get('user_id') and str(row['user_id']) not in ids})
    user_aliases = dict(ids)
    user_aliases.update({value: 'snapshot_missing_user_%03d' % (i + 1) for i, value in enumerate(missing_users)})
    deps = {str(row['id']): 'snapshot_dept_%03d' % (i + 1) for i, row in enumerate(sorted(rows['sys_depart'], key=lambda r: str(r['id'])))}
    # Deleted source classes can leave dangling assignments. Preserve that fact
    # and equality between references, without inventing live class records.
    missing_deps = sorted({value for table, data in rows.items() if table in RETAIN
                           for row in data for key in ('depart_id', 'dep_id', 'dept_id', 'depart_ids', 'work_dept')
                           if row.get(key) for value in str(row[key]).split(',') if value not in deps})
    dep_aliases = dict(deps)
    dep_aliases.update({value: 'snapshot_missing_dept_%03d' % (i + 1) for i, value in enumerate(missing_deps)})
    if len(aliases) != len(users) or any(row['username'] is None for row in users):
        raise ValueError('Source usernames must be present and unique')
    old_hashes = {row[key] for row in users for key in ('password', 'salt') if row[key]}
    personal = {str(row[key]) for row in users for key in USER_CLEAR | {'username', 'realname'} if row.get(key) and len(str(row[key])) >= 3}
    actors = sorted({str(row[key]) for name, data in rows.items() if name in RETAIN for row in data for key in ('create_by', 'update_by') if row.get(key) and str(row[key]) not in aliases and str(row[key]) not in ids})
    actor_map = {value: 'snapshot_actor_%03d' % (i + 1) for i, value in enumerate(actors)}
    def actor(value):
        if not value: return value
        return aliases.get(str(value), ids.get(str(value), actor_map.get(str(value))))
    # Referenced student files stay relationally valid, but bytes are withheld.
    file_ids = {str(row[key]) for row in rows['teaching_work'] for key in ('work_file', 'work_cover') if row.get(key)}
    rows['sys_file'] = [row for row in rows['sys_file'] if str(row['id']) in file_ids]
    for table in rows:
        if table not in RETAIN:
            rows[table] = []
    for table, data in rows.items():
        for index, row in enumerate(data, 1):
            for key in ('create_by', 'update_by'):
                if key in row: row[key] = actor(row[key])
            if 'user_id' in row and row['user_id']:
                row['user_id'] = user_aliases[str(row['user_id'])]
            for key in ('depart_id', 'dep_id', 'dept_id'):
                if row.get(key):
                    row[key] = dep_aliases[str(row[key])]
            for key in ('depart_ids', 'work_dept'):
                if row.get(key):
                    values = str(row[key]).split(',')
                    row[key] = ','.join(dep_aliases[value] for value in values)
            if 'data_rule_ids' in row: row['data_rule_ids'] = None
            if table == 'sys_user':
                row['id'] = ids[str(row['id'])]
                row['username'] = row['id']; row['realname'] = row['id']
                for key in USER_CLEAR: row[key] = '' if key == 'school' else None
                row['activiti_sync'] = 0
                row['salt'] = secrets.token_hex(4)
                row['password'] = hasher(row['username'], password, row['salt'])
            elif table == 'sys_depart':
                row['id'] = deps[str(row['id'])]
                if row['parent_id']:
                    if str(row['parent_id']) not in deps: raise ValueError('Unknown parent department')
                    row['parent_id'] = deps[str(row['parent_id'])]
                row['depart_name'] = row['id']
                for key in DEPART_CLEAR: row[key] = None
            elif table in {'sys_role', 'sys_depart_role'}:
                row['role_name'] = 'snapshot_role_%03d' % index; row['description'] = None
            elif table in {'sys_permission', 'teaching_menu'}:
                row['description'] = None
                for key in ('url', 'redirect'):
                    if row.get(key) and (str(row[key]).startswith(('http:', 'https:', '//'))): row[key] = None
                row['internal_or_external'] = 0
            elif table == 'sys_file':
                suffix = Path(str(row.get('file_name') or row['file_path'])).suffix.lower()
                suffix = suffix if re.fullmatch(r'\.[a-z0-9]{1,8}', suffix) else '.bin'
                row['file_name'] = 'snapshot_file_%03d' % index + suffix
                row['file_path'] = 'snapshot-withheld/' + row['file_name']
                row['file_location'] = 1; row['file_tag'] = None
            elif table == 'teaching_work':
                row['work_name'] = 'snapshot_work_%03d' % index; row['has_cloud_data'] = 0
            elif table == 'teaching_work_correct':
                row['comment'] = 'snapshot_feedback' if row['comment'] else row['comment']
    residual_content = 0
    for table, data in rows.items():
        for row in data:
            for key, value in row.items():
                if value and value in old_hashes:
                    raise ValueError('Production credential survived sanitization')
                if isinstance(value, str):
                    if key in CONTENT_COLUMNS.get(table, set()) or key in RESOURCE_COLUMNS.get(table, set()):
                        residual_content += sum(item in value for item in personal)
                    # Role codes, permission routes, dictionary values, IDs and
                    # foreign keys are business identifiers. Never substring
                    # replace them just because a username happens to overlap.
    return {'source_counts': original_counts, 'retained_counts': {t: len(r) for t, r in rows.items()},
            'users': len(users), 'departments': len(deps), 'historical_actors': len(actors),
            'source_dangling_department_ids': len(missing_deps),
            'source_dangling_user_ids': len(missing_users),
            'cleared_tables': sorted(set(rows) - RETAIN), 'withheld_student_files': len(rows['sys_file']),
            'known_identity_occurrences_in_preserved_content': residual_content,
            'free_text_and_media_fully_anonymous': False}


def safe_relative(value):
    """Require a POSIX local upload reference, including encoded traversal checks."""
    if not isinstance(value, str) or not value or '\\' in value or '\0' in value:
        raise ValueError('Invalid upload path')
    for _ in range(4):
        decoded = unquote(value)
        if decoded == value: break
        value = decoded
    if '%' in value or value.startswith('/') or urlsplit(value).scheme or any(x in {'', '.', '..'} for x in value.split('/')):
        raise ValueError('Absolute, ambiguous or traversing upload path')
    if any(ord(x) < 32 for x in value) or str(PurePosixPath(value)) != value:
        raise ValueError('Unsafe upload path')
    return value


def reference_candidates(value, text_only=False):
    if not value: return []
    value = str(value)
    try:
        obj = json.loads(value)
    except (ValueError, TypeError):
        obj = None
    def walk(item):
        if isinstance(item, str): yield item
        elif isinstance(item, list):
            for child in item: yield from walk(child)
        elif isinstance(item, dict):
            for key, child in item.items():
                if key.lower() in URL_KEYS:
                    yield from walk(child)
    if obj is not None: return list(walk(obj))
    if '<' in value:
        return re.findall(r'(?:src|href|poster)\s*=\s*["\']([^"\']+)', value, re.I)
    return [] if text_only else value.split(',')


def resource_inventory(rows):
    files, external, unsafe = set(), 0, 0
    for table, columns in RESOURCE_COLUMNS.items():
        for row in rows[table]:
            for column in columns:
                for value in reference_candidates(row[column], column in RESOURCE_TEXT_COLUMNS):
                    parts = urlsplit(value)
                    path = parts.path
                    # Resolve only application local-static routes to upFiles.
                    markers = ('/sys/common/static/', '/upFiles/')
                    marker = next((marker for marker in markers if marker in path), None)
                    if marker: path = path.split(marker, 1)[1]
                    elif parts.scheme or parts.netloc:
                        external += 1; continue
                    if not path or path in {'[]', 'null'}: continue
                    try:
                        files.add(safe_relative(path))
                    except ValueError:
                        unsafe += 1
    return {'paths': sorted(files), 'external_references': external, 'unsafe_references': unsafe,
            'scope': 'course, unit and additional-work resource fields; no student file bytes'}


def ordinary_asset(root, relative):
    """Reject every symlink component and any escape before reading an asset."""
    relative = safe_relative(relative)
    item = root
    if item.is_symlink() or not item.is_dir(): raise ValueError('Asset root must be an ordinary directory')
    for component in PurePosixPath(relative).parts:
        item = item / component
        if item.is_symlink(): raise ValueError('Asset symlinks are forbidden')
    if not item.is_file() or item.resolve().relative_to(root.resolve()).as_posix() != relative:
        raise ValueError('Asset is missing or escaped its root')
    return item


def normalize_resources(rows, available):
    """Relocate known app-static URLs only; preserve all other content bytes."""
    count = 0
    attribute = re.compile(r'((?:src|href|poster)\s*=\s*)(["\'])(.*?)(\2)', re.I | re.S)
    def relocate(original, browser_path=False):
        nonlocal count
        path = urlsplit(original).path
        marker = next((m for m in ('/sys/common/static/', '/upFiles/') if m in path), None)
        if marker is None: return original
        try: relative = safe_relative(path.split(marker, 1)[1])
        except ValueError: return original
        if relative not in available: return original
        replacement = ('/api/sys/common/static/' if browser_path else '') + relative
        if replacement != original: count += 1
        return replacement
    for table, columns in RESOURCE_COLUMNS.items():
        for row in rows[table]:
            for column in columns:
                value = row[column]
                if not isinstance(value, str): continue
                if '<' in value:
                    row[column] = attribute.sub(lambda m: m.group(1) + m.group(2) + relocate(m.group(3), True) + m.group(4), value)
                elif column not in RESOURCE_TEXT_COLUMNS:
                    try: obj = json.loads(value)
                    except ValueError: obj = None
                    def walk(item):
                        if isinstance(item, list): return [walk(child) for child in item]
                        if isinstance(item, dict): return {key: relocate(child) if key.lower() in URL_KEYS and isinstance(child, str) else walk(child) for key, child in item.items()}
                        if isinstance(item, str): return relocate(item)
                        return item
                    if obj is not None:
                        replacement = walk(obj)
                        if replacement != obj: row[column] = json.dumps(replacement, ensure_ascii=False, separators=(',', ':'))
                    else:
                        browser_path = column == 'course_video' and row.get('course_video_source') == 2
                        row[column] = ','.join(relocate(item, browser_path) for item in value.split(','))
    return count


def copy_assets(source, runtime, references):
    manifest_path = source / 'assets-manifest.json'
    metadata = json.loads(read_private(manifest_path))
    selected = {}
    for relative in references['paths']:
        record = metadata.get(relative)
        if not isinstance(record, dict) or set(record) != {'bytes', 'sha256'}:
            raise ValueError('Referenced course asset lacks a verified source record')
        if type(record['bytes']) is not int or record['bytes'] < 0 or not re.fullmatch('[0-9a-f]{64}', record['sha256']):
            raise ValueError('Invalid source asset record')
        selected[relative] = record
    if shutil.disk_usage(runtime).free < sum(item['bytes'] for item in selected.values()) + 512 * 1024 * 1024:
        raise ValueError('Insufficient space for independent private course asset copies')
    for relative, record in selected.items():
        original = ordinary_asset(source / 'uploads', relative)
        if original.stat().st_size != record['bytes'] or sha256(original) != record['sha256']:
            raise ValueError('Source asset differs from acquisition manifest')
        destination = runtime / 'uploads' / relative
        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if destination.exists(): raise ValueError('Asset destination already exists')
        shutil.copyfile(original, destination); destination.chmod(0o600)
        if sha256(destination) != record['sha256']:
            raise ValueError('Copied asset differs from source manifest')
    return {'source_manifest_sha256': sha256(manifest_path), 'files': selected,
            'count': len(selected), 'bytes': sum(x['bytes'] for x in selected.values()),
            'student_files_copied': False, 'atomic_with_database': False}


def assert_redis_owner(runtime):
    credentials = json.loads(read_private(runtime / 'config/credentials.json'))
    redis = [str(runtime / 'tools/redis-7.2.9/src/redis-cli'), '-h', '127.0.0.1', '-p', str(load_ports(runtime)['redis']), '--raw']
    env = dict(os.environ, REDISCLI_AUTH=credentials['redis_password'])
    if command(runtime, redis + ['CONFIG', 'GET', 'dir'], text=True, env=env).strip().splitlines() != ['dir', str(runtime / 'redis-data')]:
        raise ValueError('Redis instance is not owned by this runtime')
    if command(runtime, redis + ['CONFIG', 'GET', 'bind'], text=True, env=env).strip().splitlines() != ['bind', '127.0.0.1']:
        raise ValueError('Redis is not bound to loopback')


def verify(runtime):
    runtime = local_path(runtime)
    manifest_path = runtime / 'snapshot-manifest.json'
    manifest = json.loads(read_private(manifest_path))
    if (manifest.get('format') != FORMAT or manifest.get('kind') != KIND or manifest.get('complete') is not True
            or manifest.get('runtime') != str(runtime) or manifest.get('ports') != load_ports(runtime)
            or manifest.get('datadir') != str(runtime / 'mysql-data')):
        raise ValueError('Incomplete or mismatched private production fixture manifest')
    if (any(not isinstance(manifest.get(key), str) or not re.fullmatch('[0-9a-f]{64}', manifest[key])
            for key in ('source_sha256', 'source_manifest_sha256', 'schema_policy_sha256'))
            or manifest['schema_policy_sha256'] != sha256(SCHEMA_PROFILE)
            or type(manifest.get('source_bytes')) is not int or manifest['source_bytes'] <= 0):
        raise ValueError('Missing source binding or changed reviewed schema policy')
    assert_mysql_owner(runtime); assert_app_config(runtime); assert_redis_owner(runtime)
    credentials = json.loads(read_private(runtime / 'config/credentials.json'))
    expected_config = (HERE / 'application-localtest.properties.template').read_text()
    config_values = {'RUNTIME': str(runtime), 'MYSQL_APP_PASSWORD': credentials['mysql_app_password'],
                     'REDIS_PASSWORD': credentials['redis_password']}
    config_values.update({key.upper() + '_PORT': str(port) for key, port in load_ports(runtime).items()})
    for key, value in config_values.items(): expected_config = expected_config.replace('@' + key + '@', value)
    if read_private(runtime / 'config/application-localtest.properties').decode() != expected_config:
        raise ValueError('Snapshot application configuration differs from the isolated local profile')
    for name, digest in manifest['private_files'].items():
        if name not in {'config/application-localtest.properties', 'config/mysql.cnf', 'config/credentials.json',
                        'config/snapshot-app-client.cnf', 'snapshot-accounts.json', 'resource-references.json',
                        'sanitized.sql', 'assets-result.json'}:
            raise ValueError('Manifest contains an unexpected private file')
        read_private(runtime / name)
        if sha256(runtime / name) != digest: raise ValueError('Private fixture file differs from manifest')
    if sql(runtime, 'SELECT @@local_infile') != '0': raise ValueError('LOCAL INFILE must remain disabled')
    grants = sql(runtime, "SHOW GRANTS FOR 'teaching_dev'@'127.0.0.1'").splitlines()
    if len(grants) != 2 or 'GRANT USAGE ON *.*' not in grants[0] or 'ON `teachingopen_dev`.*' not in grants[1] or 'GRANT OPTION' in grants[1]:
        raise ValueError('Application user escaped database-scoped privileges')
    actual = database_inventory(runtime)
    if actual != manifest['database']: raise ValueError('Database differs from the sanitized manifest; do not start application')
    account = sql(runtime, "SELECT COUNT(*),COALESCE(SUM(username REGEXP '^snapshot_user_[0-9]{3}$' AND id=username AND realname=username AND school='' AND avatar IS NULL AND birthday IS NULL AND sex IS NULL AND email IS NULL AND phone IS NULL AND third_id IS NULL AND third_type IS NULL AND work_no IS NULL AND post IS NULL AND telephone IS NULL),0) FROM teachingopen_dev.sys_user")
    expected = str(manifest['sanitization']['users'])
    if account != expected + '\t' + expected: raise ValueError('Unexpected or identifiable snapshot account')
    for table in manifest['sanitization']['cleared_tables']:
        if actual[table]['rows'] != 0: raise ValueError('Cleared operational table contains rows')
    assets = json.loads(read_private(runtime / 'assets-result.json'))
    for relative, record in assets['files'].items():
        item = ordinary_asset(runtime / 'uploads', relative)
        if item.stat().st_size != record['bytes'] or sha256(item) != record['sha256']:
            raise ValueError('Runtime course asset differs from verified private copy')
    return {'verified': True, 'runtime': str(runtime), 'tables': len(actual), 'users': int(expected),
            'courses': actual['teaching_course']['rows'], 'units': actual['teaching_course_unit']['rows'],
            'works': actual['teaching_work']['rows'], 'manifest_sha256': sha256(manifest_path),
            'application_started': False, 'business_verified': False, 'assets_verified': True,
            'course_asset_count': assets['count'], 'course_asset_bytes': assets['bytes']}


def create(source, runtime, tools, ports):
    source, runtime = local_path(source), local_path(runtime, new=True)
    validate_ports(ports)
    dump = read_private(source / 'teachingopen.sql')
    source_meta_bytes = read_private(source / 'source-manifest.json')
    source_meta = json.loads(source_meta_bytes)
    digest = hashlib.sha256(dump).hexdigest()
    if source_meta.get('sha256') != digest or source_meta.get('bytes') != len(dump):
        raise ValueError('Raw source bytes differ from the acquisition manifest')
    ddl, rows = parse_dump(dump.decode('utf-8'))
    spec = importlib.util.spec_from_file_location('prepare_production_fixture', HERE / 'prepare-local.py')
    prepare = importlib.util.module_from_spec(spec); spec.loader.exec_module(prepare)
    # Only a new runtime is accepted; repository-owned schema preparation is trusted.
    prepare.prepare(runtime, Path(tools).resolve(), ports, seed_fixtures=False)
    assert_mysql_owner(runtime); assert_app_config(runtime)
    credentials = json.loads(read_private(runtime / 'config/credentials.json'))
    (runtime / 'config/mysql.cnf').write_text((runtime / 'config/mysql.cnf').read_text() + 'local-infile=OFF\n')
    sql(runtime, 'SET GLOBAL local_infile=OFF;')
    sql(runtime, "REVOKE ALL PRIVILEGES, GRANT OPTION FROM 'teaching_dev'@'127.0.0.1'; GRANT SELECT,INSERT,UPDATE,DELETE,CREATE,DROP,INDEX,ALTER,REFERENCES ON teachingopen_dev.* TO 'teaching_dev'@'127.0.0.1';")
    compile_password_helper(runtime)
    summary = sanitize(rows, lambda name, password, salt: password_hash(runtime, name, password, salt), credentials['test_user_password'])
    resources = resource_inventory(rows)
    assets = copy_assets(source, runtime, resources)
    summary['normalized_app_static_references'] = normalize_resources(rows, set(assets['files']))
    resources = resource_inventory(rows)
    private_write(runtime / 'assets-result.json', json.dumps(assets, ensure_ascii=False, indent=2) + '\n')
    private_write(runtime / 'resource-references.json', json.dumps(resources, ensure_ascii=False, indent=2) + '\n')
    private_write(runtime / 'sanitized.sql', emit_sql(ddl, rows))
    private_write(runtime / 'config/snapshot-app-client.cnf', '[client]\nuser=teaching_dev\nhost=127.0.0.1\nprotocol=tcp\nport=' + str(ports['mysql']) + '\npassword=' + credentials['mysql_app_password'] + '\n')
    client = [str(runtime / 'tools/mysql-8.4.6-macos15-arm64/bin/mysql'),
              '--defaults-extra-file=' + str(runtime / 'config/snapshot-app-client.cnf'),
              '--local-infile=0', '--binary-mode', '--default-character-set=utf8mb4', 'teachingopen_dev']
    command(runtime, client, input=(runtime / 'sanitized.sql').read_bytes())
    accounts = []
    for row in rows['sys_user']:
        accounts.append({'id': row['id'], 'username': row['username'], 'status': int(row['status']) if row['status'] is not None else None,
                         'role_ids': [r['role_id'] for r in rows['sys_user_role'] if r['user_id'] == row['id']],
                         'department_ids': [r['dep_id'] for r in rows['sys_user_depart'] if r['user_id'] == row['id']]})
    private_write(runtime / 'snapshot-accounts.json', json.dumps(accounts, indent=2) + '\n')
    database = database_inventory(runtime)
    if any(database[name]['rows'] != count for name, count in summary['retained_counts'].items()):
        raise RuntimeError('Sanitized import row counts do not match parsed source')
    names = ('config/application-localtest.properties', 'config/mysql.cnf', 'config/credentials.json',
             'config/snapshot-app-client.cnf', 'snapshot-accounts.json', 'resource-references.json', 'sanitized.sql', 'assets-result.json')
    manifest = {'format': FORMAT, 'kind': KIND, 'complete': True, 'runtime': str(runtime), 'datadir': str(runtime / 'mysql-data'),
                'ports': ports, 'source_sha256': digest, 'source_bytes': len(dump),
                'source_manifest_sha256': hashlib.sha256(source_meta_bytes).hexdigest(),
                'schema_policy_sha256': sha256(SCHEMA_PROFILE), 'database': database, 'sanitization': summary,
                'private_files': {name: sha256(runtime / name) for name in names},
                'asset_consistency': 'database transaction snapshot and asset copy are not atomic',
                'assets_verified': True, 'student_attachments': 'withheld; not copied', 'redis_sessions_restored': False,
                'application_started': False, 'business_verified': False,
                'remaining_gates': ['root review of sanitization and preserved free text', 'separate snapshot backend start method', 'real login and business checks']}
    private_write(runtime / 'snapshot-manifest.json', json.dumps(manifest, indent=2) + '\n')
    result = verify(runtime)
    private_write(runtime / 'snapshot-result.json', json.dumps(result, indent=2) + '\n')
    return result
