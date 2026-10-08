#!/usr/bin/env python3
"""Real HTTP/SQL registration checks in a fresh five-account synthetic runtime.

Requires the isolated-runtime helpers from PR #4 (pass their api/dev as --support).
Registers without phone/SMS; never contacts any provider.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
import secrets
import subprocess
import sys


def literal(value):
    if str(value) == '':
        return "''"
    return "CONVERT(0x" + str(value).encode().hex() + " USING utf8mb4)"


def run(args):
    sys.path.insert(0, str(args.support.resolve()))
    from local_http import FixtureApi
    from local_runtime import mysql_command
    runtime = args.runtime.resolve()
    if runtime.parent.name != '.devspace' or not runtime.name.startswith('registration-'):
        raise ValueError('Use a dedicated registration-* synthetic runtime')
    if args.output.exists():
        raise ValueError('Use a fresh evidence file')
    api = FixtureApi(runtime, args.jar)
    cases = []
    def check(name, value):
        cases.append({'case': name, 'passed': bool(value)})
        print(('PASS ' if value else 'FAIL ') + name, flush=True)
    def sql(statement):
        result = subprocess.run(mysql_command(runtime) + ['teachingopen_dev'], input=statement,
                                text=True, capture_output=True, timeout=20)
        if result.returncode:
            raise RuntimeError('Owned synthetic SQL failed; private details withheld')
        return result.stdout.strip()
    def rows(table):
        columns = [line.split('\t')[0] for line in sql('SHOW COLUMNS FROM ' + table + ';').splitlines()]
        if any(not re.fullmatch('[a-zA-Z0-9_]+', c) for c in columns):
            raise RuntimeError('Unexpected schema')
        expressions = ','.join("IFNULL(HEX(CAST(`" + c + "` AS BINARY)), '~')" for c in columns)
        return sorted(sql('SELECT ' + expressions + ' FROM ' + table + ';').splitlines())
    tables = ['sys_user', 'sys_user_role', 'sys_user_depart', 'sys_config']
    original = {table: rows(table) for table in tables}
    expected = {'fixture_admin', 'fixture_teacher_a', 'fixture_teacher_b', 'fixture_student_a', 'fixture_student_b'}
    if set(sql('SELECT id FROM sys_user;').splitlines()) != expected or sql('SHOW TRIGGERS;'):
        raise ValueError('Expected only the five synthetic fixture accounts and no triggers')
    if sql("SELECT COUNT(*) FROM sys_config WHERE config_key IN ('allowReg','_defaultRole','_defaultDepart');") != '0':
        raise ValueError('Fixture already has registration configuration')
    prefix = 'regtest_' + secrets.token_hex(4)
    password = 'Aa9!' + secrets.token_hex(12)
    used_tokens = []
    def accepted(response):
        return response[0] == 200 and isinstance(response[1], dict) and response[1].get('success') is True
    def rejected(response):
        return response[0] in (400, 401, 403, 405) or (response[0] == 200 and isinstance(response[1], dict) and response[1].get('success') is False)
    def config(key, value):
        sql('UPDATE sys_config SET config_value=' + literal(value) + ' WHERE id=' + literal(prefix + key) + ';')
    def payload(index=0, username=None):
        return {'username': username or prefix + str(index), 'realname': '合成注册学生',
                'password': password}
    def no_write(name, body):
        before = {t: rows(t) for t in tables}
        response = api.request('POST', '/sys/user/register', data=body)
        check(name, rejected(response) and {t: rows(t) for t in tables} == before)
    def login_registered(username):
        nonce = 'registration-test-' + secrets.token_hex(8)
        response = api.request('GET', '/sys/randomImage/' + nonce)
        if not accepted(response): raise RuntimeError('CAPTCHA unavailable')
        captcha = None
        for key in api.cache('KEYS', '*').splitlines():
            if re.fullmatch('[a-fA-F0-9]{32}', key):
                try: value = json.loads(api.cache('GET', key))
                except ValueError: continue
                if isinstance(value, str) and hashlib.md5((value + nonce).encode()).hexdigest().lower() == key.lower():
                    captcha = value; break
        if captcha is None: raise RuntimeError('Owned CAPTCHA missing')
        response = api.request('POST', '/sys/login', data={'username': username, 'password': password, 'captcha': captcha, 'checkKey': nonce})
        if accepted(response): used_tokens.append(response[1]['result']['token'])
        return response
    try:
        for key, value in [('allowReg', '0'), ('_defaultRole', 'fixture_role_student'), ('_defaultDepart', 'fixture_class_a')]:
            sql('INSERT INTO sys_config(id,config_key,config_value,config_enabled) VALUES (' + ','.join(literal(v) for v in [prefix + key, key, value]) + ',1);')
        no_write('closed registration rejects account creation', payload())
        config('allowReg', '1')
        before = {t: rows(t) for t in tables}
        response = api.request('GET', '/sys/user/register')
        check('GET registration cannot create an account', rejected(response) and {t: rows(t) for t in tables} == before)
        for field, value in [('username', ['invalid']), ('username', 'abc'), ('realname', ''), ('realname', '😀'), ('password', 'abc123!中文'), ('password', ['invalid'])]:
            no_write('invalid ' + field + ' input is rejected ' + type(value).__name__, {**payload(), field: value})
        config('_defaultRole', 'fixture_role_admin'); no_write('privileged default role is rejected', payload()); config('_defaultRole', 'fixture_role_student')
        config('_defaultDepart', 'missing'); no_write('missing default class is rejected', payload()); config('_defaultDepart', 'fixture_class_a')
        response = api.request('POST', '/sys/user/register?id=fixture_admin&status=2&userIdentity=2&departIds=fixture_class_b', data={**payload(), 'id': 'fixture_admin', 'roles': 'admin', 'status': 2, 'userIdentity': 2, 'departIds': 'fixture_class_b', 'phone': ['untrusted'], 'smscode': 'ignored'})
        check('anonymous registration succeeds without phone or SMS code', accepted(response))
        check('registration response contains username only', accepted(response) and response[1]['result'] == {'username': prefix + '0'})
        user_id = sql('SELECT id FROM sys_user WHERE username=' + literal(prefix + '0') + ';')
        check('server controls identity/status and stores encrypted password', sql('SELECT CONCAT(status,del_flag,user_identity) FROM sys_user WHERE id=' + literal(user_id) + ';') == '101' and sql('SELECT password FROM sys_user WHERE id=' + literal(user_id) + ';') not in ('', password) and user_id != 'fixture_admin')
        check('server default student role and class applied exactly once', sql('SELECT role_id FROM sys_user_role WHERE user_id=' + literal(user_id) + ';') == 'fixture_role_student' and sql('SELECT dep_id FROM sys_user_depart WHERE user_id=' + literal(user_id) + ';') == 'fixture_class_a')
        check('client phone and SMS fields are ignored; stored phone is NULL', sql('SELECT phone IS NULL FROM sys_user WHERE id=' + literal(user_id) + ';') == '1')
        no_write('same username is rejected without altering existing account', payload(1, prefix + '0'))
        response = login_registered(prefix + '0')
        check('registered account signs in with actual CAPTCHA and new password', accepted(response))
        if accepted(response): check('new student can read its assigned courses', accepted(api.request('GET', '/teaching/teachingCourse/mineCourse', token=response[1]['result']['token'])))
        with ThreadPoolExecutor(max_workers=2) as pool:
            replies = list(pool.map(lambda body: api.request('POST', '/sys/user/register', data=body), [payload(2, prefix + 'race'), payload(3, prefix + 'race')]))
        check('concurrent same-username registrations create one account', sum(accepted(r) for r in replies) == 1 and sql('SELECT COUNT(*) FROM sys_user WHERE username=' + literal(prefix + 'race') + ';') == '1')
        check('concurrent same-username loser rolls back relationships', sql('SELECT COUNT(*) FROM sys_user_role r JOIN sys_user u ON u.id=r.user_id WHERE u.username=' + literal(prefix + 'race') + ';') == '1')
        response = api.request('POST', '/sys/user/register', data=payload(4))
        check('different accounts can both have NULL phone with existing unique index', accepted(response) and sql('SELECT COUNT(*) FROM sys_user WHERE username LIKE ' + literal(prefix + '%') + ' AND phone IS NULL;') == '3')
        config('_defaultRole', ''); config('_defaultDepart', '')
        response = api.request('POST', '/sys/user/register', data=payload(7))
        check('empty configured defaults permit account without relationships', accepted(response) and sql('SELECT COUNT(*) FROM sys_user_role r JOIN sys_user u ON u.id=r.user_id WHERE u.username=' + literal(prefix + '7') + ';') == '0' and sql('SELECT COUNT(*) FROM sys_user_depart r JOIN sys_user u ON u.id=r.user_id WHERE u.username=' + literal(prefix + '7') + ';') == '0')
        config('_defaultRole', 'fixture_role_student'); config('_defaultDepart', 'fixture_class_a')
        for index, table in [(5, 'sys_user_role'), (6, 'sys_user_depart')]:
            sql("CREATE TRIGGER registration_fault BEFORE INSERT ON " + table + " FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Synthetic registration fault';")
            try:
                no_write(table + ' fault rolls back account and all relationships', payload(index))
                response = api.request('POST', '/sys/user/register', data=payload(index))
                check(table + ' failure returns fixed non-sensitive retry state', rejected(response) and response[1].get('result', {}).get('registrationState') == 'registration_failed')
            finally: sql('DROP TRIGGER registration_fault;')
            check(table + ' rollback leaves account retryable', accepted(api.request('POST', '/sys/user/register', data=payload(index))))
    finally:
        for token in used_tokens:
            api.request('GET', '/sys/logout', token=token)
        sql('DELETE r FROM sys_user_role r JOIN sys_user u ON u.id=r.user_id WHERE u.username LIKE ' + literal(prefix + '%') + ';')
        sql('DELETE r FROM sys_user_depart r JOIN sys_user u ON u.id=r.user_id WHERE u.username LIKE ' + literal(prefix + '%') + ';')
        sql('DELETE FROM sys_user WHERE username LIKE ' + literal(prefix + '%') + ';')
        sql('DELETE FROM sys_config WHERE id LIKE ' + literal(prefix + '%') + ';')
        check('all four fixture tables fully restored', {table: rows(table) for table in tables} == original)
        api.close()
    report = {'passed': sum(c['passed'] for c in cases), 'total': len(cases), 'cases': cases, 'jar_sha256': api.jar_sha256,
              'scope': 'Real loopback HTTP, synthetic MySQL/Redis. No phone/SMS registration or production access.'}
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(str(report['passed']) + '/' + str(report['total']))
    return report['passed'] == report['total']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--jar', type=Path, required=True)
    parser.add_argument('--support', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    sys.exit(0 if run(parser.parse_args()) else 1)
