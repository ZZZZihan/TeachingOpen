#!/usr/bin/env python3
"""Account status HTTP/WS regressions, restricted to the five owned fixtures.

The same desired-behavior assertions are used before and after the patch. Old
failures remain failures. Redis injection is deterministic stale-data testing,
not a reproduction of a naturally scheduled concurrent cache refill.
"""
import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

from local_http import FixtureApi
from local_recovery import database_inventory, private_write
from local_runtime import load_ports, mysql_command


def literal(value):
    return "CONVERT(0x" + str(value).encode().hex() + " USING utf8mb4)"


def verify(args):
    runtime = args.runtime.resolve()
    ports = load_ports(runtime)
    if runtime.name != 'account-freeze-1003' or any(ports[k] != v for k, v in
            {'mysql': 13367, 'redis': 16440, 'backend': 18167, 'frontend': 18168}.items()):
        raise ValueError('Only the account-freeze-1003 runtime is authorized')
    if args.output.exists():
        raise ValueError('Evidence already exists; use a fresh output name')
    spec = importlib.util.spec_from_file_location('account_freeze_ws', Path(__file__).with_name('verify-notification-websocket.py'))
    ws_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ws_module)
    cases, observations = [], []

    def check(name, passed, **details):
        cases.append({'case': name, 'passed': bool(passed), **details})
        print(('PASS ' if passed else 'FAIL ') + name, flush=True)

    with FixtureApi(runtime, args.jar) as api, ExitStack() as sockets:
        def sql(statement):
            result = subprocess.run(mysql_command(runtime) + ['teachingopen_dev', '-e', statement],
                                    capture_output=True, text=True, timeout=20)
            if result.returncode:
                # SQL and credentials are deliberately not copied to the report.
                raise RuntimeError('Owned fixture SQL operation failed')
            return result.stdout.strip()

        aliases = ('admin', 'teacher_a', 'teacher_b', 'student_a', 'student_b')
        fixtures = json.loads((runtime / 'fixture-accounts.json').read_text())
        names = {a: 'fixture_' + a for a in aliases}
        ids = {a: fixtures[names[a]]['id'] for a in aliases}
        id_list = ','.join(literal(ids[a]) for a in aliases)
        original_users = sql("SELECT id,username,status,del_flag,IFNULL(HEX(org_code),'~') FROM sys_user WHERE id IN (" + id_list + ') ORDER BY id').splitlines()
        if len(original_users) != 5 or any(line.split('\t')[1] not in names.values() or line.split('\t')[2:4] != ['1', '0'] for line in original_users):
            raise RuntimeError('Expected exactly the original five active synthetic users')
        columns = [line.split('\t')[0] for line in sql('SHOW COLUMNS FROM sys_user').splitlines()]
        if any(not column.replace('_', '').isalnum() for column in columns):
            raise RuntimeError('Unexpected fixture table column')
        row_expression = ','.join("IFNULL(HEX(CAST(`" + column + "` AS BINARY)),'~')" for column in columns)
        def complete_rows():
            return sql("SELECT 'ROW'," + row_expression + ' FROM sys_user WHERE id IN (' + id_list + ') ORDER BY id')
        original_complete_rows = complete_rows().splitlines()
        roles = {role: sql('SELECT role_id FROM sys_user_role WHERE user_id=' + literal(ids[actor]))
                 for role, actor in (('admin', 'admin'), ('teacher', 'teacher_a'), ('student', 'student_a'))}
        if any(not role or '\n' in role for role in roles.values()):
            raise RuntimeError('Expected one role per fixture actor')
        original_levels = {r: sql('SELECT role_level FROM sys_role WHERE id=' + literal(r)) for r in roles.values()}
        before = database_inventory(runtime)
        serial = uuid4().hex[:12]
        permission, grant = 'freeze_permission_' + serial, 'freeze_grant_' + serial
        trigger, ledger = 'freeze_fault_' + serial, 'freeze_attempt_' + serial
        cache_key = 'sys:cache:user::' + names['student_a']
        raw_normal, cache_ttl = None, None

        def states():
            # Include update_by/update_time and every other field; a partial
            # rollback must not become green merely because statuses match.
            return hashlib.sha256(complete_rows().encode()).hexdigest()

        def reset_statuses():
            sql('UPDATE sys_user SET status=1 WHERE id IN (' + id_list + ')')
            if raw_normal is not None:
                inject(raw_normal)

        def inject(value):
            result = subprocess.run(api.redis + ['-n', '1', '-x', 'SET', cache_key], input=value.encode(),
                                    capture_output=True, env=api.redis_env, timeout=5)
            if result.returncode or result.stdout.strip() != b'OK':
                raise RuntimeError('Owned cache injection failed')
            api.cache('EXPIRE', cache_key, str(max(60, cache_ttl or 60)))

        def call(body, actor='admin'):
            request = Request('http://127.0.0.1:' + str(ports['backend']) + '/api/sys/user/frozenBatch',
                              data=json.dumps(body).encode(), method='PUT',
                              headers={'Content-Type': 'application/json', 'X-Access-Token': api.tokens[actor]})
            try:
                response = urlopen(request, timeout=15)
            except HTTPError as error:
                response = error
            with response:
                raw = response.read(1024 * 1024)
                try:
                    payload = json.loads(raw)
                except ValueError:
                    payload = None
                return response.status, payload

        def accepted(reply):
            status, body = reply
            return status == 200 and isinstance(body, dict) and body.get('success') is True and body.get('code') == 200

        def rejected(reply, code=500):
            status, body = reply
            return status == 200 and isinstance(body, dict) and body.get('success') is False and body.get('code') == code

        def details(reply):
            return {'http_status': reply[0], 'code': reply[1].get('code') if isinstance(reply[1], dict) else None}

        def target_status(actor):
            return sql('SELECT status FROM sys_user WHERE id=' + literal(ids[actor]))

        def http_status():
            return api.request('GET', '/teaching/teachingCourse/mineCourse', 'student_a')[0]

        def http_allowed():
            status, body, _ = api.request('GET', '/teaching/teachingCourse/mineCourse', 'student_a')
            return status == 200 and isinstance(body, dict) and body.get('success') is True

        def connect():
            ws = ws_module.Socket(ports['backend'], ids['student_a'])
            sockets.callback(ws.close)
            ws.send({'type': 'authenticate', 'token': api.tokens['student_a']})
            return ws, ws.receive(2)

        def authz_key(actor):
            return 'shiro:cache:org.jeecg.modules.shiro.authc.ShiroRealm.authorizationCache:' + names[actor]

        try:
            sql('INSERT INTO sys_permission (id,name,url,component,menu_type,parent_id,status,del_flag,hidden,is_leaf,is_route,keep_alive,sort_no,perms,perms_type) VALUES ('
                + literal(permission) + ", 'Synthetic status permission','','',2,NULL,'1',0,0,1,1,1,1,'user:status','1')")
            sql('INSERT INTO sys_role_permission (id,role_id,permission_id) VALUES ('
                + ','.join(literal(v) for v in (grant, roles['admin'], permission)) + ')')
            for role, level in (('admin', 99), ('teacher', 2), ('student', 0)):
                sql('UPDATE sys_role SET role_level=' + str(level) + ' WHERE id=' + literal(roles[role]))
            for actor in ('admin', 'student_a', 'student_b'):
                api.cache('DEL', authz_key(actor))
                api.login(actor)

            check('ordinary old JWT accepted before status transition', http_allowed())
            raw_normal = api.cache('GET', cache_key)
            cache_ttl = int(api.cache('TTL', cache_key))
            cached = json.loads(raw_normal)
            if not isinstance(cached, dict) or cached.get('status') != 1:
                raise RuntimeError('Expected a warmed active LoginUser cache value')
            check('real active identity cache warmed', cache_ttl > 0 and cached.get('status') == 1)
            ws, reply = connect()
            check('actual notification socket authenticates before freeze', (reply or {}).get('cmd') == 'authenticated')
            reply = call({'ids': ids['student_a'], 'status': 2})
            check('normal administrator freeze commits status 2', accepted(reply) and target_status('student_a') == '2', **details(reply))
            check('successful freeze clears the previously warmed user cache after commit', api.cache('GET', cache_key) == '')
            status = http_status()
            check('same old JWT rejected after committed freeze', status == 401, http_status=status)
            ws.send('HeartBeat'); response = ws.receive(2)
            check('existing socket rechecks frozen state at heartbeat', (response or {}).get('close') == 1008)
            inject(raw_normal)
            status = http_status(); stale_ws, response = connect()
            check('DB frozen plus injected old active cache rejects HTTP and socket', status == 401 and (response or {}).get('close') == 1008, http_status=status)
            stale_ws.close()
            reply = call({'ids': ids['student_a'], 'status': '1'})
            check('normal administrator unfreeze commits status 1', accepted(reply) and target_status('student_a') == '1', **details(reply))
            check('successful unfreeze clears the injected user cache after commit', api.cache('GET', cache_key) == '')
            cached['status'] = 2
            inject(json.dumps(cached, ensure_ascii=False))
            allowed = http_allowed(); active_ws, response = connect()
            check('DB active plus injected stale frozen cache accepts the same old JWT and socket', allowed and (response or {}).get('cmd') == 'authenticated', http_allowed=allowed)
            active_ws.close(); ws.close(); inject(raw_normal)

            expected = states()
            reply = call({'ids': ids['student_b'], 'status': 2}, 'student_a')
            unchanged = states() == expected
            # Existing Result.noauth uses SC_JEECG_NO_AUTHZ=510. This is a
            # business code carried by HTTP 200, distinct from invalid JWT 401.
            check('equal-level actor without status permission rejected with no mutation', rejected(reply, 510) and unchanged,
                  unchanged=unchanged, success=reply[1].get('success') if isinstance(reply[1], dict) else None, **details(reply))
            reset_statuses()

            reply = call({'ids': ' ' + ids['student_b'] + ', ' + ids['student_b'] + ', , ', 'status': ' 2 '})
            check('trim duplicate and trailing comma normalize to one valid target', accepted(reply) and target_status('student_b') == '2' and target_status('student_a') == '1', **details(reply))
            call({'ids': ids['student_b'], 'status': 1}); reset_statuses()
            expected = states(); reply = call({'ids': ids['student_b'], 'status': 1})
            check('same-state request is successful and idempotent', accepted(reply) and states() == expected, **details(reply))

            invalid = [('null body', None), ('missing status', {'ids': ids['student_b']}),
                       ('null status', {'ids': ids['student_b'], 'status': None})]
            invalid += [('invalid status ' + str(v), {'ids': ids['student_b'], 'status': v}) for v in (0, 3, -1, '1.0', '01', 'bad', True)]
            invalid += [('missing ids', {'status': 2}), ('null ids', {'ids': None, 'status': 2}),
                        ('empty ids', {'ids': '', 'status': 2}), ('empty comma ids', {'ids': ' , , ', 'status': 2}),
                        ('array ids outside existing contract', {'ids': [ids['student_b']], 'status': 2})]
            for name, body in invalid:
                expected = states(); reply = call(body)
                # Literal JSON null may be rejected by MVC before the method.
                denied = rejected(reply) or (body is None and reply[0] == 400)
                check(name + ' rejected without changing users', denied and states() == expected, **details(reply))
                reset_statuses()

            expected = states()
            reply = call({'ids': ids['student_a'] + ',missing_' + serial, 'status': 2})
            check('valid plus missing target rejects entire batch', rejected(reply) and states() == expected, **details(reply))
            reset_statuses()
            sql('UPDATE sys_role SET role_level=100 WHERE id=' + literal(roles['teacher']))
            expected = states()
            reply = call({'ids': ids['student_a'] + ',' + ids['teacher_a'], 'status': 2})
            check('allowed plus higher-level target rejects entire batch', rejected(reply) and states() == expected, **details(reply))
            sql('UPDATE sys_role SET role_level=2 WHERE id=' + literal(roles['teacher'])); reset_statuses()

            if sql("SELECT COUNT(*) FROM sys_user WHERE username='admin'") != '0':
                raise RuntimeError('Canonical administrator fixture already exists; refusing rename')
            sql("UPDATE sys_user SET username='admin' WHERE id=" + literal(ids['teacher_b']))
            for state in (2, 1):
                expected = states()
                reply = call({'ids': ids['student_a'] + ',' + ids['teacher_b'], 'status': state})
                check('canonical administrator protected for target state ' + str(state), rejected(reply) and states() == expected, **details(reply))
                reset_statuses()
            sql('UPDATE sys_user SET username=' + literal(names['teacher_b']) + ' WHERE id=' + literal(ids['teacher_b']))

            # The nontransactional ledger records entry into row 1 before the
            # injected row-2 failure even when the application transaction rolls back.
            sql('CREATE TABLE ' + ledger + ' (seq INT AUTO_INCREMENT PRIMARY KEY, target_slot INT NOT NULL) ENGINE=MyISAM')
            sql('DELIMITER //\nCREATE TRIGGER ' + trigger + ' BEFORE UPDATE ON sys_user FOR EACH ROW BEGIN '
                + 'IF OLD.id IN (' + literal(ids['student_a']) + ',' + literal(ids['student_b']) + ') AND NEW.status=2 AND OLD.status<>NEW.status THEN '
                + 'INSERT INTO ' + ledger + ' (target_slot) VALUES (IF(OLD.id=' + literal(ids['student_a']) + ',1,2)); '
                + 'IF OLD.id=' + literal(ids['student_b']) + " THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='synthetic account status fault'; END IF; END IF; END//\nDELIMITER ;")
            expected = states()
            reply = call({'ids': ids['student_a'] + ',' + ids['student_b'], 'status': 2})
            attempts = sql('SELECT target_slot FROM ' + ledger + ' ORDER BY seq').splitlines()
            check('fault was injected after the first target update entered', attempts == ['1', '2'], attempted_slots=[int(v) for v in attempts])
            check('mid-batch SQL failure reports business failure without SQL details', rejected(reply) and 'synthetic account status fault' not in (reply[1] or {}).get('message', ''), **details(reply))
            check('mid-batch SQL failure rolls back all target states', states() == expected)
        finally:
            sockets.close()
            sql('DROP TRIGGER IF EXISTS ' + trigger)
            sql('DROP TABLE IF EXISTS ' + ledger)
            # The snapshot stays in memory. Full restoration includes normal
            # login org_code initialization and MyBatis update audit fields.
            for row in original_complete_rows:
                values = row.split('\t')[1:]
                assignments = []
                for column, value in zip(columns, values):
                    expression = 'NULL' if value == '~' else ("''" if value == '' else 'CONVERT(0x' + value + ' USING utf8mb4)')
                    if column != 'id':
                        assignments.append('`' + column + '`=' + expression)
                sql('UPDATE sys_user SET ' + ','.join(assignments) + ' WHERE id=CONVERT(0x' + values[columns.index('id')] + ' USING utf8mb4)')
            if raw_normal is not None:
                inject(raw_normal)
            for role, level in original_levels.items():
                sql('UPDATE sys_role SET role_level=' + level + ' WHERE id=' + literal(role))
            api.close()
            sql('DELETE FROM sys_role_permission WHERE id=' + literal(grant))
            sql('DELETE FROM sys_permission WHERE id=' + literal(permission))
            for actor in aliases:
                api.cache('DEL', authz_key(actor))

        after = database_inventory(runtime)
        changed_tables = [t for t in before if before[t] != after.get(t) and t != 'sys_log']
        check('all original database rows and schemas restored except ordinary audit logs',
              not changed_tables and before.keys() == after.keys(), changed_tables=changed_tables)
        check('owned trigger and ledger removed', sql("SELECT COUNT(*) FROM information_schema.triggers WHERE TRIGGER_SCHEMA='teachingopen_dev' AND TRIGGER_NAME=" + literal(trigger)) == '0'
              and sql("SELECT COUNT(*) FROM information_schema.tables WHERE TABLE_SCHEMA='teachingopen_dev' AND TABLE_NAME=" + literal(ledger)) == '0')
        observations.append({'kind': 'path_scope', 'value': 'Notification WebSocket and ordinary JWT use ShiroRealm. No application invocation of TokenUtils.verifyToken was found; this is not a TokenUtils direct-call test.'})
        observations.append({'kind': 'stale_cache_scope', 'value': 'An actual warmed active cache value and a constructed status-2 variant were injected through stdin in the owned Redis. This does not reproduce natural concurrent scheduling.'})
        result = {'observed_utc': datetime.now(timezone.utc).isoformat(), 'jar_sha256': api.jar_sha256,
                  'scope': 'Actual loopback HTTP and notification WebSocket; owned five-account permission/role fixture, deterministic stale-cache injection, and owned SQL trigger. No production, browser authentication, capacity or manual acceptance claim.',
                  'passed': sum(c['passed'] for c in cases), 'total': len(cases), 'cases': cases, 'observations': observations}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    private_write(args.output, json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(str(result['passed']) + '/' + str(result['total']) + ' checks passed', flush=True)
    return result['passed'] == result['total']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--jar', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    raise SystemExit(0 if verify(parser.parse_args()) else 1)
