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
    phones = ['199' + ''.join(secrets.choice('0123456789') for _ in range(8)) for _ in range(4)]
    check('synthetic phones unused', sql('SELECT COUNT(*) FROM sys_user WHERE phone IN (' + ','.join("'" + p + "'" for p in phones) + ')') == '0')
    tokens = []
    password = 'Verify9!' + secrets.token_hex(10)
    try:
        for i, identity in enumerate(('student', 'teacher')):
            payload = {'phone': phones[i], 'password': password, 'realname': '验收𠮷' + str(i),
                'school': '数据库隔离验收𠮷学校', 'identity': identity, 'role': 'admin', 'userIdentity': 2, 'status': 2}
            r = api('/sys/user/register', payload)
            check(identity + ' registration', r.get('success') is True)
            check(identity + ' no credentials returned', password not in json.dumps(r) and phones[i] not in json.dumps(r))
            check(identity + ' exact required fields persisted', sql("SELECT CONCAT(realname,'|',school,'|',phone) FROM sys_user WHERE phone='" + phones[i] + "'") == payload['realname'] + '|' + payload['school'] + '|' + phones[i])
            check(identity + ' password protected at rest', sql("SELECT COUNT(*) FROM sys_user WHERE phone='" + phones[i] + "' AND password<>'" + password + "' AND password<>'' AND salt<>''") == '1')
            check(identity + ' profile persisted', sql("SELECT identity FROM teaching_registration_profile p JOIN sys_user u ON u.id=p.user_id WHERE u.phone='" + phones[i] + "'") == identity)
            check(identity + ' only student role granted', sql("SELECT r.role_code FROM sys_user u JOIN sys_user_role ur ON ur.user_id=u.id JOIN sys_role r ON r.id=ur.role_id WHERE u.phone='" + phones[i] + "'") == 'student')
            check(identity + ' duplicate rejected', api('/sys/user/register', payload).get('code') == 409)
            token = login(phones[i], password); tokens.append(token)
            check(identity + ' admin endpoint refused', api('/teaching/teachingCourse/list', token=token).get('code') == 510)
        payload = {'phone': phones[2], 'password': password, 'realname': '并发验收', 'school': '隔离学校', 'identity': 'student'}
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(lambda _: api('/sys/user/register', payload), range(6)))
        check('six concurrent attempts create one user', sum(r.get('success') is True for r in results) == 1)
        check('other concurrent attempts report duplicate', sum(r.get('code') == 409 for r in results) == 5)
        check('concurrent profile and role each saved once', sql("SELECT CONCAT((SELECT COUNT(*) FROM sys_user WHERE phone='"+phones[2]+"'),'|',(SELECT COUNT(*) FROM teaching_registration_profile p JOIN sys_user u ON u.id=p.user_id WHERE u.phone='"+phones[2]+"'),'|',(SELECT COUNT(*) FROM sys_user_role r JOIN sys_user u ON u.id=r.user_id WHERE u.phone='"+phones[2]+"'))") == '1|1|1')
        trigger = 'backup_check_' + secrets.token_hex(6)
        sql("CREATE TRIGGER " + trigger + " BEFORE INSERT ON teaching_registration_profile FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='isolated registration rollback probe'")
        try:
            payload['phone'] = phones[3]
            check('profile write failure reports retryable error', api('/sys/user/register', payload).get('code') == 503)
            check('failed registration rolls back user', sql("SELECT COUNT(*) FROM sys_user WHERE phone='" + phones[3] + "'") == '0')
        finally:
            sql('DROP TRIGGER ' + trigger)
        check('recovery after failure succeeds', api('/sys/user/register', payload).get('success') is True)
        check('final user count includes exactly four test accounts', int(sql('SELECT COUNT(*) FROM sys_user')) == base + 4)
        directory = api('/teaching/user/publicDirectory')['result']
        check('public directory contains only masked safe fields', all(set(row) == {'name', 'school', 'identity'} and '*' in row['name'] for row in directory['records']))
        return {'status': 'passed', 'database': db, 'checks': checks, 'passed': len(checks),
                'test_accounts': 4, 'production_test_writes': False}
    finally:
        for token in tokens: api('/sys/logout', token=token)


if __name__ == '__main__':
    result = main(sys.argv[1])
    print(json.dumps(result, ensure_ascii=False, indent=2))
