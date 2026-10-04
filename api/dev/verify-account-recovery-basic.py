#!/usr/bin/env python3
"""Exercise password recovery on the existing five-account local fixture only.

This is a functional test, not an SMS delivery or browser acceptance test.
The test seeds only its own reset OTP; it never calls the SMS provider.
Credentials remain in memory and the private runtime; reports contain no secrets.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess

from local_http import FixtureApi
from local_runtime import mysql_command


def literal(value):
    return "CONVERT(0x" + value.encode().hex() + " USING utf8mb4)" if value else "''"


def accepted(reply):
    return reply[0] == 200 and isinstance(reply[1], dict) and reply[1].get('success') is True


def denied(reply):
    return reply[0] in (400, 401, 403, 405) or (
        reply[0] == 200 and isinstance(reply[1], dict) and reply[1].get('success') is False)


def run(args):
    runtime = args.runtime.resolve()
    if runtime.parent.name != '.devspace' or not runtime.name.startswith('recovery-'):
        raise ValueError('Use a dedicated recovery-* synthetic runtime directly under .devspace')
    if args.output.exists() or not args.output.parent.is_dir() or args.output.parent.is_symlink():
        raise ValueError('Use a fresh output file in an existing private directory')
    if args.output.parent.stat().st_mode & 0o077:
        raise ValueError('Evidence directory must be private')
    api = FixtureApi(runtime, args.jar)
    process = json.loads((runtime / 'backend-process.json').read_text())
    command = subprocess.check_output(['ps', '-p', str(process['pid']), '-o', 'command='], text=True)
    listeners = subprocess.check_output(['lsof', '-nP', '-t', '-iTCP:' + str(api.ports['backend']), '-sTCP:LISTEN'], text=True).split()
    if listeners != [str(process['pid'])] or '--spring.config.additional-location=file:' + str(runtime / 'config') + '/' not in command:
        raise RuntimeError('Backend listener or configuration belongs to another runtime')
    cases = []
    def check(name, value, **detail):
        cases.append({'case': name, 'passed': bool(value), **detail})
        print(('PASS ' if value else 'FAIL ') + name, flush=True)
    def sql(statement):
        reply = subprocess.run(mysql_command(runtime) + ['teachingopen_dev'], input=statement,
                               capture_output=True, text=True, timeout=20)
        if reply.returncode:
            raise RuntimeError('Synthetic fixture SQL failed; private details withheld')
        return reply.stdout.rstrip('\n')
    columns = [line.split('\t')[0] for line in sql('SHOW COLUMNS FROM sys_user;').splitlines()]
    if any(not c.replace('_', '').isalnum() for c in columns):
        raise ValueError('Unexpected schema')
    expression = ','.join("IFNULL(HEX(CAST(`" + c + "` AS BINARY)),'~')" for c in columns)
    def rows():
        return [line.split('\t') for line in sql('SELECT ' + expression + ' FROM sys_user ORDER BY id;').splitlines()]
    original = rows()
    id_index = columns.index('id')
    expected_names = {'fixture_admin', 'fixture_teacher_a', 'fixture_teacher_b', 'fixture_student_a', 'fixture_student_b'}
    if {bytes.fromhex(row[id_index]).decode() for row in original} != expected_names:
        raise ValueError('Expected exactly five owned fixture identities')
    target, phone = 'fixture_student_a', '19900000001'
    key = 'sys:password-reset:code:' + target + ':' + phone
    if api.cache('EXISTS', key) != '0':
        raise ValueError('Existing reset state would be overwritten')
    code = ''.join(secrets.choice('0123456789') for _ in range(6))
    new_password = 'Aa9!' + secrets.token_hex(12)
    payload = {'username': target, 'phone': phone, 'smscode': code, 'password': new_password}
    verify_payload = {k: payload[k] for k in ('username', 'phone', 'smscode')}
    reset = '/sys/user/passwordChange'
    started = datetime.now(timezone.utc).isoformat()
    def seed():
        reply = subprocess.run(api.redis + ['-n', '1', '-x', 'SET', key], input=code.encode(),
                               capture_output=True, env=api.redis_env, timeout=5)
        if reply.returncode or reply.stdout.strip() != b'OK':
            raise RuntimeError('Could not seed owned synthetic OTP')
        if api.cache('EXPIRE', key, '600') != '1':
            raise RuntimeError('Could not assign finite OTP expiry')
    def no_change(name, body):
        before = rows()
        response = api.request('POST', reset, data=body)
        check(name, denied(response) and rows() == before)
    error = None
    try:
        check('runtime, exact JAR and five synthetic identities verified', True)
        sql('UPDATE sys_user SET phone=' + literal(phone) + ' WHERE id=' + literal(target) + ';')
        api.login('student_a')
        check('ordinary fixture login reads protected course route', accepted(api.request('GET', '/teaching/teachingCourse/mineCourse', 'student_a')))
        old_token = api.tokens['student_a']
        before = rows()
        legacy = api.request('GET', reset)
        check('GET reset is rejected without database writes', denied(legacy) and rows() == before,
              http_status=legacy[0], business_code=legacy[1].get('code') if isinstance(legacy[1], dict) else None)
        no_change('missing OTP cannot update credentials', payload)
        seed()
        no_change('wrong code leaves credentials unchanged', {**payload, 'smscode': 'x' * 6})
        no_change('mismatched account leaves all user rows unchanged', {**payload, 'username': 'fixture_student_b'})
        no_change('mismatched phone leaves all user rows unchanged', {**payload, 'phone': '19900000002'})
        no_change('unsupported password characters rejected before consuming OTP', {**payload, 'password': 'Aa9!中文测试'})
        no_change('nonstring password rejected before consuming OTP', {**payload, 'password': ['invalid']})
        check('validation failures retain the finite OTP', api.cache('GET', key) == code and 0 < int(api.cache('TTL', key)) <= 600)
        api.cache('EXPIRE', key, '0')
        no_change('expired code cannot update credentials', payload)
        seed()
        ttl_before = int(api.cache('TTL', key))
        response = api.request('POST', '/sys/user/phoneVerification', data=verify_payload)
        ttl_after = int(api.cache('TTL', key))
        check('valid verification succeeds without returning the code', accepted(response) and code not in json.dumps(response[1]))
        check('verification preserves finite expiry and does not consume', 0 < ttl_after <= ttl_before and api.cache('GET', key) == code,
              ttl_before=ttl_before, ttl_after=ttl_after)
        before = rows()
        response = api.request('POST', reset, data=payload)
        after = rows()
        check('POST JSON reports success after actual credential change', accepted(response) and after != before)
        target_hex = target.encode().hex().upper()
        check('other four complete user rows remain unchanged', [r for r in before if r[id_index] != target_hex] == [r for r in after if r[id_index] != target_hex])
        check('successful reset consumes the OTP', api.cache('EXISTS', key) == '0')
        check('existing session loses protected access after reset', api.request('GET', '/teaching/teachingCourse/mineCourse', token=old_token)[0] == 401)
        no_change('used OTP cannot change the password again', {**payload, 'password': 'Aa9!' + secrets.token_hex(12)})
        old_login = api.request('POST', '/sys/mLogin', data={'username': target, 'password': api.credentials['test_user_password']})
        check('old password no longer signs in', denied(old_login))
        api.credentials['test_user_password'] = new_password
        api.login('student_a')
        check('new password signs in and reads the same protected route', accepted(api.request('GET', '/teaching/teachingCourse/mineCourse', 'student_a')))
        api.close()
    except Exception as exc:
        error = type(exc).__name__
        check('functional execution completed', False, error_type=error)
    finally:
        # Restore every original column, including audit and organization values
        # populated by ordinary login. Reports never serialize these snapshots.
        for row in original:
            values = [('NULL' if value == '~' else "CONVERT(0x" + value + " USING utf8mb4)" if value else "''") for value in row]
            assignments = ','.join('`' + col + '`=' + value for col, value in zip(columns, values))
            sql('UPDATE sys_user SET ' + assignments + ' WHERE id=' + values[id_index] + ';')
        api.cache('DEL', key, 'sys:cache:user::' + target)
        check('all five original user rows restored byte-for-byte', rows() == original)
        FixtureApi(runtime, args.jar)  # Re-run ownership guards; do not log in.
        check('ending process, data and frozen artifact guard passed', True)
    report = {'started_utc': started, 'ended_utc': datetime.now(timezone.utc).isoformat(),
              'jar_sha256': api.jar_sha256, 'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'runtime': str(runtime), 'ports': api.ports, 'pid': process['pid'],
              'passed': sum(c['passed'] for c in cases), 'total': len(cases), 'cases': cases,
              'scope': 'Root-agent actual synthetic HTTP functional check; no SMS delivery, browser credentials, independent full matrix, production or manual acceptance.',
              'exception_type': error}
    with os.fdopen(os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w') as out:
        json.dump(report, out, ensure_ascii=False, indent=2)
        out.write('\n')
    return report['passed'] == report['total']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--jar', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    raise SystemExit(0 if run(parser.parse_args()) else 1)
