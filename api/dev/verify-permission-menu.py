#!/usr/bin/env python3
"""Verify current-principal menu identity and empty/configured menus on local fixtures."""
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
from urllib.parse import quote
from local_http import FixtureApi
from local_runtime import mysql_command

PREFIX = 'fixture_mp_'
TABLES = ('sys_permission', 'sys_role_permission', 'sys_depart_role',
          'sys_depart_role_permission', 'sys_depart_role_user')
BASE = '/sys/permission/getUserPermissionByToken'


def verify(args):
    checks = []
    with FixtureApi(args.runtime.resolve(), args.jar) as api:
        def sql(query):
            return subprocess.check_output(mysql_command(api.runtime) + ['teachingopen_dev', '-e', query], text=True).strip()

        def snapshot():
            return {table: hashlib.sha256(sql('SELECT * FROM ' + table + ' ORDER BY id').encode()).hexdigest() for table in TABLES}

        def check(name, passed, **details):
            checks.append({'case': name, 'passed': bool(passed), **details})
            print(('PASS ' if passed else 'FAIL ') + name, flush=True)

        def request(actor=None, query=None, token=None):
            path = BASE if query is None else BASE + '?token=' + quote(query, safe='')
            return api.request('GET', path, actor=actor, token=token)[:2]

        def result(actor, query=None):
            status, body = request(actor, query)
            good = status == 200 and body and body.get('success') is True
            check(actor + ' menu response succeeds' + (' with legacy parameter' if query is not None else ''), good)
            return body.get('result', {}) if good else {}

        def ids(body):
            found = set()
            def walk(items):
                for item in items:
                    found.add(item['id'])
                    walk(item.get('children', []))
            walk(body.get('menu', []))
            return found

        def actions(body, field='auth'):
            return {item['action'] for item in body.get(field, [])}

        def permission(key, name, url, component, menu_type=0, parent=None, status='1', deleted=0, hidden=0, leaf=1, sort=1):
            # Only script-defined synthetic values are interpolated here.
            parent_value = 'NULL' if parent is None else "'" + PREFIX + parent + "'"
            url_value = 'NULL' if url is None else "'" + url + "'"
            sql("INSERT INTO sys_permission (id,name,url,component,menu_type,parent_id,status,del_flag,hidden,is_leaf,is_route,keep_alive,sort_no,perms,perms_type) VALUES "
                + f"('{PREFIX + key}','{name}',{url_value},'{component}',{menu_type},{parent_value},'{status}',{deleted},{hidden},{leaf},1,1,{sort},'fixture:{key}','1')")

        def grant_id(role, key):
            return PREFIX + hashlib.sha256((role + '_' + key).encode()).hexdigest()[:16]

        def grant(role, key):
            sql(f"INSERT INTO sys_role_permission(id,role_id,permission_id) VALUES ('{grant_id(role, key)}','fixture_role_{role}','{PREFIX + key}')")

        if any(sql('SELECT COUNT(*) FROM ' + table) != '0' for table in TABLES):
            raise RuntimeError('This menu fixture requires empty owned permission tables; refusing to overwrite')
        unavailable_table = PREFIX + 'permission_unavailable'
        if sql("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name='" + unavailable_table + "'") != '0':
            raise RuntimeError('Unexpected fault-injection table; refusing to overwrite')
        original = snapshot()
        process = json.loads((api.runtime / 'backend-process.json').read_text())
        log = Path(process['log_path']).resolve()
        if log.parent != api.runtime / 'logs' or log.stat().st_mode & 0o077:
            raise RuntimeError('Expected private runtime log')
        offset = log.stat().st_size
        observed_credentials = []
        try:
            for actor in ('admin', 'teacher_a', 'student_a', 'student_b'):
                api.login(actor)
                observed_credentials.append(api.tokens[actor])
            status, body = request('student_a')
            check('header-only request without URL credential', (status == 200 and body.get('success') and body.get('result') == {'menu': [], 'auth': [], 'allAuth': []}) if not args.expect_legacy else status != 200 or not body.get('success'), http_status=status)
            status, body = request('student_a', api.tokens['student_a'])
            check('empty menu table returns valid arrays without mandatory dashboard' if not args.expect_legacy else 'legacy empty menu reproduces failure',
                  (status == 200 and body.get('success') and body.get('result') == {'menu': [], 'auth': [], 'allAuth': []}) if not args.expect_legacy else status == 200 and body.get('success') is False,
                  http_status=status, code=body.get('code') if body else None)

            # A dashboard exists but is not implicitly granted to every user.
            permission('home', 'Fixture home', '/dashboard/analysis', 'dashboard/Index')
            permission('student', 'Fixture learning', '/fixture/learn', 'teaching/TeachingCourseList', leaf=0, sort=2)
            permission('child', 'Fixture unit', '/fixture/learn/unit', 'teaching/TeachingCourseUnitList', menu_type=1, parent='student', hidden=1, sort=3)
            permission('teacher', 'Fixture work', '/fixture/work', 'teaching/TeachingWorkList', sort=4)
            permission('admin', 'Fixture users', '/fixture/users', 'system/UserList', sort=5)
            permission('department', 'Fixture department', '/fixture/department', 'teaching/TeachingCourseList', sort=6)
            permission('deleted', 'Fixture deleted', '/fixture/deleted', 'teaching/TeachingCourseList', deleted=1)
            permission('student_button', 'Fixture student action', '', '', menu_type=2, parent='student')
            permission('teacher_button', 'Fixture teacher action', '', '', menu_type=2, parent='teacher')
            permission('admin_button', 'Fixture admin action', '', '', menu_type=2, parent='admin')
            permission('disabled_button', 'Fixture disabled control', '', '', menu_type=2, status='0')
            permission('deleted_button', 'Fixture deleted control', '', '', menu_type=2, deleted=1)
            for role, names in {'student': ['student', 'child', 'student_button', 'deleted', 'disabled_button', 'deleted_button'], 'teacher': ['teacher', 'teacher_button'], 'admin': ['admin', 'admin_button', 'home']}.items():
                for name in names: grant(role, name)
            sql(f"INSERT INTO sys_depart_role(id,depart_id,role_name,role_code) VALUES ('{PREFIX}dept_role','fixture_class_a','Fixture department role','fixture_mp')")
            sql(f"INSERT INTO sys_depart_role_user(id,user_id,drole_id) VALUES ('{PREFIX}dept_user','fixture_student_a','{PREFIX}dept_role')")
            sql(f"INSERT INTO sys_depart_role_permission(id,depart_id,role_id,permission_id) VALUES ('{PREFIX}dept_permission','fixture_class_a','{PREFIX}dept_role','{PREFIX}department')")
            before_reads = snapshot()
            own = result('student_a', api.tokens['student_a'] if args.expect_legacy else None)
            admin = result('admin', api.tokens['admin'] if args.expect_legacy else None)
            teacher = result('teacher_a', api.tokens['teacher_a'] if args.expect_legacy else None)
            check('admin assigned dashboard and controls retained', ids(admin) == {PREFIX + 'admin', PREFIX + 'home'} and actions(admin) == {'fixture:admin_button'})
            check('teacher role menu and controls retained', ids(teacher) == {PREFIX + 'teacher'} | ({PREFIX + 'home'} if args.expect_legacy else set()) and actions(teacher) == {'fixture:teacher_button'})
            check('student role and department menus combined', ids(own) == {PREFIX + x for x in ('student', 'child', 'department')} | ({PREFIX + 'home'} if args.expect_legacy else set()))
            check('hidden child and cache configuration preserved', any(item.get('children', [{}])[0].get('hidden') is True and item.get('meta', {}).get('keepAlive') is True for item in own.get('menu', []) if item['id'] == PREFIX + 'student'))
            check('deleted menu and disabled/deleted assigned controls excluded', PREFIX + 'deleted' not in ids(own) and actions(own) == {'fixture:student_button'})
            check('global button configuration retains status and excludes deleted', 'fixture:disabled_button' in actions(own, 'allAuth') and 'fixture:deleted_button' not in actions(own, 'allAuth'))
            sibling = result('student_b', api.tokens['student_b'] if args.expect_legacy else None)
            check('department menu is not shared with another student', PREFIX + 'department' not in ids(sibling))
            for query_name, query in [('other account', api.tokens['admin']), ('invalid signature', 'eyJhbGciOiJub25lIn0.' + base64.urlsafe_b64encode(b'{"username":"fixture_admin"}').decode().rstrip('=') + '.invalid')]:
                observed_credentials.append(query)
                status, body = request('student_a', query)
                check('query ' + query_name + (' selects another identity in legacy code' if args.expect_legacy else ' cannot override authenticated identity'),
                      status == 200 and body and body.get('result') == (admin if args.expect_legacy else own))
            if not args.expect_legacy:
                for query in ('', 'not-a-token', api.tokens['teacher_a']):
                    status, body = request('student_a', query)
                    check('ignored legacy parameter leaves current menu unchanged', status == 200 and body.get('result') == own)
                check('menu responses are not cacheable', api.last_response_headers.get('Cache-Control') == 'no-store')
            for label, actor, query, token in [('anonymous', None, None, None), ('query-only credential', None, api.tokens['admin'], None), ('invalid header with valid query', None, api.tokens['admin'], 'invalid-header')]:
                status, body = request(actor, query, token)
                check(label + ' is denied by real authentication', status == 401 and body and body.get('code') == 401)
            check('read and denied requests preserve permission tables', snapshot() == before_reads)
            if not args.expect_legacy:
                # Role/department changes must be reflected without reusing an old menu result.
                sql(f"DELETE FROM sys_role_permission WHERE id='{grant_id('student', 'child')}'")
                sql(f"DELETE FROM sys_depart_role_permission WHERE id='{PREFIX}dept_permission'")
                revoked = result('student_a')
                check('revoked child and department assignment disappear on next request', ids(revoked) == {PREFIX + 'student'})
                grant('student', 'child')
                sql(f"INSERT INTO sys_depart_role_permission(id,depart_id,role_id,permission_id) VALUES ('{PREFIX}dept_permission','fixture_class_a','{PREFIX}dept_role','{PREFIX}department')")
                check('restored assignments reappear without logout', result('student_a') == own)
                # Temporarily make only the verified, initially empty fixture menu table unavailable.
                # Restore it even when the real HTTP request fails; never drop application data.
                sql('RENAME TABLE sys_permission TO ' + unavailable_table)
                try:
                    status, body = request('student_a')
                    check('database failure returns recoverable generic HTTP error', status == 503 and body and body.get('success') is False and body.get('message') == '权限信息暂时不可用，请稍后重试。', http_status=status)
                finally:
                    sql('RENAME TABLE ' + unavailable_table + ' TO sys_permission')
                check('restored database recovers without clearing session', result('student_a') == own)
            api.request('GET', '/sys/logout', 'student_a')
            status, body = request('student_a', api.tokens['admin'])
            check('logged-out header cannot use another query credential', status == 401 and body.get('code') == 401)
            captured = log.read_bytes()[offset:].decode(errors='replace')
            check('menu request credential exposure matches candidate', any(token in captured for token in observed_credentials) == args.expect_legacy)
            check('no login password exported to captured logs', api.credentials['test_user_password'] not in captured)
            jar_hash = api.jar_sha256
        finally:
            for table in ('sys_depart_role_permission', 'sys_depart_role_user', 'sys_depart_role', 'sys_role_permission', 'sys_permission'):
                sql('DELETE FROM ' + table + " WHERE id LIKE '" + PREFIX + "%'")
        check('all original permission tables restored byte-for-byte', snapshot() == original)
    report = {'observed_utc': datetime.now(timezone.utc).isoformat(), 'jar_sha256': jar_hash,
              'expected_legacy': args.expect_legacy, 'scope': 'actual HTTP, authentication, role/department SQL fixtures, bounded menu-table unavailability, private log scan; no browser login or administrative menu-editor acceptance',
              'passed': sum(item['passed'] for item in checks), 'total': len(checks), 'cases': checks}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(f"{report['passed']}/{report['total']} checks passed")
    return report['passed'] == report['total']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--jar', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--expect-legacy', action='store_true')
    raise SystemExit(0 if verify(parser.parse_args()) else 1)
