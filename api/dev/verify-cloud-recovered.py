#!/usr/bin/env python3
"""Read-only recovery proof for an owned synthetic local runtime; no login or writes."""
import argparse
import base64
import hashlib
import http.client
import importlib.util
import json
from pathlib import Path
import re
import shlex
import subprocess
import time

from local_http import FixtureApi
from local_recovery import (database_inventory, file_inventory, inspect_snapshot,
                            local_path, private_write, project_ids, sha256, sql)
from local_runtime import assert_database, assert_mysql_owner, load_ports
from scratch_cloud_recovery import (OwnedRedis, PREFIX, capture_cloud,
                                    cloud_summary, load_cloud, read_private)


def key_inventory(client):
    """Read names only, without reading authentication/cache values."""
    cursor, keys = b'0', set()
    for _ in range(10000):
        reply = client.execute('SCAN', cursor, 'COUNT', 256)
        if (not isinstance(reply, list) or len(reply) != 2 or not isinstance(reply[0], bytes)
                or not isinstance(reply[1], list) or any(not isinstance(k, bytes) for k in reply[1])):
            raise RuntimeError('Invalid owned Redis key inventory')
        cursor = reply[0]; keys.update(reply[1])
        if len(keys) > 20000: raise RuntimeError('Synthetic inventory exceeded limit')
        if cursor == b'0': return keys
    raise RuntimeError('Synthetic inventory did not finish')


def inventory_digest(keys):
    digest = hashlib.sha256()
    for key in sorted(keys):
        digest.update(len(key).to_bytes(8, 'big')); digest.update(key)
    return digest.hexdigest()


def old_session_rejected(port, token):
    # http.client stays on this loopback endpoint and does not follow redirects.
    connection = http.client.HTTPConnection('127.0.0.1', port, timeout=10)
    try:
        connection.request('GET', '/api/sys/permission/getUserPermissionByToken',
                           headers={'X-Access-Token': token, 'Accept': 'application/json'})
        response = connection.getresponse()
        raw = response.read(65537)
        if len(raw) > 65536: raise RuntimeError('Permission reply exceeded limit')
        payload = json.loads(raw)
        return response.status == 401 and isinstance(payload, dict) and payload.get('success') is False and payload.get('code') == 401
    finally:
        connection.close()


def cloud_socket_class():
    # Import definitions only; verify() in this module is a separate mutation drill.
    spec = importlib.util.spec_from_file_location('cloud_recovery_protocol', Path(__file__).with_name('verify-scratch-cloud.py'))
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module.CloudSocket


def handshake(port, project):
    ws = cloud_socket_class()(port, project)
    messages, acknowledged = [], False
    try:
        ws.command('handshake')
        deadline = time.monotonic() + 5
        while not ws.closed and time.monotonic() < deadline:
            messages.extend(ws.receive(min(.25, max(.001, deadline - time.monotonic()))))
            if any(m.get('method') == 'ack' for m in messages):
                acknowledged = True; break
        return messages, acknowledged
    finally:
        ws.close()


