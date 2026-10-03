"""Opt-in, cold-application UI fixtures layered on the unchanged five-account seed.

Only a fresh role-flow-* runtime is accepted. This module does not start services,
log in, retrieve captchas, or read production data. SQL comes from fixed fixture
records; the original seed is parsed for comparison and is never executed.
"""
from collections import defaultdict
from decimal import Decimal, InvalidOperation
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import socket
import struct
import time
import zlib

from local_recovery import command, database_inventory, file_inventory, local_path, private_write, sha256, sql
from local_runtime import assert_app_config, assert_database, assert_mysql_owner, load_ports
from production_fixture import lex, literal, split_groups, sql_value, statements

HERE = Path(__file__).resolve().parent
SCHEMA_SOURCE = HERE.parent / 'db/teachingopen2.8.sql'
FORMAT = 1
MANIFEST = 'role-flow-manifest.json'
STARTED = 'role-flow-seed.started.json'
ACCOUNT_ROLES = {'fixture_admin': 'admin', 'fixture_teacher_a': 'teacher',
                 'fixture_teacher_b': 'teacher', 'fixture_student_a': 'student',
                 'fixture_student_b': 'student'}
# Existing API/production-copy environments are not opt-in targets.
EXCLUDED_PORTS = {13306, 16379, 18091, 18092, 18101, 18102, 18111, 18112, 18141, 18142}
COPIED_ASSETS = {
    'lesson.mp4': 'a13e04078b6d1a7aa52bec79aea4a8beeec7d5911d88c02931df84180b363dd0',
    'starter.sb3': '94b92bf01ca353f9853a56a027fe3351b6e64883b7e301a6f0e46f0fd05990d2',
    'starter.sjr': '3db97173b9436df3ce8deacacbf3dd46ac60467044ea1650b14f7d250bf88147',
}
# Records are ordinary backend permission registrations, not frontend overrides.
ROUTES = (
    ('center', '个人中心', '/account/center', 'account/center/Index', ('admin', 'teacher', 'student'), False),
    ('mine_work', '我的作品', '/account/mineWork', 'account/center/MineWorkList', ('admin', 'teacher', 'student'), False),
    ('mine_course', '我的课程', '/teaching/mineCourse/cardList', 'account/course/CourseListCard', ('admin', 'teacher', 'student'), False),
    ('unit_card', '课程单元', '/teaching/mineCourse/courseUnitCard', 'account/course/CourseUnitListCard', ('admin', 'teacher', 'student'), True),
    ('my_task', '我的班级作业', '/center/myAdditionalWork', 'account/course/MyAdditionalWorkList', ('student',), False),
    ('work_list', '学生作业批改', '/teaching/workList', 'teaching/TeachingWorkList', ('teacher', 'admin'), False),
    ('task_list', '布置班级作业', '/work/additionalWork', 'teaching/TeachingAdditionalWorkList', ('teacher', 'admin'), False),
    ('course_list', '课程包管理', '/course/course', 'teaching/TeachingCourseList', ('admin',), False),
    ('unit_list', '课程单元管理', '/course/courseUnit', 'teaching/TeachingCourseUnitList', ('admin',), False),
    ('users', '用户管理', '/isystem/user', 'system/UserList', ('admin',), False),
    ('classes', '班级管理', '/isystem/departDetailList', 'system/DepartList', ('admin',), False),
)
DICT_ITEMS = {
    'work_type': [('0', '文件'), ('1', 'Scratch'), ('2', 'Scratch 3'), ('3', 'ScratchJr'), ('4', 'Python')],
    'work_status': [('0', '草稿'), ('1', '已提交'), ('2', '已批改'), ('3', '公开展示'), ('4', '精选')],
    'course_type': [('1', '合成实验课程')],
    'course_category': [('1', '编程实践')],
    'additional_work_status': [('0', '未发布'), ('1', '已发布')],
    'activiti_sync': [('0', '不同步'), ('1', '同步')],
    'sex': [('0', '未知'), ('1', '男'), ('2', '女')],
    'user_status': [('1', '正常'), ('2', '冻结')],
    'yn': [('0', '否'), ('1', '是')],
}


