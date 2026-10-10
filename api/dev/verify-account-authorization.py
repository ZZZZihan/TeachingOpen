#!/usr/bin/env python3
"""Exercise administrative and profile boundaries on an owned synthetic runtime."""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import subprocess
from urllib.parse import urlencode
from uuid import uuid4

from local_http import FixtureApi
from local_runtime import mysql_command


def verify(args):
    checks = []
    with FixtureApi(args.runtime.resolve(), args.jar) as api:
        def sql(statement):
            result = subprocess.run(mysql_command(api.runtime) + ['teachingopen_dev', '-e', statement],
                                    capture_output=True, text=True, timeout=20)
            if result.returncode:
                raise RuntimeError('Synthetic account SQL failed')
            return result.stdout.strip()

        def literal(value):
            return '0x' + str(value).encode().hex()

        def check(name, passed):
            checks.append({'case': name, 'passed': bool(passed)})
            print(('PASS ' if passed else 'FAIL ') + name, flush=True)
            if not passed:
                raise AssertionError(name)

        tables = ('sys_user', 'sys_user_role', 'sys_user_depart', 'sys_depart_role_user',
                  'sys_permission', 'sys_role_permission', 'sys_depart_role', 'sys_depart_role_permission',
                  'sys_role', 'sys_depart_permission')

        def snapshot():
            return {table: hashlib.sha256(sql('SELECT * FROM ' + table + ' ORDER BY id').encode()).hexdigest()
                    for table in tables}

        def request(method, route, actor, body=None):
            return api.request(method, route, actor, body)

        def denied(name, method, route, actor, body=None):
            before = snapshot()
            status, result, _ = request(method, route, actor, body)
            check(name, status != 404 and (status >= 400 or result is not None and result.get('success') is False))
            check(name + ' changes no account or permission records', snapshot() == before)

        def allowed(name, method, route, actor, body=None):
            status, result, _ = request(method, route, actor, body)
            check(name, status == 200 and result is not None and result.get('success') is True)

        def clear(actor):
            for key in ('sys:cache:user::fixture_' + actor, 'shiro:cache:org.jeecg.modules.shiro.authc.ShiroRealm.authorizationCache:fixture_' + actor):
                api.cache('DEL', key)

        # Exact state restoration is limited to the five synthetic accounts and roles.
        saved = {}
        for table in ('sys_user', 'sys_role'):
            columns = [line.split('\t')[0] for line in sql('SHOW COLUMNS FROM ' + table).splitlines()]
            rows = sql('SELECT ' + ','.join("IFNULL(HEX(CAST(`" + c + "` AS BINARY)),'NULL')" for c in columns)
                       + ' FROM ' + table + " WHERE id LIKE 'fixture_%' ORDER BY id").splitlines()
            saved[table] = (columns, rows)
        prefix = 'account_auth_' + uuid4().hex[:10]
        probe_a, probe_b = prefix + '_a', prefix + '_b'
        trigger = prefix + '_reject'
        original = snapshot()
        sql("UPDATE sys_role SET role_level=CASE role_code WHEN 'admin' THEN 9 WHEN 'teacher' THEN 5 ELSE 1 END WHERE id LIKE 'fixture_role_%'")
        try:
            for actor in ('admin', 'teacher_a', 'teacher_b', 'student_a', 'student_b'):
                api.login(actor)
            role_body = {'roleId': 'fixture_role_admin', 'userIdList': ['fixture_student_a']}
            for actor in ('student_a', 'teacher_a'):
                denied(actor + ' cannot self-grant admin', 'POST', '/sys/user/addSysUserRole', actor, role_body)
                denied(actor + ' cannot reset another password', 'PUT', '/sys/user/changePassword', actor,
                       {'id': 'fixture_student_b', 'username': 'fixture_student_b', 'password': 'SecurePassword9!'})
                denied(actor + ' cannot add account', 'POST', '/sys/user/add', actor,
                       {'username': prefix, 'realname': 'probe', 'password': 'SecurePassword9!', 'selectedroles': 'fixture_role_admin'})
                denied(actor + ' cannot edit account roles', 'PUT', '/sys/user/edit', actor,
                       {'id': 'fixture_student_a', 'selectedroles': 'fixture_role_admin'})
                for route in ('/sys/user/importExcel', '/sys/user/importStudent'):
                    denied(actor + ' cannot import accounts ' + route, 'POST', route, actor, {})
                for route in ('/sys/permission/add', '/sys/permission/saveRolePermission', '/sys/sysDepartRole/add'):
                    denied(actor + ' permission graph blocked ' + route, 'POST', route, actor, {})
                for method, route, body in (
                    ('POST', '/sys/sysDepartPermission/add', {}),
                    ('PUT', '/sys/sysDepartPermission/edit', {}),
                    ('DELETE', '/sys/sysDepartPermission/delete?id=missing', None),
                    ('DELETE', '/sys/sysDepartPermission/deleteBatch?ids=missing', None),
                    ('POST', '/sys/sysDepartPermission/importExcel', {}),
                    ('POST', '/sys/sysDepartPermission/datarule', {}),
                    ('POST', '/sys/sysDepartPermission/saveDeptRolePermission', {})):
                    denied(actor + ' department authorization blocked ' + route, method, route, actor, body)
                denied(actor + ' cannot restore recycle bin', 'PUT', '/sys/user/putRecycleBin', actor,
                       {'userIds': 'fixture_student_b'})
                denied(actor + ' cannot purge accounts', 'DELETE', '/sys/user/deleteRecycleBin?userIds=fixture_student_b', actor)
            for actor in ('student_a', 'teacher_a', 'admin'):
                for method, route, body in (
                    ('POST', '/sys/role/add', {'roleCode': 'dev', 'roleLevel': 999}),
                    ('PUT', '/sys/role/edit', {'id': 'fixture_role_admin', 'roleLevel': 999}),
                    ('PUT', '/sys/role/edit', {'id': 'fixture_role_student', 'roleCode': 'dev'}),
                    ('DELETE', '/sys/role/delete?id=fixture_role_admin', None),
                    ('DELETE', '/sys/role/deleteBatch?ids=fixture_role_student', None),
                    ('POST', '/sys/role/importExcel', {})):
                    denied(actor + ' cannot redefine role identity ' + route, method, route, actor, body)
            for route in ('/sys/user/appEdit', '/teaching/user/edit'):
                denied('profile alias rejects other ID ' + route, 'PUT', route, 'student_a',
                       {'id': 'fixture_student_b', 'realname': 'forged'})
                for key, value in (('password', 'forged'), ('salt', 'salt'), ('status', 0), ('delFlag', 1),
                                   ('departIds', 'fixture_school'), ('phone', '13912345678'), ('userIdentity', 2)):
                    denied('profile rejects ' + key + ' ' + route, 'PUT', route, 'student_a',
                           {'id': 'fixture_student_a', 'realname': 'probe', key: value})
            denied('self-password API cannot target a different username', 'PUT', '/sys/user/updatePassword', 'student_a',
                   {'username': 'fixture_student_b', 'oldpassword': api.credentials['test_user_password'],
                    'password': 'SecurePassword9!', 'confirmpassword': 'SecurePassword9!'})
            denied('role batch validates all target IDs', 'POST', '/sys/user/addSysUserRole', 'admin',
                   {'roleId': 'fixture_role_teacher', 'userIdList': ['fixture_student_a', prefix + '_missing']})
            denied('case aliases are not accepted as exact target IDs', 'POST', '/sys/user/addSysUserRole', 'admin',
                   {'roleId': 'fixture_role_teacher', 'userIdList': ['FIXTURE_STUDENT_A']})
            sql("INSERT INTO sys_role(id,role_code,role_name,role_level) VALUES ('" + prefix + "','dev','probe',10)")
            denied('administrator cannot grant developer', 'POST', '/sys/user/addSysUserRole', 'admin',
                   {'roleId': prefix, 'userIdList': ['fixture_student_a']})
            allowed('administrator creates account with validated roles and class', 'POST', '/sys/user/add', 'admin',
                    {'username': prefix + '_new', 'password': 'SecurePassword9!', 'realname': '合成管理账号',
                     'selectedroles': 'fixture_role_student', 'selecteddeparts': 'fixture_class_a',
                     'id': 'forged', 'status': 0, 'delFlag': 1})
            new_id = sql('SELECT id FROM sys_user WHERE username=' + literal(prefix + '_new'))
            check('new identity is server generated and active', new_id.isdigit() and
                  sql('SELECT CONCAT(status,del_flag) FROM sys_user WHERE id=' + literal(new_id)) == '10')
            credentials = sql('SELECT password,salt,username FROM sys_user WHERE id=' + literal(new_id))
            allowed('administrator edits allowed account fields', 'PUT', '/sys/user/edit', 'admin',
                    {'id': new_id, 'username': 'forged', 'password': 'forged', 'salt': 'forged',
                     'status': 0, 'realname': '合成已修改', 'selectedroles': 'fixture_role_teacher',
                     'selecteddeparts': 'fixture_class_b'})
            check('administrative edit preserves credentials and account identity',
                  sql('SELECT password,salt,username FROM sys_user WHERE id=' + literal(new_id)) == credentials)
            check('administrative edit commits selected memberships',
                  sql('SELECT role_id FROM sys_user_role WHERE user_id=' + literal(new_id)) == 'fixture_role_teacher' and
                  sql('SELECT dep_id FROM sys_user_depart WHERE user_id=' + literal(new_id)) == 'fixture_class_b')
            allowed('administrator logically deletes newly created account', 'DELETE', '/sys/user/delete?id=' + new_id, 'admin')
            allowed('administrator purges newly deleted account', 'DELETE', '/sys/user/deleteRecycleBin?userIds=' + new_id, 'admin')
            # Populate the real Shiro authorization cache before adding/removing a grant.
            denied('student has no recycle access before grant', 'GET', '/sys/user/recycleBin', 'student_a')
            allowed('administrator grants an allowed role', 'POST', '/sys/user/addSysUserRole', 'admin', role_body)
            allowed('same token observes newly granted role', 'GET', '/sys/user/recycleBin', 'student_a')
            allowed('administrator revokes role', 'DELETE', '/sys/user/deleteUserRole?' + urlencode(
                {'roleId': 'fixture_role_admin', 'userId': 'fixture_student_a'}), 'admin')
            denied('same token loses revoked role', 'GET', '/sys/user/recycleBin', 'student_a')
            for probe in (probe_a, probe_b):
                sql('INSERT INTO sys_user(id,username,realname,status,del_flag) VALUES (' + literal(probe) + ','
                    + literal(probe) + ",'probe',1,1)")
                sql('INSERT INTO sys_user_role(id,user_id,role_id) VALUES (' + literal(probe) + ',' + literal(probe)
                    + ",'fixture_role_student')")
                sql('INSERT INTO sys_user_depart(id,user_id,dep_id) VALUES (' + literal(probe) + ',' + literal(probe)
                    + ",'fixture_class_a')")
            denied('normal account cannot be permanently deleted', 'DELETE', '/sys/user/deleteRecycleBin?userIds=fixture_student_a', 'admin')
            denied('mixed normal and deleted targets preserve all rows', 'DELETE', '/sys/user/deleteRecycleBin?' + urlencode(
                {'userIds': probe_a + ',fixture_student_a'}), 'admin')
            for route, method in (('/sys/user/deleteRecycleBin', 'DELETE'), ('/sys/user/putRecycleBin', 'PUT')):
                value = probe_a + "') OR 1=1 -- "
                denied('SQL-shaped ID is only a bound value ' + route, method,
                       route + ('?' + urlencode({'userIds': value}) if method == 'DELETE' else ''),
                       'admin', {'userIds': value} if method == 'PUT' else None)
            sql('CREATE TRIGGER ' + trigger + " BEFORE DELETE ON sys_user_role FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='synthetic relationship failure'")
            try:
                denied('relationship failure rolls back physical account deletion', 'DELETE',
                       '/sys/user/deleteRecycleBin?userIds=' + probe_a + ',' + probe_b, 'admin')
            finally:
                sql('DROP TRIGGER ' + trigger)
            allowed('restore accepts valid recycle account', 'PUT', '/sys/user/putRecycleBin', 'admin', {'userIds': probe_a})
            check('restore changes deletion state only', sql('SELECT del_flag FROM sys_user WHERE id=' + literal(probe_a)) == '0')
            allowed('purge removes deleted account', 'DELETE', '/sys/user/deleteRecycleBin?userIds=' + probe_b, 'admin')
            check('purge removes all related memberships', all(sql('SELECT COUNT(*) FROM ' + t + ' WHERE '
                  + ('id' if t == 'sys_user' else 'user_id') + '=' + literal(probe_b)) == '0'
                  for t in ('sys_user', 'sys_user_role', 'sys_user_depart', 'sys_depart_role_user')))
            sensitive = 'username,password,salt,phone,status,del_flag,depart_ids,user_identity'
            before = sql('SELECT ' + sensitive + " FROM sys_user WHERE id='fixture_student_a'")
            allowed('own profile updates permitted fields', 'PUT', '/teaching/user/edit', 'student_a',
                    {'id': 'fixture_student_a', 'realname': '合成个人资料', 'avatar': '', 'email': None, 'sex': 1, 'birthday': None})
            check('own profile preserves all sensitive columns', sql('SELECT ' + sensitive + " FROM sys_user WHERE id='fixture_student_a'") == before)
            before = sql("SELECT username,realname,status,del_flag,depart_ids,user_identity FROM sys_user WHERE id='fixture_student_b'")
            allowed('reset uses canonical username and only credentials', 'PUT', '/sys/user/changePassword', 'admin',
                    {'id': 'fixture_student_b', 'username': 'forged', 'realname': 'forged', 'status': 0, 'password': 'SecurePassword9!'})
            check('reset preserves identity and status', sql("SELECT username,realname,status,del_flag,depart_ids,user_identity FROM sys_user WHERE id='fixture_student_b'") == before)
            denied('old token is rejected after password reset', 'GET', '/sys/user/queryById?id=fixture_student_b', 'student_b')
        finally:
            sql('DROP TRIGGER IF EXISTS ' + trigger)
            for table in ('sys_user_role', 'sys_user_depart', 'sys_depart_role_user'):
                sql('DELETE FROM ' + table + ' WHERE user_id IN (SELECT id FROM sys_user WHERE username=' + literal(prefix + '_new') + ')')
            sql('DELETE FROM sys_user WHERE username=' + literal(prefix + '_new'))
            for table in ('sys_user_role', 'sys_user_depart', 'sys_depart_role_user'):
                sql('DELETE FROM ' + table + ' WHERE user_id IN (' + literal(probe_a) + ',' + literal(probe_b) + ')')
            sql("DELETE FROM sys_user_role WHERE user_id='fixture_student_a' AND role_id IN ('fixture_role_admin','fixture_role_teacher')")
            sql('DELETE FROM sys_user WHERE id IN (' + literal(probe_a) + ',' + literal(probe_b) + ')')
            sql('DELETE FROM sys_role WHERE id=' + literal(prefix))
            for table, (columns, rows) in saved.items():
                for row in rows:
                    values = row.split('\t'); record = dict(zip(columns, ['NULL' if v == 'NULL' else "CONVERT(X'" + v + "' USING utf8mb4)" for v in values]))
                    sql('UPDATE ' + table + ' SET ' + ','.join('`' + c + '`=' + record[c] for c in columns if c != 'id') + ' WHERE id=' + record['id'])
            for actor in ('admin', 'teacher_a', 'teacher_b', 'student_a', 'student_b'):
                clear(actor)
        check('original account and permission records restored', snapshot() == original)
        report = {'observed_utc': datetime.now(timezone.utc).isoformat(), 'scope': 'owned synthetic HTTP/MySQL',
                  'jar_sha256': api.jar_sha256, 'production_connected': False, 'passed': len(checks), 'failed': 0, 'checks': checks}
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--jar', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    verify(parser.parse_args())