def verify(args):
    cases, phase, error_type, aggregates = [], 'guard', None, {}
    output = Path(args.output).absolute()
    runtime = local_path(args.runtime)
    if output.parent != runtime or output.exists() or output.is_symlink():
        raise ValueError('Output must be a new private file directly inside the target runtime')
    def check(name, condition):
        cases.append({'case': name, 'passed': bool(condition)})
        print(('PASS ' if condition else 'FAIL ') + name, flush=True)
        if not condition: raise AssertionError('Recovery check failed')
    try:
        source, snapshot = local_path(args.source_runtime), local_path(args.snapshot)
        if len({source, snapshot, runtime}) != 3: raise ValueError('Source, snapshot and target must be distinct')
        for owned in (source, runtime):
            assert_mysql_owner(owned); assert_database(owned)
        if set(load_ports(source).values()) & set(load_ports(runtime).values()):
            raise ValueError('Source and target ports must be distinct')
        if not re.fullmatch(r'fixture_cloud_recovery_[A-Za-z0-9_-]{1,40}', args.project_id):
            raise ValueError('Only an explicitly synthetic cloud recovery project is accepted')
        proof_path = Path(args.old_session_record).absolute()
        if proof_path.parent != source: raise ValueError('Old session proof must belong to the source runtime')
        proof = json.loads(read_private(proof_path))
        if (set(proof) != {'token', 'actor', 'endpoint', 'source_verified_http'}
                or proof['actor'] != 'fixture_admin' or proof['endpoint'] != '/sys/permission/getUserPermissionByToken'
                or type(proof['source_verified_http']) is not int or proof['source_verified_http'] != 200
                or not isinstance(proof['token'], str) or not proof['token'] or len(proof['token']) > 8192
                or any(ord(c) < 33 or ord(c) > 126 for c in proof['token'])):
            raise ValueError('Old synthetic session proof is invalid')
        manifest = inspect_snapshot(snapshot)
        document = load_cloud(snapshot)
        check('format 2 bound cloud payload', manifest['format'] == 2 and manifest['redis'] == cloud_summary(document))
        result = json.loads(read_private(runtime / 'restore-result.json'))
        expected_summary = cloud_summary(document)
        check('restore completion records equal bytes and excludes sessions',
              result.get('snapshot_manifest_sha256') == sha256(snapshot / 'manifest.json')
              and result.get('runtime') == str(runtime) and result.get('database_equal') is True
              and result.get('attachments_equal') is True and result.get('cloud_data_present') is True
              and result.get('cloud_equal') is True and result.get('legacy_cloud_missing') is False
              and result.get('redis_sessions_restored') is False
              and result.get('cloud_keys') == expected_summary['keys'] and result.get('cloud_fields') == expected_summary['fields'])
        phase = 'source-read'
        with OwnedRedis(source) as client:
            check('source cloud bytes still equal snapshot', capture_cloud(client, project_ids(source)) == document)
            source_keys = key_inventory(client)
        excluded = {key for key in source_keys if not key.startswith(PREFIX)}
        check('source contains excluded synthetic cache sentinel', b'fixture:recovery:excluded' in excluded)
        aggregates.update(source_excluded_keys=len(excluded), source_excluded_keys_sha256=inventory_digest(excluded))
        phase = 'target-read-before-probes'
        with OwnedRedis(runtime) as client:
            check('target raw cloud key field value bytes equal snapshot', capture_cloud(client, project_ids(runtime)) == document)
            target_keys = key_inventory(client)
        check('target initially contains only restored cloud hashes',
              target_keys == {base64.b64decode(e['key_b64'], validate=True) for e in document['entries']})
        check('source login CAPTCHA and cache names were not restored', not (target_keys & excluded))
        aggregates.update(target_initial_keys=len(target_keys), cloud_keys=expected_summary['keys'], cloud_fields=expected_summary['fields'])
        # No context manager: FixtureApi.__exit__ logs out tokens. This probe never logs in.
        api = FixtureApi(runtime, args.jar)
        process_path = runtime / 'backend-process.json'
        if process_path.is_symlink() or not process_path.is_file(): raise ValueError('Backend process record must be ordinary')
        record = json.loads(process_path.read_text())
        command = subprocess.check_output(['ps', '-ww', '-p', str(record['pid']), '-o', 'command='], text=True).strip()
        process_args = shlex.split(command)
        listeners = subprocess.check_output(['lsof', '-nP', '-iTCP:' + str(api.ports['backend']), '-sTCP:LISTEN', '-Fp'], text=True)
        check('running exact JAR belongs to target local profile',
              '--spring.config.additional-location=file:' + str(runtime / 'config') + '/' in process_args
              and '--spring.profiles.active=dev,localtest' in process_args and str(Path(args.jar).resolve()) in process_args
              and {line[1:] for line in listeners.splitlines() if line.startswith('p')} == {str(record['pid'])}
              and result.get('ports') == api.ports)
        aggregates['jar_sha256'] = api.jar_sha256
        # The app may write local audit/scheduler rows; compare stable business tables.
        business = {name: row for name, row in manifest['database'].items()
                    if name.startswith('teaching_') or name == 'e_file'}
        before = database_inventory(runtime)
        check('restored business tables and attachment bytes match snapshot',
              bool(business) and all(before.get(n) == row for n, row in business.items())
              and file_inventory(runtime / 'uploads') == manifest['uploads'])
        project = args.project_id.encode()
        row = next((e for e in document['entries'] if base64.b64decode(e['key_b64']) == PREFIX + project), None)
        if row is None: raise ValueError('Synthetic public project is absent from cloud payload')
        expected = {}
        for name, value in row['fields']:
            decoded_name = base64.b64decode(name).decode('utf-8')
            decoded_value = json.loads(base64.b64decode(value).decode('utf-8'))
            if not isinstance(decoded_value, str): raise ValueError('This public proof requires Java string cloud values')
            expected[decoded_name] = decoded_value
        published = sql(runtime, "SELECT COUNT(*) FROM teachingopen_dev.teaching_work WHERE HEX(id)='" + project.hex().upper()
                        + "' AND work_status IN ('3','4') AND work_type IN ('1','2') AND (del_flag IS NULL OR del_flag<>1)")
        check('synthetic probe project is public and has expected three values', published == '1' and len(expected) == 3)
        phase = 'java-protocol'
        messages, acknowledged = handshake(api.ports['backend'], args.project_id)
        sets = [m for m in messages if m.get('method') == 'set']
        observed = {m.get('name'): m.get('value') for m in sets}
        check('anonymous Java handshake acknowledges complete restored values',
              acknowledged and any(m.get('method') == 'ack' and m.get('reply') == 'OK' for m in messages)
              and len(sets) == len(expected) and observed == expected
              and all(m.get('project_id') == args.project_id for m in sets)
              and not any('close' in m or m.get('closed') for m in messages))
        phase = 'old-session'
        check('formerly valid source admin session is rejected HTTP 401', old_session_rejected(api.ports['backend'], proof['token']))
        phase = 'after-read'
        with OwnedRedis(runtime) as client:
            check('read probes preserve raw cloud bytes', capture_cloud(client, project_ids(runtime)) == document)
        after = database_inventory(runtime)
        check('read probes preserve business tables and attachment bytes',
              all(before.get(n) == after.get(n) for n in business)
              and file_inventory(runtime / 'uploads') == manifest['uploads'])
        aggregates['business_tables'] = len(business)
        aggregates['handshake_set_messages'] = len(sets)
        phase = 'complete'
    except Exception as error:
        # Exceptions may contain credentials, raw rows or private paths: emit type only.
        error_type = type(error).__name__
    report = {'scope': 'Read-only owned synthetic local restore; actual anonymous Java handshake and stale-session HTTP; no login, mutation or browser acceptance',
              'cases': cases, 'passed': sum(c['passed'] for c in cases), 'total': len(cases),
              'completed': phase == 'complete', 'phase': phase, 'error_type': error_type,
              'aggregates': aggregates, 'script_sha256': sha256(Path(__file__)),
              'snapshot_manifest_sha256': sha256(snapshot / 'manifest.json') if 'snapshot' in locals() and (snapshot / 'manifest.json').is_file() else None}
    private_write(output, json.dumps(report, indent=2) + '\n')
    print(json.dumps({'completed': report['completed'], 'passed': report['passed'], 'total': report['total'], 'phase': phase, 'error_type': error_type}), flush=True)
    return report['completed'] and report['passed'] == report['total']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ('runtime', 'source-runtime', 'snapshot', 'jar', 'old-session-record', 'output'):
        parser.add_argument('--' + flag, type=Path, required=True)
    parser.add_argument('--project-id', required=True)
    raise SystemExit(0 if verify(parser.parse_args()) else 1)
