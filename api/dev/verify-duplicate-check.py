#!/usr/bin/env python3
"""Named duplicate checks through real Shiro/HTTP and an owned synthetic database."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
from urllib.parse import urlencode
from uuid import uuid4

from local_http import FixtureApi
from local_runtime import mysql_command


def verify(args):
    checks = []
    output = args.output.resolve()
    if output.exists():
        raise RuntimeError('Preserve existing duplicate-check evidence')
    report = {'observed_utc': datetime.now(timezone.utc).isoformat(),
              'scope': 'owned synthetic Spring/Shiro HTTP and MySQL',
              'production_connected': False, 'checks': checks}
    try:
        with FixtureApi(args.runtime.resolve(), args.jar) as api:
            report['jar_sha256'] = api.jar_sha256

            def sql(statement):
                result = subprocess.run(mysql_command(api.runtime) + ['teachingopen_dev'],
                                        input=statement, capture_output=True, text=True, timeout=20)
                if result.returncode:
                    raise RuntimeError('Synthetic duplicate-check SQL failed')
                return result.stdout.strip()

            def literal(value):
                return 'CONVERT(0x' + str(value).encode().hex() + ' USING utf8mb4) COLLATE utf8mb4_bin'

            def check(name, passed):
                checks.append({'case': name, 'passed': bool(passed)})
                print(('PASS ' if passed else 'FAIL ') + name, flush=True)
                if not passed:
                    raise AssertionError(name)

            tables = ('sys_user', 'sys_role', 'sys_user_role', 'sys_user_depart',
                      'sys_dict', 'sys_permission', 'sys_position', 'sys_depart_role',
                      'sys_sms_template', 'sys_fill_rule', 'sys_check_rule', 'sys_data_source')

            def snapshot():
                statements = ';'.join('SELECT ' + literal(table) + ';SELECT * FROM ' + table
                                      + ' ORDER BY id' for table in tables) + ';'
                return hashlib.sha256(sql(statements).encode()).hexdigest()

            def query(name, actor, params, success=None, code=None, raw=None):
                before = snapshot()
                status, body, _ = api.request('GET', '/sys/duplicate/check?' +
                                             (raw if raw is not None else urlencode(params)), actor)
                if code == 401:
                    accepted = status == 401 and (not body or body.get('success') is not True)
                else:
                    accepted = (status == 200 and isinstance(body, dict)
                                and body.get('success') is success and body.get('code') == code)
                    if code == 500:
                        accepted = accepted and body.get('message') == '该值不可用，系统中已存在！'
                check(name, accepted)
                check(name + ': protected database rows unchanged', snapshot() == before)

            prefix = 'dup_' + uuid4().hex[:12]
            dev_role, dev_grant = prefix + '_dev', prefix + '_grant'
            stale_grant, stale_dev_grant = prefix + '_old', prefix + '_olddev'
            original = snapshot()
            report['baseline_sha256'] = original
            saved = {}
            for table in ('sys_user', 'sys_role'):
                columns = [row.split('\t')[0] for row in sql('SHOW COLUMNS FROM ' + table).splitlines()]
                rows = sql('SELECT ' + ','.join("IFNULL(HEX(CAST(`" + column + "` AS BINARY)),'NULL')"
                                              for column in columns) + ' FROM ' + table + ' ORDER BY id').splitlines()
                saved[table] = columns, rows
            seed_targets = (
                ('dict_code', 'sys_dict', 'dict_code', {'dict_name': '合成字典', 'del_flag': '0'}),
                ('permission_perms', 'sys_permission', 'perms', {'name': '合成权限', 'menu_type': '2', 'del_flag': '0', 'status': '1'}),
                ('position_code', 'sys_position', 'code', {'name': '合成岗位'}),
                ('depart_role_code', 'sys_depart_role', 'role_code', {'depart_id': 'fixture_class_a', 'role_name': '合成部门角色'}),
                ('message_template_code', 'sys_sms_template', 'template_code',
                 {'template_name': '合成模板', 'template_type': '1', 'template_content': 'synthetic'}),
                ('fill_rule_code', 'sys_fill_rule', 'rule_code', {'rule_name': '合成规则'}),
                ('check_rule_code', 'sys_check_rule', 'rule_code', {'rule_name': '合成校验规则'}),
                ('data_source_code', 'sys_data_source', 'code', {'name': '合成数据源'}),
            )
            try:
                sql("UPDATE sys_role SET role_level=CASE role_code WHEN 'admin' THEN 9 WHEN 'teacher' THEN 5 ELSE 1 END;"
                    + 'INSERT INTO sys_role(id,role_code,role_name,role_level) VALUES ('
                    + literal(dev_role) + ",'dev','合成开发者',10);"
                    + 'INSERT INTO sys_user_role(id,user_id,role_id) VALUES ('
                    + literal(dev_grant) + ",'fixture_teacher_b'," + literal(dev_role) + ');'
                    + "UPDATE sys_user SET phone='13900000001',email='student-a@example.invalid',work_no='synthetic-001' WHERE id='fixture_student_a';"
                    + "UPDATE sys_user SET phone='13900000002',email='student-b@example.invalid',work_no='synthetic-002' WHERE id='fixture_student_b';")
                for index, (_, table, column, extra) in enumerate(seed_targets):
                    fields = dict(id=prefix + '_' + str(index), **{column: prefix + '_' + str(index)}, **extra)
                    sql('INSERT INTO ' + table + '(' + ','.join(fields) + ') VALUES ('
                        + ','.join(literal(value) for value in fields.values()) + ')')
                for actor in ('admin', 'teacher_a', 'teacher_b', 'student_a', 'student_b'):
                    for key in ('sys:cache:user::fixture_' + actor,
                                'shiro:cache:org.jeecg.modules.shiro.authc.ShiroRealm.authorizationCache:fixture_' + actor):
                        api.cache('DEL', key)
                    api.login(actor)

                query('anonymous is rejected by authentication', None,
                      {'purpose': 'user_username', 'fieldVal': 'fixture_student_a'}, code=401)
                management = ('user_username', 'user_phone', 'user_email', 'user_work_no', 'role_code') + tuple(x[0] for x in seed_targets)
                for actor in ('student_a', 'teacher_a'):
                    for purpose in management:
                        query(actor + ' cannot use management purpose ' + purpose, actor,
                              {'purpose': purpose, 'fieldVal': prefix}, False, 403)
                query('administrator cannot use developer role purpose', 'admin',
                      {'purpose': 'role_code', 'fieldVal': 'student'}, False, 403)

                # No arbitrary identifier or expression is accepted, even for a developer.
                for actor in ('student_a', 'admin', 'teacher_b'):
                    for index, params in enumerate((
                        {'tableName': 'sys_user', 'fieldName': 'password', 'fieldVal': 'x'},
                        {'tableName': 'sys_user', 'fieldName': "username AND SUBSTRING(password,1,1)='a' AND username", 'fieldVal': 'fixture_admin'},
                        {'tableName': 'sys_user WHERE 1=1', 'fieldName': 'username', 'fieldVal': 'fixture_admin'},
                        {'purpose': 'user_username', 'fieldVal': 'fixture_admin', 'tableName': 'sys_user'},
                        {'purpose': 'user_username', 'fieldVal': 'fixture_admin', 'fieldName': ''},
                        {'purpose': 'user_password', 'fieldVal': 'x'},
                        {'purpose': 'sys_user.password', 'fieldVal': 'x'},
                        {'fieldVal': 'x'},
                        {'purpose': 'user_username'},
                        {'purpose': 'user_username', 'fieldVal': prefix, 'unexpected': 'x'},
                    )):
                        query(actor + ' rejects identifier or malformed request ' + str(index), actor, params, False, 400)
                query('repeated purpose parameters are rejected', 'admin', {}, False, 400,
                      raw='purpose=user_username&purpose=profile_email&fieldVal=x')

                user_cases = (('user_username', 'fixture_student_a'), ('user_phone', '13900000001'),
                              ('user_email', 'student-a@example.invalid'), ('user_work_no', 'synthetic-001'))
                for purpose, existing in user_cases:
                    for actor in ('admin', 'teacher_b'):
                        query(actor + ' detects existing ' + purpose, actor,
                              {'purpose': purpose, 'fieldVal': existing}, False, 500)
                        query(actor + ' accepts unused ' + purpose, actor,
                              {'purpose': purpose, 'fieldVal': prefix + '_unused'}, True, 200)
                        query(actor + ' excludes authorized user for ' + purpose, actor,
                              {'purpose': purpose, 'fieldVal': existing, 'dataId': 'fixture_student_a'}, True, 200)
                        query(actor + ' cannot exclude away another match for ' + purpose, actor,
                              {'purpose': purpose, 'fieldVal': existing, 'dataId': 'fixture_student_b'}, False, 500)
                for index, (purpose, _, _, _) in enumerate(seed_targets):
                    identifier = prefix + '_' + str(index)
                    for actor in ('admin', 'teacher_b'):
                        query(actor + ' detects existing ' + purpose, actor, {'purpose': purpose, 'fieldVal': identifier}, False, 500)
                        query(actor + ' accepts unused ' + purpose, actor, {'purpose': purpose, 'fieldVal': prefix + '_unused'}, True, 200)
                        query(actor + ' edits authorized ' + purpose, actor,
                              {'purpose': purpose, 'fieldVal': identifier, 'dataId': identifier}, True, 200)
                query('developer detects role code', 'teacher_b', {'purpose': 'role_code', 'fieldVal': 'student'}, False, 500)
                query('developer accepts unused role code', 'teacher_b', {'purpose': 'role_code', 'fieldVal': prefix}, True, 200)
                query('developer excludes existing role', 'teacher_b',
                      {'purpose': 'role_code', 'fieldVal': 'student', 'dataId': 'fixture_role_student'}, True, 200)

                for purpose, _ in user_cases:
                    query('administrator cannot exclude higher-level developer for ' + purpose, 'admin',
                          {'purpose': purpose, 'fieldVal': prefix, 'dataId': 'fixture_teacher_b'}, False, 403)
                for purpose in management:
                    actor = 'teacher_b' if purpose == 'role_code' else 'admin'
                    query('missing exclusion record is rejected for ' + purpose, actor,
                          {'purpose': purpose, 'fieldVal': prefix, 'dataId': prefix + '_missing'}, False, 400)
                for identifier in ('FIXTURE_STUDENT_A', "fixture_student_a' OR '1'='1"):
                    query('exclusion ID must identify exact authorized object ' + identifier[:17], 'admin',
                          {'purpose': 'user_username', 'fieldVal': prefix, 'dataId': identifier}, False, 400)
                query('SQL-shaped field value is a literal', 'admin',
                      {'purpose': 'user_username', 'fieldVal': "' OR 1=1 -- "}, True, 200)
                query('cache-busting parameter is compatible', 'admin',
                      {'purpose': 'user_username', 'fieldVal': prefix, '_t': '123'}, True, 200)

                for purpose, own_value, other_value in (
                    ('profile_phone', '13900000001', '13900000002'),
                    ('profile_email', 'student-a@example.invalid', 'student-b@example.invalid')):
                    query('self-service keeps own unchanged ' + purpose, 'student_a',
                          {'purpose': purpose, 'fieldVal': own_value, 'dataId': 'fixture_student_a'}, True, 200)
                    query('self-service handles other value for ' + purpose, 'student_a',
                          {'purpose': purpose, 'fieldVal': other_value, 'dataId': 'fixture_student_a'},
                          False, 403 if purpose == 'profile_phone' else 500)
                    query('self-service handles unused value for ' + purpose, 'student_a',
                          {'purpose': purpose, 'fieldVal': prefix, 'dataId': 'fixture_student_a'},
                          purpose != 'profile_phone', 403 if purpose == 'profile_phone' else 200)
                    query('self-service rejects another account exclusion ' + purpose, 'student_a',
                          {'purpose': purpose, 'fieldVal': other_value, 'dataId': 'fixture_student_b'}, False, 403)
                    query('self-service requires own exclusion ID ' + purpose, 'student_a',
                          {'purpose': purpose, 'fieldVal': own_value}, False, 403)

                # Keep the same token and a real old Shiro role cache during revocation.
                for grant, role in ((stale_grant, 'fixture_role_admin'), (stale_dev_grant, dev_role)):
                    sql('INSERT INTO sys_user_role(id,user_id,role_id) VALUES (' + literal(grant)
                        + ",'fixture_student_a'," + literal(role) + ')')
                query('same token observes live administrator grant', 'student_a',
                      {'purpose': 'user_username', 'fieldVal': prefix}, True, 200)
                query('same token observes live developer grant', 'student_a',
                      {'purpose': 'role_code', 'fieldVal': prefix}, True, 200)
                path = Path(__file__).with_name('verify-account-authorization.py')
                spec = importlib.util.spec_from_file_location('duplicate_legacy_cache', path)
                legacy = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(legacy)
                jar = (args.jar or Path(__file__).resolve().parents[1] / 'jeecg-boot-module-system/target/teaching-open-2.8.0.jar').resolve()
                stale_value = legacy.legacy_authorization_payload(api.runtime, jar)
                stale_key = 'shiro:cache:org.jeecg.modules.shiro.authc.ShiroRealm.authorizationCache:fixture_student_a'
                stale_hash = hashlib.sha1(stale_value).hexdigest()
                replay = "local v=ARGV[1]:gsub('..',function(h)return string.char(tonumber(h,16))end);redis.call('SET',KEYS[1],v,'EX',200000);return redis.sha1hex(v)"
                check('authentic legacy role cache seeded', api.cache('EVAL', replay, '1', stale_key, stale_value.hex()) == stale_hash)
                sql('DELETE FROM sys_user_role WHERE id IN (' + literal(stale_grant) + ',' + literal(stale_dev_grant) + ')')
                for purpose in management:
                    query('revocation rejects old cache for ' + purpose, 'student_a', {'purpose': purpose, 'fieldVal': prefix}, False, 403)
                check('old authorization cache remained during all revoked requests',
                      api.cache('EVAL', "return redis.sha1hex(redis.call('GET',KEYS[1]) or '')", '1', stale_key) == stale_hash)
            finally:
                sql('DELETE FROM sys_user_role WHERE id IN (' + ','.join(map(literal, (dev_grant, stale_grant, stale_dev_grant))) + ');'
                    + 'DELETE FROM sys_role WHERE id=' + literal(dev_role) + ';')
                for index, (_, table, _, _) in enumerate(seed_targets):
                    sql('DELETE FROM ' + table + ' WHERE id=' + literal(prefix + '_' + str(index)))
                for table, (columns, rows) in saved.items():
                    for row in rows:
                        values = ['NULL' if value == 'NULL' else "CONVERT(X'" + value + "' USING utf8mb4)" for value in row.split('\t')]
                        record = dict(zip(columns, values))
                        sql('UPDATE ' + table + ' SET ' + ','.join('`' + column + '`=' + record[column]
                            for column in columns if column != 'id') + ' WHERE id=' + record['id'])
                for actor in api.tokens:
                    for key in ('sys:cache:user::fixture_' + actor,
                                'shiro:cache:org.jeecg.modules.shiro.authc.ShiroRealm.authorizationCache:fixture_' + actor):
                        api.cache('DEL', key)
            report['restored_sha256'] = snapshot()
            check('all synthetic fixture records restored', report['restored_sha256'] == original)
    except Exception as error:
        report['exception'] = type(error).__name__
        raise
    finally:
        report.update(passed=sum(case['passed'] for case in checks),
                      failed=sum(not case['passed'] for case in checks), total=len(checks))
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        output.chmod(0o600)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--jar', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    verify(parser.parse_args())