def ident(name):
    if not re.fullmatch('[A-Za-z0-9_]+', name):
        raise ValueError('Unexpected fixture SQL identifier')
    return '`' + name + '`'


def normalized_type(value):
    value = re.sub(r'\b(tinyint|smallint|mediumint|int|integer|bigint)\(\d+\)', r'\1', value.lower())
    return ' '.join(value.split())


def schema_model(source=None):
    """Read only CREATE definitions using the existing quote-aware extractor."""
    spec = importlib.util.spec_from_file_location('role_flow_extract', HERE / 'extract-schema.py')
    extractor = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(extractor)
    schema = extractor.extract_schema(SCHEMA_SOURCE.read_text() if source is None else source)
    result = {}
    for tokens in statements(lex(schema)):
        if tokens[:2] != [('word', 'CREATE'), ('word', 'TABLE')]:
            continue
        name = tokens[2][1]
        depth, end = 1, 4
        while depth:
            if tokens[end] == ('sym', '('): depth += 1
            if tokens[end] == ('sym', ')'): depth -= 1
            end += 1
        columns = {}
        for group in split_groups(tokens[4:end - 1]):
            if group[0][0] != 'id': continue
            column, data_type, pos = group[0][1], group[1][1].lower(), 2
            if pos < len(group) and group[pos] == ('sym', '('):
                closing = group.index(('sym', ')'), pos)
                data_type += ''.join(t[1] for t in group[pos:closing + 1])
                pos = closing + 1
            for modifier in ('UNSIGNED', 'ZEROFILL'):
                if pos < len(group) and group[pos][0] == 'word' and group[pos][1].upper() == modifier:
                    data_type += ' ' + modifier.lower(); pos += 1
            default = None
            if ('word', 'DEFAULT') in group:
                default = literal(group[group.index(('word', 'DEFAULT')) + 1])
            nullable = not any(group[i:i + 2] == [('word', 'NOT'), ('word', 'NULL')] for i in range(len(group)))
            columns[column] = {'type': normalized_type(data_type), 'nullable': nullable, 'default': default}
        result[name] = columns
    if len(result) != 69:
        raise ValueError('Expected the reviewed 69-table source schema')
    return result


def base_records():
    """Exact unchanged seed values, except its locally randomized password/salt."""
    rows = defaultdict(list)
    def add(table, **fields): rows[table].append(fields)
    for role in ('admin', 'teacher', 'student'):
        add('sys_role', id='fixture_role_' + role, role_code=role, role_name='测试' + role)
    add('sys_depart', id='fixture_school', parent_id='', depart_name='合成测试学校', org_code='A99', org_category='1', org_type='1', status='1', del_flag='0')
    for suffix in ('a', 'b'):
        add('sys_depart', id='fixture_class_' + suffix, parent_id='fixture_school', depart_name='合成测试班' + suffix, org_code='A99A0' + ('1' if suffix == 'a' else '2'), org_category='2', org_type='2', status='1', del_flag='0')
    for name, role in ACCOUNT_ROLES.items():
        suffix = '' if role == 'admin' else name[-1]
        depart = 'fixture_class_' + suffix if suffix else 'fixture_school'
        add('sys_user', id=name, username=name, realname='合成测试' + role + suffix, password=None, salt=None, status=1, del_flag=0, user_identity=2 if role != 'student' else 1, depart_ids=depart if role != 'student' else '')
        add('sys_user_role', id='role_' + name, user_id=name, role_id='fixture_role_' + role)
        add('sys_user_depart', ID='dept_' + name, user_id=name, dep_id=depart)
    for suffix in ('a', 'b'):
        filename = 'fixture-work-' + suffix + '.txt'
        add('teaching_course', id='fixture_course_' + suffix, course_name='合成测试课程' + suffix, course_desc='仅用于本地验收', show_home=1, is_shared=0, depart_ids='fixture_school', course_type='1', course_category='1')
        add('teaching_course_dept', id='fixture_assignment_' + suffix, dept_id='fixture_class_' + suffix, course_id='fixture_course_' + suffix, open_time='2026-01-01 00:00:00')
        add('teaching_course_unit', id='fixture_unit_' + suffix, course_id='fixture_course_' + suffix, unit_name='合成单元' + suffix, unit_intro='仅用于本地验收', course_video='[]', course_work_type=1, course_work='合成作业题目' + suffix, course_plan='仅教师可见的教案' + suffix, show_course_plan=0)
        add('sys_file', id='fixture_file_' + suffix, file_name=filename, file_path=filename, file_location=1, file_type=0, create_by='fixture_student_' + suffix)
        add('teaching_additional_work', id='fixture_additional_' + suffix, work_name='合成附加作业' + suffix, work_dept='fixture_class_' + suffix, status=1, code_type=0)
        add('teaching_work', id='fixture_work_' + suffix, user_id='fixture_student_' + suffix, depart_id='fixture_class_' + suffix, course_id='fixture_unit_' + suffix, work_name='合成作业' + suffix, work_type='1', work_file='fixture_file_' + suffix, create_by='fixture_student_' + suffix, create_time='2026-10-02 20:00:00', work_scene='course')
    return dict(rows)


