#!/usr/bin/env python3
"""Exercise registration only on an explicitly named isolated database/application.

Config is private JSON. Never point this tool at the production application.
The isolated app must use this database and its own Redis database.
"""
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import urllib.error
import urllib.request

EXPECTED_CHECKS = 115
STUDENT_ENTRY = '/sys/user/register'
TEACHER_ENTRY = '/sys/user/register/teacher'
STATE_TABLES = ('sys_user', 'sys_user_role', 'teaching_registration_profile', 'sys_user_depart',
                'sys_depart', 'teaching_course', 'teaching_course_dept', 'teaching_course_unit',
                'teaching_additional_work', 'teaching_work')


def main(config_file):
    os.umask(0o077)
    c = json.loads(Path(config_file).read_text())
    db = c['database']
    if not re.fullmatch(r'teachingopen_check_[a-z0-9_]+', db):
        raise ValueError('Only a task-owned isolated database may be tested')
    if not re.fullmatch(r'http://127\.0\.0\.1:(8082|18259)/api', c['base_url']):
        raise ValueError('Only reserved task-owned loopback ports may be tested')
    props = dict(line.split('=', 1) for line in Path(c['application_config']).read_text().splitlines()
                 if '=' in line and not line.startswith('#'))
    if '/' + db + '?' not in props['spring.datasource.dynamic.datasource.master.url']:
        raise ValueError('Application/database mismatch')
    if props['spring.redis.database'] != str(c['redis_database']) or c['redis_database'] in (0, 1):
        raise ValueError('Isolated Redis database required')
    checks = []

    def check(name, value):
        if not value: raise AssertionError(name)
        checks.append(name)

    def sql(query):
        p = subprocess.run([c['mysql'], '--defaults-extra-file=' + c['mysql_options'],
            '--default-character-set=utf8mb4', '-N', db], input=query.encode(), capture_output=True)
        if p.returncode: raise RuntimeError('Isolated SQL failed')
        return p.stdout.decode().strip()

    def api(path, data=None, token=None):
        h = {'Content-Type': 'application/json'}
        if token: h['X-Access-Token'] = token
        req = urllib.request.Request(c['base_url'] + path,
            data=None if data is None else json.dumps(data).encode(), headers=h)
        try: response = urllib.request.urlopen(req, timeout=30)
        except urllib.error.HTTPError as error: response = error
        with response: return json.load(response)

    def cache(*args):
        env = {**os.environ, 'REDISCLI_AUTH': props['spring.redis.password']}
        return subprocess.check_output([c['redis_cli'], '-h', '127.0.0.1', '-p', props['spring.redis.port'],
            '--no-auth-warning', '-n', str(c['redis_database']), '--raw', *args], env=env).decode().strip()

    def state_snapshot():
        # Full-column aggregate hashes cover permission-denial and rollback side effects.
        # No row contents, password hashes, or tokens are included in the report.
        snapshot = {}
        for table in STATE_TABLES:
            columns = sql("SELECT COLUMN_NAME FROM information_schema.columns WHERE table_schema=DATABASE() "
                          "AND table_name='" + table + "' ORDER BY ORDINAL_POSITION").splitlines()
            if not columns or not all(re.fullmatch('[A-Za-z0-9_]+', column) for column in columns):
                raise RuntimeError('Unexpected isolated table columns')
            count = int(sql('SELECT COUNT(*) FROM `' + table + '`'))
            if count * 64 > 10000000:
                raise RuntimeError('Isolated table exceeds digest budget')
            row = 'SHA2(CAST(JSON_ARRAY(' + ','.join('`' + column + '`' for column in columns) + ') AS CHAR),256)'
            snapshot[table] = sql('SET SESSION group_concat_max_len=10000000; SELECT COUNT(*),'
                "COALESCE(SHA2(GROUP_CONCAT(" + row + ' ORDER BY ' + row + " SEPARATOR ''),256),'EMPTY') FROM `" + table + '`')
        return snapshot

    def profile(phone):
        return sql("SELECT identity FROM teaching_registration_profile p JOIN sys_user u ON u.id=p.user_id WHERE u.phone='" + phone + "'")

    def account_security(phone):
        return sql("SELECT CONCAT(username,'|',user_identity,'|',status,'|',del_flag,'|',COALESCE(depart_ids,'')) "
                   "FROM sys_user WHERE phone='" + phone + "'") == phone + '|1|1|0|'

    def extra_relations(phone):
        tables = ('sys_user_depart', 'sys_depart_role_user', 'teaching_student', 'teaching_work',
                  'teaching_work_comment', 'wechat_user')
        counts = [sql('SELECT COUNT(*) FROM `' + table + "` r JOIN sys_user u ON u.id=r.user_id WHERE u.phone='" + phone + "'") for table in tables]
        counts.append(sql("SELECT COUNT(*) FROM sys_user_agent WHERE user_name='" + phone + "' OR agent_user_name='" + phone + "'"))
        return all(count == '0' for count in counts)

    def refuse_management(label, token):
        before = state_snapshot()
        for name, path in (('admin', '/teaching/teachingCourse/list'),
                           ('class management', '/teaching/teachingCourseDept/list'),
                           ('teacher work management', '/teaching/teachingWork/list')):
            result = api(path, token=token)
            check(label + ' ' + name + ' endpoint refused', result.get('success') is False and result.get('code') == 510)
        check(label + ' permission denial leaves all 10 tables unchanged', state_snapshot() == before)

    def login(phone, password):
        nonce = 'registration-check-' + secrets.token_hex(12)
        check('captcha generated', api('/sys/randomImage/' + nonce).get('success') is True)
        captcha = None
        for key in cache('KEYS', '*').splitlines():
            if re.fullmatch('[a-f0-9]{32}', key):
                try: value = json.loads(cache('GET', key))
                except ValueError: continue
                if isinstance(value, str) and hashlib.md5((value + nonce).encode()).hexdigest() == key:
                    captcha = value; break
        check('captcha belongs to isolated cache', captcha is not None)
        r = api('/sys/login', {'username': phone, 'password': password, 'checkKey': nonce, 'captcha': captcha})
        check('new account password login', r.get('success') is True)
        return r['result']['token']

    check('isolated application healthy', api('/actuator/health').get('status') == 'UP')
    base = int(sql('SELECT COUNT(*) FROM sys_user'))
    phones = ['199' + ''.join(secrets.choice('0123456789') for _ in range(8)) for _ in range(5)]
    check('synthetic phones unused', sql('SELECT COUNT(*) FROM sys_user WHERE phone IN (' + ','.join("'" + p + "'" for p in phones) + ')') == '0')
    tokens = []
    password = 'abc12345'
    try:
        check('one isolated allowReg configuration is enabled', sql("SELECT CONCAT(COUNT(*),'|',COALESCE(MIN(config_value),'missing')) FROM sys_config WHERE config_key='allowReg' AND config_enabled=1") == '1|1')
        before_disabled = state_snapshot()
        sql("UPDATE sys_config SET config_value='0' WHERE config_key='allowReg' AND config_enabled=1")
        try:
            for label, entry in (('student', STUDENT_ENTRY), ('teacher', TEACHER_ENTRY)):
                result = api(entry, {'phone': phones[0], 'password': password, 'realname': '开关验收', 'school': '隔离学校'})
                check(label + ' entry respects disabled allowReg', result.get('success') is False and result.get('code') == 403)
            check('disabled entries leave all 10 tables unchanged', state_snapshot() == before_disabled)
        finally:
            sql("UPDATE sys_config SET config_value='1' WHERE config_key='allowReg' AND config_enabled=1")

        invalid_passwords = (('', 'empty'), ('1234567', 'seven characters'), ('a' * 65, '65 characters'),
                             ('abc defg', 'space'), ('abcdefgh中文', 'non-ASCII'),
                             ('abcdefgh\n', 'newline'), ('abcdefgh\t', 'tab'), ('abcdefgh\x7f', 'DEL'))
        for entry_label, entry in (('student', STUDENT_ENTRY), ('teacher', TEACHER_ENTRY)):
            for invalid_password, label in invalid_passwords:
                before_invalid = state_snapshot()
                result = api(entry, {'phone': phones[0], 'password': invalid_password,
                                    'realname': '密码边界验收', 'school': '隔离学校'})
                check(entry_label + ' rejects password with ' + label,
                      result.get('success') is False and result.get('code') == 400)
                check(entry_label + ' invalid password ' + label + ' leaves all 10 tables unchanged',
                      state_snapshot() == before_invalid)

        cases = (('public default student with digits-only password', STUDENT_ENTRY, None, 'student', '12345678'),
                 ('public forged teacher with letters-only password', STUDENT_ENTRY, 'teacher', 'student', 'abcdefgh'),
                 ('teacher entry with 64-character password', TEACHER_ENTRY, 'student', 'teacher', 'a' * 64))
        for i, (label, entry, supplied_identity, identity, case_password) in enumerate(cases):
            payload = {'phone': phones[i], 'password': case_password, 'realname': '验收𠮷' + str(i),
                'school': '数据库隔离验收𠮷学校', 'role': 'admin', 'roles': 'teacher,admin',
                'username': 'admin', 'userIdentity': 2, 'status': 2, 'departIds': 'privileged-depart'}
            if supplied_identity is not None: payload['identity'] = supplied_identity
            r = api(entry, payload)
            check(label + ' registration', r.get('success') is True)
            check(label + ' no credentials returned', case_password not in json.dumps(r) and phones[i] not in json.dumps(r))
            check(label + ' exact required fields persisted', sql("SELECT CONCAT(realname,'|',school,'|',phone) FROM sys_user WHERE phone='" + phones[i] + "'") == payload['realname'] + '|' + payload['school'] + '|' + phones[i])
            check(label + ' password protected at rest', sql("SELECT COUNT(*) FROM sys_user WHERE phone='" + phones[i] + "' AND password<>'" + case_password + "' AND password<>'' AND salt<>''") == '1')
            check(label + ' fixed profile persisted', profile(phones[i]) == identity)
            check(label + ' only student role granted', sql("SELECT r.role_code FROM sys_user u JOIN sys_user_role ur ON ur.user_id=u.id JOIN sys_role r ON r.id=ur.role_id WHERE u.phone='" + phones[i] + "'") == 'student')
            check(label + ' security fields are server owned', account_security(phones[i]))
            check(label + ' no business or department links created', extra_relations(phones[i]))
            before_duplicate = state_snapshot()
            check(label + ' duplicate rejected', api(entry, payload).get('code') == 409)
            opposite_entry = TEACHER_ENTRY if entry == STUDENT_ENTRY else STUDENT_ENTRY
            check(label + ' cross entry duplicate rejected', api(opposite_entry, payload).get('code') == 409)
            check(label + ' duplicate leaves profile and all 10 tables unchanged', state_snapshot() == before_duplicate)
            token = login(phones[i], case_password); tokens.append(token)
            refuse_management(label, token)
        payload = {'phone': phones[3], 'password': password, 'realname': '并发验收', 'school': '隔离学校',
                   'identity': 'teacher', 'roles': 'admin,teacher', 'userIdentity': 2, 'departIds': 'privileged-depart', 'status': 2}
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            attempts = list(pool.map(lambda entry: (entry, api(entry, payload)), [STUDENT_ENTRY, TEACHER_ENTRY] * 3))
        results = [result for _, result in attempts]
        check('six concurrent attempts create one user', sum(r.get('success') is True for r in results) == 1)
        check('other concurrent attempts report duplicate', sum(r.get('code') == 409 for r in results) == 5)
        check('concurrent profile and role each saved once', sql("SELECT CONCAT((SELECT COUNT(*) FROM sys_user WHERE phone='"+phones[3]+"'),'|',(SELECT COUNT(*) FROM teaching_registration_profile p JOIN sys_user u ON u.id=p.user_id WHERE u.phone='"+phones[3]+"'),'|',(SELECT COUNT(*) FROM sys_user_role r JOIN sys_user u ON u.id=r.user_id WHERE u.phone='"+phones[3]+"'))") == '1|1|1')
        winning_entry = next(entry for entry, result in attempts if result.get('success') is True)
        check('mixed concurrent winner owns fixed profile', profile(phones[3]) == ('teacher' if winning_entry == TEACHER_ENTRY else 'student'))
        check('concurrent security fields are server owned', account_security(phones[3]))
        check('concurrent no business or department links created', extra_relations(phones[3]))
        token = login(phones[3], password); tokens.append(token)
        refuse_management('mixed concurrent winner', token)
        trigger = 'backup_check_' + secrets.token_hex(6)
        sql("CREATE TRIGGER " + trigger + " BEFORE INSERT ON teaching_registration_profile FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='isolated registration rollback probe'")
        try:
            payload['phone'] = phones[4]
            for label, entry in (('student', STUDENT_ENTRY), ('teacher', TEACHER_ENTRY)):
                before_failure = state_snapshot()
                check(label + ' profile write failure reports retryable error', api(entry, payload).get('code') == 503)
                check(label + ' failed registration rolls back user', sql("SELECT COUNT(*) FROM sys_user WHERE phone='" + phones[4] + "'") == '0')
                check(label + ' failed registration leaves all 10 tables unchanged', state_snapshot() == before_failure)
        finally:
            sql('DROP TRIGGER ' + trigger)
        check('recovery after failure succeeds', api(STUDENT_ENTRY, payload).get('success') is True)
        check('recovery still uses fixed student profile', profile(phones[4]) == 'student')
        check('final user count includes exactly five test accounts', int(sql('SELECT COUNT(*) FROM sys_user')) == base + 5)
        directory = api('/teaching/user/publicDirectory')['result']
        check('public directory contains only masked safe fields', all(set(row) == {'name', 'school', 'identity'} and '*' in row['name'] for row in directory['records']))
        return {'status': 'passed', 'database': db, 'checks': checks, 'passed': len(checks),
                'test_accounts': 5, 'production_test_writes': False}
    finally:
        for token in tokens: api('/sys/logout', token=token)


if __name__ == '__main__':
    result = main(sys.argv[1])
    print(json.dumps(result, ensure_ascii=False, indent=2))
