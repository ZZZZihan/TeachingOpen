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

EXPECTED_CHECKS = 186
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

    def profile(username):
        return sql("SELECT identity FROM teaching_registration_profile p JOIN sys_user u ON u.id=p.user_id WHERE u.username='" + username + "'")

    def account_security(username):
        return sql("SELECT CONCAT(username,'|',user_identity,'|',status,'|',del_flag,'|',COALESCE(depart_ids,'')) "
                   "FROM sys_user WHERE username='" + username + "'") == username + '|1|1|0|'

    def extra_relations(username):
        tables = ('sys_user_depart', 'sys_depart_role_user', 'teaching_student', 'teaching_work',
                  'teaching_work_comment', 'wechat_user')
        counts = [sql('SELECT COUNT(*) FROM `' + table + "` r JOIN sys_user u ON u.id=r.user_id WHERE u.username='" + username + "'") for table in tables]
        counts.append(sql("SELECT COUNT(*) FROM sys_user_agent WHERE user_name='" + username + "' OR agent_user_name='" + username + "'"))
        return all(count == '0' for count in counts)

    def refuse_management(label, token):
        before = state_snapshot()
        for name, path in (('admin', '/teaching/teachingCourse/list'),
                           ('class management', '/teaching/teachingCourseDept/list'),
                           ('teacher work management', '/teaching/teachingWork/list')):
            result = api(path, token=token)
            check(label + ' ' + name + ' endpoint refused', result.get('success') is False and result.get('code') == 510)
        check(label + ' permission denial leaves all 10 tables unchanged', state_snapshot() == before)

    def login(username, password):
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
        r = api('/sys/login', {'username': username, 'password': password, 'checkKey': nonce, 'captcha': captcha})
        check('password login accepts requested account', r.get('success') is True)
        return r['result']['token']

    check('isolated application healthy', api('/actuator/health').get('status') == 'UP')
    base = int(sql('SELECT COUNT(*) FROM sys_user'))
    usernames = ['registration_' + secrets.token_hex(8) for _ in range(5)]
    usernames[0] = 'reg_' + secrets.token_hex(4) + '@example.edu-cn'
    usernames[1] = 'r' + secrets.token_hex(1)
    usernames[2] = 'Reg_' + secrets.token_hex(48)
    usernames[3] = '198' + ''.join(secrets.choice('0123456789') for _ in range(8))
    check('synthetic usernames unused', sql('SELECT COUNT(*) FROM sys_user WHERE username IN (' + ','.join("'" + value + "'" for value in usernames) + ')') == '0')
    tokens = []
    password = 'abc12345'
    legacy_id = 'reg_legacy_' + secrets.token_hex(8)
    legacy_username, legacy_password = '19900000001', 'Legacy8!'
    legacy_created = False
    try:
        check('synthetic legacy username and phone unused', sql("SELECT COUNT(*) FROM sys_user WHERE username='" + legacy_username + "' OR phone='" + legacy_username + "'") == '0')
        # Known synthetic ciphertext from the unchanged PasswordUtil.encrypt(
        # '19900000001', 'Legacy8!', 'legacy01'), representing an older phone account.
        sql("INSERT INTO sys_user(id,username,phone,password,salt,realname,school,status,del_flag,user_identity,depart_ids) VALUES ('"
            + legacy_id + "','" + legacy_username + "','" + legacy_username
            + "','174bbf2179eb33e9109160eb818ff57e','legacy01','旧账号验收','隔离学校',1,0,1,'')")
        legacy_created = True
        legacy_before = sql("SELECT SHA2(CAST(JSON_ARRAY(username,phone,password,salt,status,del_flag) AS CHAR),256) FROM sys_user WHERE id='" + legacy_id + "'")
        check('synthetic legacy phone account exists before new registrations', bool(legacy_before))
        tokens.append(login(legacy_username, legacy_password))
        check('one isolated allowReg configuration is enabled', sql("SELECT CONCAT(COUNT(*),'|',COALESCE(MIN(config_value),'missing')) FROM sys_config WHERE config_key='allowReg' AND config_enabled=1") == '1|1')
        before_disabled = state_snapshot()
        sql("UPDATE sys_config SET config_value='0' WHERE config_key='allowReg' AND config_enabled=1")
        try:
            for label, entry in (('student', STUDENT_ENTRY), ('teacher', TEACHER_ENTRY)):
                result = api(entry, {'username': usernames[0], 'password': password, 'realname': '开关验收', 'school': '隔离学校'})
                check(label + ' entry respects disabled allowReg', result.get('success') is False and result.get('code') == 403)
            check('disabled entries leave all 10 tables unchanged', state_snapshot() == before_disabled)
        finally:
            sql("UPDATE sys_config SET config_value='1' WHERE config_key='allowReg' AND config_enabled=1")

        invalid_usernames = (('', 'empty'), ('ab', 'two characters'), ('a' * 101, '101 characters'),
                             ('abc def', 'interior space'), ('用户名', 'non-ASCII'),
                             ("abc'xyz", 'quote'), ('abc/xyz', 'slash'), ({}, 'object'), (None, 'null'))
        for entry_label, entry in (('student', STUDENT_ENTRY), ('teacher', TEACHER_ENTRY)):
            for invalid_username, label in invalid_usernames:
                before_invalid = state_snapshot()
                result = api(entry, {'username': invalid_username, 'password': password,
                                    'realname': '用户名边界验收', 'school': '隔离学校'})
                check(entry_label + ' rejects username with ' + label,
                      result.get('success') is False and result.get('code') == 400)
                check(entry_label + ' invalid username ' + label + ' leaves all 10 tables unchanged',
                      state_snapshot() == before_invalid)
            before_phone_only = state_snapshot()
            result = api(entry, {'phone': '13900000002', 'password': password,
                                'realname': '旧页面验收', 'school': '隔离学校'})
            check(entry_label + ' phone-only registration requires username',
                  result.get('success') is False and result.get('code') == 400)
            check(entry_label + ' phone-only rejection gives a refresh and username instruction',
                  '用户名' in result.get('message', '') and '刷新' in result.get('message', ''))
            check(entry_label + ' phone-only registration leaves all 10 tables unchanged',
                  state_snapshot() == before_phone_only)

        # Exercise username, legacy phone-only, and soft-deleted reservation paths.
        for reservation, patch in (
                ('existing username', "username='" + legacy_username + "',del_flag=0"),
                ('legacy phone', "username='" + legacy_id + "',del_flag=0"),
                ('deleted username', "username='" + legacy_username + "',del_flag=1")):
            sql("UPDATE sys_user SET " + patch + " WHERE id='" + legacy_id + "'")
            for label, entry in (('student', STUDENT_ENTRY), ('teacher', TEACHER_ENTRY)):
                before_reserved = state_snapshot()
                result = api(entry, {'username': legacy_username, 'password': password,
                                    'realname': '占位验收', 'school': '隔离学校'})
                check(label + ' reserves ' + reservation, result.get('success') is False and result.get('code') == 409)
                check(label + ' reserved ' + reservation + ' leaves all 10 tables unchanged', state_snapshot() == before_reserved)
        sql("UPDATE sys_user SET username='" + legacy_username + "',del_flag=0 WHERE id='" + legacy_id + "'")

        invalid_passwords = (('', 'empty'), ('1234567', 'seven characters'), ('a' * 65, '65 characters'),
                             ('abc defg', 'space'), ('abcdefgh中文', 'non-ASCII'),
                             ('abcdefgh\n', 'newline'), ('abcdefgh\t', 'tab'), ('abcdefgh\x7f', 'DEL'))
        for entry_label, entry in (('student', STUDENT_ENTRY), ('teacher', TEACHER_ENTRY)):
            for invalid_password, label in invalid_passwords:
                before_invalid = state_snapshot()
                result = api(entry, {'username': usernames[0], 'password': invalid_password,
                                    'realname': '密码边界验收', 'school': '隔离学校'})
                check(entry_label + ' rejects password with ' + label,
                      result.get('success') is False and result.get('code') == 400)
                check(entry_label + ' invalid password ' + label + ' leaves all 10 tables unchanged',
                      state_snapshot() == before_invalid)

        cases = (('public default student with digits-only password', STUDENT_ENTRY, None, 'student', '12345678'),
                 ('public forged teacher with letters-only password', STUDENT_ENTRY, 'teacher', 'student', 'abcdefgh'),
                 ('teacher entry with 64-character password', TEACHER_ENTRY, 'student', 'teacher', 'a' * 64))
        for i, (label, entry, supplied_identity, identity, case_password) in enumerate(cases):
            payload = {'username': usernames[i], 'password': case_password, 'realname': '验收𠮷' + str(i),
                'school': '数据库隔离验收𠮷学校', 'role': 'admin', 'roles': 'teacher,admin',
                'phone': '13900000002', 'userIdentity': 2, 'status': 2, 'departIds': 'privileged-depart'}
            if supplied_identity is not None: payload['identity'] = supplied_identity
            if i == 0: payload['username'] = ' ' + usernames[i] + ' '
            r = api(entry, payload)
            check(label + ' registration', r.get('success') is True)
            check(label + ' no credentials returned', case_password not in json.dumps(r) and usernames[i] not in json.dumps(r))
            check(label + ' exact required fields persisted', sql("SELECT CONCAT(realname,'|',school,'|',username) FROM sys_user WHERE username='" + usernames[i] + "'") == payload['realname'] + '|' + payload['school'] + '|' + usernames[i])
            check(label + ' password protected at rest', sql("SELECT COUNT(*) FROM sys_user WHERE username='" + usernames[i] + "' AND password<>'" + case_password + "' AND password<>'' AND salt<>''") == '1')
            check(label + ' no phone value is persisted', sql("SELECT COUNT(*) FROM sys_user WHERE username='" + usernames[i] + "' AND phone IS NULL") == '1')
            check(label + ' fixed profile persisted', profile(usernames[i]) == identity)
            check(label + ' only student role granted', sql("SELECT r.role_code FROM sys_user u JOIN sys_user_role ur ON ur.user_id=u.id JOIN sys_role r ON r.id=ur.role_id WHERE u.username='" + usernames[i] + "'") == 'student')
            check(label + ' security fields are server owned', account_security(usernames[i]))
            check(label + ' no business or department links created', extra_relations(usernames[i]))
            before_duplicate = state_snapshot()
            check(label + ' duplicate rejected', api(entry, payload).get('code') == 409)
            opposite_entry = TEACHER_ENTRY if entry == STUDENT_ENTRY else STUDENT_ENTRY
            check(label + ' cross entry duplicate rejected', api(opposite_entry, payload).get('code') == 409)
            check(label + ' username duplicate follows existing case-insensitive uniqueness',
                  api(entry, {**payload, 'username': usernames[i].upper()}).get('code') == 409)
            check(label + ' duplicate leaves profile and all 10 tables unchanged', state_snapshot() == before_duplicate)
            token = login(usernames[i], case_password); tokens.append(token)
            refuse_management(label, token)
        payload = {'username': usernames[3], 'password': password, 'realname': '并发验收', 'school': '隔离学校',
                   'identity': 'teacher', 'roles': 'admin,teacher', 'userIdentity': 2, 'departIds': 'privileged-depart', 'status': 2}
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            attempts = list(pool.map(lambda entry: (entry, api(entry, payload)), [STUDENT_ENTRY, TEACHER_ENTRY] * 3))
        results = [result for _, result in attempts]
        check('six concurrent attempts create one user', sum(r.get('success') is True for r in results) == 1)
        check('other concurrent attempts report duplicate', sum(r.get('code') == 409 for r in results) == 5)
        check('concurrent profile and role each saved once', sql("SELECT CONCAT((SELECT COUNT(*) FROM sys_user WHERE username='"+usernames[3]+"'),'|',(SELECT COUNT(*) FROM teaching_registration_profile p JOIN sys_user u ON u.id=p.user_id WHERE u.username='"+usernames[3]+"'),'|',(SELECT COUNT(*) FROM sys_user_role r JOIN sys_user u ON u.id=r.user_id WHERE u.username='"+usernames[3]+"'))") == '1|1|1')
        winning_entry = next(entry for entry, result in attempts if result.get('success') is True)
        check('mixed concurrent winner owns fixed profile', profile(usernames[3]) == ('teacher' if winning_entry == TEACHER_ENTRY else 'student'))
        check('concurrent security fields are server owned', account_security(usernames[3]))
        check('concurrent username account has no phone', sql("SELECT COUNT(*) FROM sys_user WHERE username='" + usernames[3] + "' AND phone IS NULL") == '1')
        check('concurrent no business or department links created', extra_relations(usernames[3]))
        token = login(usernames[3], password); tokens.append(token)
        refuse_management('mixed concurrent winner', token)
        trigger = 'backup_check_' + secrets.token_hex(6)
        sql("CREATE TRIGGER " + trigger + " BEFORE INSERT ON teaching_registration_profile FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='isolated registration rollback probe'")
        try:
            payload['username'] = usernames[4]
            for label, entry in (('student', STUDENT_ENTRY), ('teacher', TEACHER_ENTRY)):
                before_failure = state_snapshot()
                check(label + ' profile write failure reports retryable error', api(entry, payload).get('code') == 503)
                check(label + ' failed registration rolls back user', sql("SELECT COUNT(*) FROM sys_user WHERE username='" + usernames[4] + "'") == '0')
                check(label + ' failed registration leaves all 10 tables unchanged', state_snapshot() == before_failure)
        finally:
            sql('DROP TRIGGER ' + trigger)
        check('recovery after failure succeeds', api(STUDENT_ENTRY, payload).get('success') is True)
        check('recovery still uses fixed student profile', profile(usernames[4]) == 'student')
        check('recovered username account has no phone', sql("SELECT COUNT(*) FROM sys_user WHERE username='" + usernames[4] + "' AND phone IS NULL") == '1')
        tokens.append(login(legacy_username, legacy_password))
        check('legacy phone username password and salt remain unchanged', sql("SELECT SHA2(CAST(JSON_ARRAY(username,phone,password,salt,status,del_flag) AS CHAR),256) FROM sys_user WHERE id='" + legacy_id + "'") == legacy_before)
        check('final user count includes five new accounts and one temporary legacy fixture', int(sql('SELECT COUNT(*) FROM sys_user')) == base + 6)
        directory = api('/teaching/user/publicDirectory')['result']
        check('public directory contains only masked safe fields', all(set(row) == {'name', 'school', 'identity'} and '*' in row['name'] for row in directory['records']))
        return {'status': 'passed', 'database': db, 'checks': checks, 'passed': len(checks),
                'test_accounts': 5, 'legacy_fixture_accounts_created': 1,
                'legacy_fixture_accounts_retained': 0, 'production_test_writes': False}
    finally:
        try:
            for token in tokens: api('/sys/logout', token=token)
        finally:
            if legacy_created: sql("DELETE FROM sys_user WHERE id='" + legacy_id + "'")


if __name__ == '__main__':
    result = main(sys.argv[1])
    print(json.dumps(result, ensure_ascii=False, indent=2))