def parse_original_seed(data):
    """Scalar INSERT comparison only. Never send this private file to MySQL."""
    rows = defaultdict(list)
    parsed = list(statements(lex(data)))
    if not parsed or parsed[0] != [('word', 'START'), ('word', 'TRANSACTION')] or parsed[-1] != [('word', 'COMMIT')]:
        raise ValueError('Original seed lacks its exact transaction envelope')
    for tokens in parsed[1:-1]:
        if tokens[:2] != [('word', 'INSERT'), ('word', 'INTO')] or tokens[2][0] != 'id' or tokens[3] != ('sym', '('):
            raise ValueError('Original seed contains unexpected SQL')
        closing = tokens.index(('sym', ')'), 4)
        names = split_groups(tokens[4:closing])
        if any(len(n) != 1 or n[0][0] != 'id' for n in names):
            raise ValueError('Original seed has unsupported column syntax')
        names = [n[0][1] for n in names]
        if len(set(names)) != len(names) or tokens[closing + 1:closing + 3] != [('word', 'VALUES'), ('sym', '(')] or tokens[-1] != ('sym', ')'):
            raise ValueError('Original seed has unexpected INSERT structure')
        values = split_groups(tokens[closing + 3:-1])
        if len(values) != len(names) or any(len(v) != 1 for v in values):
            raise ValueError('Original seed expressions or row count are forbidden')
        rows[tokens[2][1]].append(dict(zip(names, [literal(v[0]) for v in values])))
    expected = base_records()
    if set(rows) != set(expected): raise ValueError('Original seed has unknown or missing tables')
    for table, data in rows.items():
        key = 'ID' if table == 'sys_user_depart' else 'id'
        by_id = {r[key]: r for r in data}
        if len(by_id) != len(data) or set(by_id) != {r[key] for r in expected[table]}:
            raise ValueError('Original seed has unknown, duplicated, or missing fixture rows: ' + table)
        for record in expected[table]:
            actual = dict(by_id[record[key]])
            if table == 'sys_user':
                salt, password = actual.get('salt'), actual.get('password')
                length = ((len(record['username'].encode()) // 8) + 1) * 16
                if not isinstance(salt, str) or not re.fullmatch('[0-9a-f]{8}', salt) or not isinstance(password, str) or not re.fullmatch('[0-9a-f]{' + str(length) + '}', password):
                    raise ValueError('Original seed has unexpected synthetic credential format')
                actual['salt'] = actual['password'] = None
            if set(actual) != set(record) or any(str(actual[k]) != str(v) for k, v in record.items()):
                raise ValueError('Original seed differs from the standard fixture: ' + table)
    return dict(rows)


def numeric_type(column):
    return column['type'].split('(')[0].split()[0] in {'int', 'tinyint', 'smallint', 'mediumint', 'bigint', 'integer', 'decimal', 'double', 'float'}


def equivalent(actual, expected, column):
    if actual is None or expected is None: return actual is None and expected is None
    try:
        return Decimal(actual) == Decimal(expected) if numeric_type(column) else str(actual) == str(expected)
    except (InvalidOperation, TypeError):
        return False


def complete_records(model, records):
    result = {table: [] for table in model}
    for table, data in records.items():
        if table not in model: raise ValueError('Unreviewed fixture table')
        for fields in data:
            if not set(fields) <= set(model[table]): raise ValueError('Unreviewed fixture column')
            row = {name: column['default'] for name, column in model[table].items()}
            row.update(fields)
            if any(row[n] is None and not c['nullable'] for n, c in model[table].items()):
                raise ValueError('Missing required synthetic field: ' + table)
            result[table].append(row)
    return result


def compare_records(model, actual, expected):
    if set(actual) != set(model) or set(expected) != set(model):
        raise ValueError('Unknown or missing database tables')
    for table, columns in model.items():
        data, desired = actual[table], expected[table]
        if len(data) != len(desired): raise ValueError('Runtime has unknown or missing rows: ' + table)
        if not desired: continue
        key = 'ID' if table == 'sys_user_depart' else 'id'
        by_id = {r.get(key): r for r in data}
        if len(by_id) != len(data) or set(by_id) != {r[key] for r in desired}:
            raise ValueError('Runtime has unknown or duplicated fixture IDs: ' + table)
        for row in desired:
            found = by_id[row[key]]
            if set(found) != set(columns) or any(not equivalent(found[n], row[n], c) for n, c in columns.items()):
                raise ValueError('Runtime row differs from the permitted cold fixture: ' + table)


def read_database(runtime, model):
    metadata = sql(runtime, "SELECT TABLE_NAME,HEX(COLUMN_NAME),HEX(COLUMN_TYPE),IS_NULLABLE,IFNULL(HEX(COLUMN_DEFAULT),'~') FROM information_schema.columns WHERE TABLE_SCHEMA='teachingopen_dev' ORDER BY TABLE_NAME,ORDINAL_POSITION")
    found = defaultdict(dict)
    for line in metadata.splitlines():
        table, name, kind, nullable, default = line.split('\t')
        found[table][bytes.fromhex(name).decode()] = {'type': normalized_type(bytes.fromhex(kind).decode()), 'nullable': nullable == 'YES', 'default': None if default == '~' else bytes.fromhex(default).decode()}
    if set(found) != set(model): raise ValueError('Runtime has unknown or missing schema tables')
    for table, columns in model.items():
        if list(found[table]) != list(columns): raise ValueError('Runtime has changed or new columns: ' + table)
        for name, c in columns.items():
            actual = found[table][name]
            if actual['type'] != c['type'] or actual['nullable'] != c['nullable'] or not equivalent(actual['default'], c['default'], c):
                raise ValueError('Runtime column type/default differs from the reviewed schema: ' + table)
    engines = sql(runtime, "SELECT COUNT(*) FROM information_schema.tables WHERE TABLE_SCHEMA='teachingopen_dev' AND (TABLE_TYPE<>'BASE TABLE' OR ENGINE<>'InnoDB')")
    objects = sql(runtime, "SELECT (SELECT COUNT(*) FROM information_schema.triggers WHERE TRIGGER_SCHEMA='teachingopen_dev')+(SELECT COUNT(*) FROM information_schema.routines WHERE ROUTINE_SCHEMA='teachingopen_dev')+(SELECT COUNT(*) FROM information_schema.events WHERE EVENT_SCHEMA='teachingopen_dev')")
    if engines != '0' or objects != '0': raise ValueError('Unreviewed engine or database object')
    rows = {}
    for table, columns in model.items():
        expression = ','.join("IFNULL(HEX(CAST(" + ident(n) + " AS BINARY)),'~')" for n in columns)
        output = sql(runtime, "SELECT 'ROW'," + expression + ' FROM teachingopen_dev.' + ident(table))
        rows[table] = [dict(zip(columns, [None if v == '~' else bytes.fromhex(v).decode() for v in line.split('\t')[1:]])) for line in output.splitlines()]
    return rows


def generated_assets():
    result = {}
    for name, digest in COPIED_ASSETS.items():
        path = HERE / 'role-flow-assets' / name
        if path.is_symlink() or sha256(path) != digest:
            raise ValueError('Self-authored fixture asset changed: ' + name)
        result[name] = path.read_bytes()
    def chunk(tag, payload):
        return struct.pack('!I', len(payload)) + tag + payload + struct.pack('!I', zlib.crc32(tag + payload) & 0xffffffff)
    width, height = 320, 180
    result['cover.png'] = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('!2I5B', width, height, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress((b'\x00' + bytes([90, 155, 170]) * width) * height)) + chunk(b'IEND', b'')
    result['starter.py'] = b'print("Role flow practice")\nprint(6 * 7)\n'
    result['learning-notes.txt'] = '合成学习资料：观看视频，再修改项目并保存；所有素材均为自制。\n'.encode()
    result['teacher-plan.txt'] = '合成教案：检查学生真实修改、保存与重新打开，然后给出反馈。\n'.encode()
    result['submission.txt'] = '合成提交材料：我完成了观看、编辑、保存和重新打开。\n'.encode()
    return result


def ui_records(assets):
    rows = defaultdict(list)
    def add(table, **fields): rows[table].append(fields)
    for index, (key, title, url, component, roles, hidden) in enumerate(ROUTES):
        permission = 'fixture_ui_' + key
        add('sys_permission', id=permission, parent_id='', name=title, url=url, component=component,
            menu_type=0, sort_no=index + 1, is_route=1, is_leaf=1, keep_alive=0,
            hidden=int(hidden), del_flag=0, status='1', internal_or_external=0)
        for role in roles:
            add('sys_role_permission', id='fixture_ui_rp_' + role[0] + '_' + key,
                role_id='fixture_role_' + role, permission_id=permission)
    for code in ('edit', 'status'):
        permission = 'fixture_ui_user_' + code
        add('sys_permission', id=permission, parent_id='fixture_ui_users', name='用户' + code,
            menu_type=2, perms='user:' + code, perms_type='1', is_route=0, is_leaf=1,
            del_flag=0, status='1', hidden=0)
        add('sys_role_permission', id='fixture_ui_rp_user_' + code, role_id='fixture_role_admin', permission_id=permission)
    add('sys_fill_rule', id='fixture_ui_org_rule', rule_name='合成班级机构编码', rule_code='org_num_role',
        rule_class='org.jeecg.modules.system.rule.OrgCodeRule', rule_params='{}')
    for index, (code, items) in enumerate(DICT_ITEMS.items()):
        dictionary = 'fixture_ui_dict_' + str(index)
        add('sys_dict', id=dictionary, dict_name=code, dict_code=code, del_flag=0, type=0)
        for number, (value, label) in enumerate(items):
            add('sys_dict_item', id='fixture_ui_di_' + str(index) + '_' + str(number), dict_id=dictionary,
                item_text=label, item_value=value, sort_order=number, status=1)
    for index, name in enumerate(sorted(assets)):
        add('sys_file', id='fixture_ui_file_' + str(index), file_name=name, file_path='role-flow/' + name,
            file_location=1, file_type=2, create_by='fixture_admin', del_flag=0)
    add('teaching_course', id='fixture_ui_course', course_name='三角色编程实践（自制夹具）',
        course_desc='合成验收课程：学生学习与创作、教师批改、管理员维护。', course_cover='role-flow/cover.png',
        show_type=2, show_home=1, is_shared=0, depart_ids='fixture_school', course_type='1', course_category='1', del_flag=0)
    add('teaching_course_dept', id='fixture_ui_assignment', dept_id='fixture_class_a', course_id='fixture_ui_course', open_time='2026-01-01 00:00:00')
    for index, (engine, kind, extension) in enumerate((('Scratch', 2, 'sb3'), ('ScratchJr', 3, 'sjr'), ('Python', 4, 'py'))):
        add('teaching_course_unit', id='fixture_ui_unit_' + extension, course_id='fixture_ui_course',
            unit_name=engine + '：编辑、保存与反馈', unit_intro='先播放与拖动自制视频，再完成真实项目修改。',
            unit_cover='role-flow/cover.png', course_video='role-flow/lesson.mp4', course_video_source=1,
            show_course_video=1, course_case='role-flow/starter.' + extension, show_course_case=1,
            course_ppt='role-flow/learning-notes.txt', show_course_ppt=1, course_work_type=kind,
            course_work='role-flow/starter.' + extension, course_plan='role-flow/teacher-plan.txt', show_course_plan=0,
            media_content='<h2>合成编程练习</h2><p>观看 10 秒视频并尝试拖动进度条。修改项目，保存后关闭编辑器，再从我的作品重新打开，确认修改仍存在，最后提交。</p>',
            del_flag=0, order_num=index + 1)
    add('teaching_additional_work', id='fixture_ui_task', work_name='三角色反馈练习（文件提交）',
        work_desc='<p>提交自制材料，等待教师给出零分与具体评语，然后重新打开查看。</p><p><a href="/api/sys/common/static/role-flow/submission.txt">下载自制提交示例</a></p>',
        work_cover='role-flow/cover.png', work_document_url='role-flow/learning-notes.txt',
        work_dept='fixture_class_a', status=1, code_type=0, create_by='fixture_teacher_a')
    return dict(rows)


def expected_after(model, original, additions):
    combined = {t: [dict(r) for r in data] for t, data in original.items()}
    for row in combined['sys_depart']:
        if row['id'] in {'fixture_class_a', 'fixture_class_b'}: row['org_category'] = '3'
    for table, data in additions.items(): combined.setdefault(table, []).extend(data)
    return complete_records(model, combined)


def fixture_sql(additions):
    out = ['SET NAMES utf8mb4;', 'SET SESSION sql_mode=\'STRICT_TRANS_TABLES,NO_ENGINE_SUBSTITUTION\';', 'START TRANSACTION;']
    for name in ('fixture_class_a', 'fixture_class_b'):
        out.append('UPDATE `sys_depart` SET `org_category`=' + sql_value('3') + ' WHERE `id`=' + sql_value(name) + ';')
    for table, data in additions.items():
        for row in data:
            out.append('INSERT INTO ' + ident(table) + ' (' + ','.join(ident(n) for n in row) + ') VALUES (' + ','.join(sql_value(v) for v in row.values()) + ');')
    return '\n'.join(out + ['COMMIT;', ''])


def private_file(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o077:
        raise ValueError('Expected an ordinary private runtime file')
    return path


def isolation_files(runtime, ports):
    credentials = json.loads(private_file(runtime / 'config/credentials.json').read_text())
    if set(credentials) != {'mysql_root_password', 'mysql_app_password', 'redis_password', 'test_user_password'} or any(not isinstance(v, str) or not re.fullmatch('[0-9a-f]{40}', v) for v in credentials.values()):
        raise ValueError('Unexpected fresh local credential metadata')
    template = (HERE / 'application-localtest.properties.template').read_text()
    values = {'RUNTIME': str(runtime), 'MYSQL_APP_PASSWORD': credentials['mysql_app_password'], 'REDIS_PASSWORD': credentials['redis_password']}
    values.update({key.upper() + '_PORT': str(value) for key, value in ports.items()})
    for name, value in values.items(): template = template.replace('@' + name + '@', value)
    # Include external-service/loopback settings, not only the JDBC prefix.
    if private_file(runtime / 'config/application-localtest.properties').read_text() != template:
        raise ValueError('Dedicated runtime must use the unchanged isolated localtest profile')
    expected_client = '[client]\nuser=root\nhost=127.0.0.1\nport=' + str(ports['mysql']) + '\nprotocol=tcp\npassword=' + credentials['mysql_root_password'] + '\n'
    if private_file(runtime / 'config/mysql-admin-client.cnf').read_text() != expected_client:
        raise ValueError('Unexpected local admin client configuration')
    return credentials


def cold_runtime(path, creating=False):
    runtime = local_path(path)
    if not re.fullmatch(r'role-flow-[A-Za-z0-9_-]+', runtime.name):
        raise ValueError('Use a new dedicated role-flow-* runtime')
    for name in ('config', 'uploads', 'mysql-data', 'logs'):
        item = runtime / name
        if item.is_symlink() or not item.is_dir() or item.resolve() != item or item.stat().st_mode & 0o077:
            raise ValueError('Runtime directories must be ordinary private local directories')
    private_file(runtime / 'ports.json')
    ports = load_ports(runtime)
    if set(ports.values()) & EXCLUDED_PORTS: raise ValueError('Dedicated runtime must not reuse existing application ports')
    private_file(runtime / 'config/mysql-admin-client.cnf')
    private_file(runtime / 'config/credentials.json')
    private_file(runtime / 'config/application-localtest.properties')
    isolation_files(runtime, ports)
    assert_app_config(runtime)
    assert_mysql_owner(runtime)
    assert_database(runtime)
    for name in ('backend', 'frontend'):
        with socket.socket() as probe:
            probe.settimeout(0.5)
            if probe.connect_ex(('127.0.0.1', ports[name])) == 0:
                raise ValueError('Stop the dedicated application and frontend before fixture creation/initial verification')
    if any((runtime / name).exists() or (runtime / name).is_symlink() for name in ('backend.pid', 'backend-process.json', 'frontend.pid', 'frontend-process.json')):
        raise ValueError('This tool requires a runtime whose application has never started')
    if creating and any((runtime / name).exists() or (runtime / name).is_symlink() for name in (MANIFEST, STARTED, 'role-flow-app-client.cnf')):
        raise ValueError('Fixture creation is one-shot; an existing/incomplete target is never overwritten')
    return runtime


def baseline(runtime, model):
    seed = private_file(runtime / 'config/fixture-seed.sql')
    original = parse_original_seed(seed.read_text())
    accounts = json.loads((runtime / 'fixture-accounts.json').read_text())
    expected_accounts = {name: {'id': name, 'role': role, 'class_id': 'fixture_school' if role == 'admin' else 'fixture_class_' + name[-1]} for name, role in ACCOUNT_ROLES.items()}
    if accounts != expected_accounts: raise ValueError('Fixture account metadata differs from the exact five accounts')
    compare_records(model, read_database(runtime, model), complete_records(model, original))
    inventory = file_inventory(runtime / 'uploads')
    expected_files = {f'fixture-work-{s}.txt': {'bytes': len(('synthetic work ' + s + '\n').encode()), 'sha256': hashlib.sha256(('synthetic work ' + s + '\n').encode()).hexdigest()} for s in ('a', 'b')}
    if inventory != expected_files: raise ValueError('Uploads contain unknown, modified, or missing baseline attachments')
    return original, inventory


def source_fingerprints():
    return {name: sha256(HERE / name) for name in ('role_flow_fixture.py', 'seed-role-flows.py', 'seed-fixtures.py', 'extract-schema.py', 'production_fixture.py', 'application-localtest.properties.template')} | {'teachingopen2.8.sql': sha256(SCHEMA_SOURCE)}


def create(path):
    runtime = cold_runtime(path, creating=True)
    model, assets = schema_model(), generated_assets()
    original, _ = baseline(runtime, model)
    additions = ui_records(assets)
    desired = expected_after(model, original, additions)
    # Re-check ownership/cold state before the exclusive marker. A failed or
    # interrupted operation stays marked incomplete and cannot overwrite/retry.
    cold_runtime(runtime, creating=True)
    private_write(runtime / STARTED, json.dumps({'format': FORMAT, 'kind': 'teachingopen-synthetic-role-flow', 'started_unix': int(time.time())}) + '\n')
    asset_directory = runtime / 'uploads/role-flow'
    asset_directory.mkdir(mode=0o700)
    for name, data in assets.items(): private_write(asset_directory / name, data)
    credentials = json.loads((runtime / 'config/credentials.json').read_text())
    password = credentials.get('mysql_app_password')
    if not isinstance(password, str) or not re.fullmatch('[0-9a-f]{40}', password):
        raise ValueError('Unexpected local application credential format')
    client = runtime / 'role-flow-app-client.cnf'
    private_write(client, '[client]\nuser=teaching_dev\npassword=' + password + '\nhost=127.0.0.1\nprotocol=tcp\nport=' + str(load_ports(runtime)['mysql']) + '\nlocal-infile=0\n')
    args = [str(runtime / 'tools/mysql-8.4.6-macos15-arm64/bin/mysql'), '--defaults-file=' + str(client), '--no-login-paths', '--host=127.0.0.1', '--protocol=tcp', '--port=' + str(load_ports(runtime)['mysql']), '--local-infile=0', '--batch', '--skip-column-names', '--database=teachingopen_dev']
    identity = command(runtime, args + ['-e', "SELECT CONCAT(CURRENT_USER(),'|',@@datadir,'|',@@port)"], text=True).strip()
    if identity != 'teaching_dev@127.0.0.1|' + str(runtime / 'mysql-data') + '/|' + str(load_ports(runtime)['mysql']):
        raise ValueError('Local application database identity changed')
    grants = command(runtime, args + ['-e', 'SHOW GRANTS FOR CURRENT_USER'], text=True).splitlines()
    if any(not re.fullmatch(r"GRANT USAGE ON \*\.\* TO `teaching_dev`@`127\.0\.0\.1`|GRANT [A-Z, ]+ ON `teachingopen_dev`\.\* TO `teaching_dev`@`127\.0\.0\.1`", grant) for grant in grants):
        raise ValueError('Application user has privileges outside the dedicated schema')
    command(runtime, args, input=fixture_sql(additions), text=True)
    compare_records(model, read_database(runtime, model), desired)
    assert_database(runtime)
    manifest = {'format': FORMAT, 'kind': 'teachingopen-synthetic-role-flow', 'complete': True,
                'created_unix': int(time.time()), 'runtime': str(runtime), 'datadir': str(runtime / 'mysql-data'),
                'ports': load_ports(runtime), 'sources': source_fingerprints(),
                'config_sha256': sha256(runtime / 'config/application-localtest.properties'),
                'seed_sha256': sha256(runtime / 'config/fixture-seed.sql'),
                'database': database_inventory(runtime), 'uploads': file_inventory(runtime / 'uploads'),
                'accounts': 5, 'ui_courses': 1, 'ui_units': 3, 'ui_tasks': 1,
                'initial_verification_only': True, 'asset_origin': 'self-authored; no production material'}
    cold_runtime(runtime)
    private_write(runtime / MANIFEST, json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    return summary(manifest)


def verify(path):
    runtime = cold_runtime(path)
    manifest = json.loads(private_file(runtime / MANIFEST).read_text())
    if manifest.get('format') != FORMAT or manifest.get('kind') != 'teachingopen-synthetic-role-flow' or manifest.get('complete') is not True:
        raise ValueError('Missing or unsupported complete role-flow manifest')
    if manifest.get('runtime') != str(runtime) or manifest.get('datadir') != str(runtime / 'mysql-data') or manifest.get('ports') != load_ports(runtime):
        raise ValueError('Manifest does not belong to this runtime')
    if manifest.get('sources') != source_fingerprints() or manifest.get('config_sha256') != sha256(runtime / 'config/application-localtest.properties') or manifest.get('seed_sha256') != sha256(private_file(runtime / 'config/fixture-seed.sql')):
        raise ValueError('Fixture tool, schema, seed, or isolation configuration changed')
    model, assets = schema_model(), generated_assets()
    original = parse_original_seed((runtime / 'config/fixture-seed.sql').read_text())
    compare_records(model, read_database(runtime, model), expected_after(model, original, ui_records(assets)))
    inventory = file_inventory(runtime / 'uploads')
    if inventory != manifest.get('uploads') or database_inventory(runtime) != manifest.get('database'):
        raise ValueError('Initial fixture database/assets changed; this is not a runtime health/stop check')
    expected_files = {name: {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()} for name, data in assets.items()}
    if file_inventory(runtime / 'uploads/role-flow') != expected_files:
        raise ValueError('Self-authored runtime resources differ from the tool')
    return summary(manifest)


def summary(manifest):
    return {'complete': True, 'verification': 'cold initial fixture', 'accounts': 5,
            'classes_category_3': 2, 'new_courses': 1, 'new_units': 3, 'new_tasks': 1,
            'registered_routes': len(ROUTES), 'button_permissions': 2,
            'self_authored_assets': len(manifest['uploads']) - 2,
            'real_browser_acceptance': 'not performed by this tool'}
