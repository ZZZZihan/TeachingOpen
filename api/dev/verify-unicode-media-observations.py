#!/usr/bin/env python3
"""Separate Unicode-media observations; never change the frozen main assertions.

Reproduce repeated-separator permission/byte identity, the existing legal %2B
reference failure, and backend versus local frontend proxy HEAD behavior. No
service lifecycle actions or browser authentication are performed.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import http.client
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
from urllib.parse import quote
from uuid import uuid4

from local_http import FixtureApi
from local_recovery import database_inventory, private_write
from local_runtime import load_ports, mysql_command

spec = importlib.util.spec_from_file_location('unicode_media_main', Path(__file__).with_name('verify-unicode-media.py'))
main_probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(main_probe)


def verify(args):
    runtime = args.runtime.resolve()
    if (runtime.name != 'unicode-media-1003' or runtime.parent.name != '.devspace'
            or load_ports(runtime) != main_probe.EXPECTED_PORTS or runtime.is_symlink()):
        raise ValueError('Only the unicode-media-1003 synthetic runtime is authorized')
    if args.output.exists():
        raise ValueError('Evidence exists; use a fresh output name')
    lock = runtime / 'unicode-media-probe.lock'
    os.close(os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600))
    observations, checks = [], []
    prefix = 'fixture_ump_obs_' + uuid4().hex[:10]
    sandbox = runtime / 'uploads' / prefix
    fatal = None
    try:
        with FixtureApi(runtime, args.jar) as api:
            def sql(statement):
                result = subprocess.run(mysql_command(runtime) + ['teachingopen_dev', '-e', statement],
                                        capture_output=True, text=True, timeout=25)
                if result.returncode:
                    raise RuntimeError('Owned observation SQL operation failed')
                return result.stdout.rstrip('\n')

            literal = main_probe.literal
            before = database_inventory(runtime)
            files_before = main_probe.attachment_inventory(runtime / 'uploads')
            columns = [row.split('\t')[0] for row in sql('SHOW COLUMNS FROM sys_user').splitlines()]
            expression = ','.join("IFNULL(HEX(CAST(`" + column + "` AS BINARY)),'~')" for column in columns)
            original_users = sql("SELECT 'ROW'," + expression + ' FROM sys_user ORDER BY id').splitlines()
            if len(original_users) != 5 or sandbox.exists():
                raise RuntimeError('Expected untouched synthetic users and namespace')

            def call(path, actor=None, method='GET', headers=None, port=18169):
                h = dict(headers or {})
                if actor is not None:
                    h['X-Access-Token'] = api.tokens[actor]
                connection = http.client.HTTPConnection('127.0.0.1', port, timeout=15)
                try:
                    connection.request(method, path, headers=h)
                    reply = connection.getresponse()
                    return reply.status, reply.read(1024 * 1024), {k.lower(): v for k, v in reply.getheaders()}
                finally:
                    connection.close()

            def observe(name, reply, **fields):
                status, body, headers = reply
                item = {'case': name, 'http_status': status, 'body_bytes': len(body),
                        'body_sha256': hashlib.sha256(body).hexdigest(),
                        'headers': {k: v for k, v in headers.items() if k in
                                    ('content-type', 'content-length', 'content-range', 'content-disposition')}, **fields}
                observations.append(item)
                return item

            try:
                for actor in main_probe.ACTORS:
                    api.login(actor)
                sandbox.mkdir()
                (sandbox / '私人').mkdir()
                payload = main_probe.png(12, 200, 45)
                neighbor = main_probe.png(220, 14, 89)
                key = prefix + '/私人/图片.png'
                duplicate = prefix + '/私人//图片.png'
                (sandbox / '私人' / '图片.png').write_bytes(payload)
                (sandbox / '私人' / '邻居.png').write_bytes(neighbor)
                file_id, work_id = prefix + 'f', prefix + 'w'
                sql('INSERT INTO sys_file (id,create_by,file_path,file_name,file_location,del_flag) VALUES ('
                    + ','.join(map(literal, (file_id, 'fixture_student_a', key, '图片.png'))) + ',1,0)')
                sql('INSERT INTO teaching_work (id,user_id,depart_id,work_file,work_status,work_name,work_type,create_by,create_time) VALUES ('
                    + ','.join(map(literal, (work_id, 'fixture_student_a', 'fixture_class_a', file_id))) + ',0,'
                    + literal('合成重复分隔观察') + ',1,' + literal('fixture_student_a') + ',' + literal('2026-10-03 00:00:00') + ')')
                actors = ((None, False), ('student_b', False), ('teacher_b', False),
                          ('student_a', True), ('teacher_a', True), ('admin', True))
                for actor, allowed in actors:
                    for method, headers in (('GET', {}), ('HEAD', {}), ('GET', {'Range': 'bytes=2-8'})):
                        reply = call(main_probe.STATIC + quote(duplicate, safe='/'), actor, method, headers)
                        status = (206 if headers else 200) if allowed else (401 if actor is None else 403)
                        body = (payload[2:9] if headers else (b'' if method == 'HEAD' else payload)) if allowed else None
                        satisfied = (reply[0] == status and (reply[1] == body if allowed else payload not in reply[1])
                                     and neighbor not in reply[1])
                        name = 'duplicate separator ' + str(actor) + ' ' + method + (' Range' if headers else '')
                        observe(name, reply, expected_status=status,
                                canonical_permission_and_byte_identity_satisfied=satisfied, returned_neighbor=neighbor in reply[1])
                        checks.append({'case': name, 'passed': satisfied})
                        print(('PASS ' if satisfied else 'FAIL ') + name, flush=True)

                plus_key = prefix + '/plus+name.png'
                (sandbox / 'plus+name.png').write_bytes(payload)
                config_id = prefix + 'c'
                reference = main_probe.STATIC + quote(plus_key, safe='/')
                sql('INSERT INTO sys_config (id,config_key,config_enabled,config_value) VALUES ('
                    + literal(config_id) + ',' + literal(config_id) + ',1,' + literal('<img src="' + reference + '">') + ')')
                reply = call(main_probe.STATIC + quote(plus_key, safe='/'))
                observe('legal percent2B reference alone', reply, desired_status=200, returned_expected_bytes=reply[1] == payload)
                reference = main_probe.STATIC + quote(plus_key, safe='/+')
                sql('UPDATE sys_config SET config_value=' + literal('<img src="' + reference + '">') + ' WHERE id=' + literal(config_id))
                reply = call(main_probe.STATIC + quote(plus_key, safe='/'))
                observe('literal plus reference comparison', reply, desired_status=200, returned_expected_bytes=reply[1] == payload,
                        expected_body_sha256=hashlib.sha256(payload).hexdigest())
                for port in (18169, 18170):
                    observe('ASCII public HEAD via port ' + str(port),
                            call(main_probe.STATIC + quote(plus_key, safe='/'), method='HEAD', port=port), desired_status=200)
            except Exception as error:
                fatal = type(error).__name__
            finally:
                api.close()
                for table in ('sys_config', 'teaching_work', 'sys_file'):
                    sql('DELETE FROM `' + table + '` WHERE LEFT(id,' + str(len(prefix)) + ')=' + literal(prefix))
                for row in original_users:
                    values = row.split('\t')[1:]
                    assignments = []
                    for column, value in zip(columns, values):
                        if column == 'id':
                            continue
                        expression = 'NULL' if value == '~' else ("''" if value == '' else 'CONVERT(0x' + value + ' USING utf8mb4)')
                        assignments.append('`' + column + '`=' + expression)
                    sql('UPDATE sys_user SET ' + ','.join(assignments) + ' WHERE id=CONVERT(0x'
                        + values[columns.index('id')] + ' USING utf8mb4)')
                if sandbox.is_symlink():
                    raise RuntimeError('Owned observational sandbox unexpectedly became a link')
                if sandbox.exists():
                    shutil.rmtree(sandbox)
            after = database_inventory(runtime)
            files_after = main_probe.attachment_inventory(runtime / 'uploads')
            changed = [table for table in before if table != 'sys_log' and before[table] != after.get(table)]
            cleanup = {'complete_rows_and_schemas_restored_except_sys_log': before.keys() == after.keys() and not changed,
                       'changed_tables': changed, 'complete_attachment_inventory_restored': files_before == files_after}
            report = {'observed_utc': datetime.now(timezone.utc).isoformat(), 'jar_sha256': api.jar_sha256,
                      'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                      'scope': 'Separate observations, not added to 186 frozen assertions; actual synthetic CLI HTTP; existing contract and frontend tool limitations',
                      'passed_canonical_checks': sum(c['passed'] for c in checks), 'total_canonical_checks': len(checks),
                      'checks': checks, 'observations': observations, 'error_type': fatal, 'cleanup': cleanup,
                      'database_before': before, 'database_after': after}
    finally:
        lock.unlink(missing_ok=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    private_write(args.output, json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(str(report['passed_canonical_checks']) + '/' + str(report['total_canonical_checks'])
          + ' canonical permission/byte checks; known failures remain separate observations', flush=True)
    return (fatal is None and len(checks) == 18 and all(c['passed'] for c in checks)
            and cleanup['complete_rows_and_schemas_restored_except_sys_log'] and cleanup['complete_attachment_inventory_restored'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--jar', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    raise SystemExit(0 if verify(parser.parse_args()) else 1)
