"""Explicit process lifecycle for the dedicated private snapshot runtime."""
import json
import os
from pathlib import Path
import re
import signal
import socket
import subprocess
import time
from uuid import uuid4

from local_recovery import local_path, private_write, sha256
from local_runtime import load_ports
from production_fixture import verify, read_private


def validate_jar(jar, expected_sha256):
    jar = Path(jar).absolute()
    if jar.is_symlink() or not jar.is_file() or not re.fullmatch('[0-9a-f]{64}', expected_sha256) or sha256(jar) != expected_sha256:
        raise ValueError('Provide an ordinary built JAR and its exact expected SHA256')
    return jar


def process_identity(pid):
    result = subprocess.run(['ps', '-ww', '-p', str(pid), '-o', 'lstart=', '-o', 'command='], capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else None


def config_argument(runtime):
    return '--spring.config.additional-location=file:' + str(runtime / 'config') + '/'


def start(runtime, java_home, jar, expected_sha256):
    runtime = local_path(runtime)
    java_home = Path(java_home).absolute()
    jar = validate_jar(jar, expected_sha256)
    if not os.access(java_home / 'bin/java', os.X_OK): raise ValueError('Provide an executable Java runtime')
    # Full baseline, source/policy/configuration binding, MySQL/Redis ownership,
    # anonymous accounts, cleared tables and selected media before any Popen.
    verified = verify(runtime)
    for name in ('backend-process.json', 'backend.pid'):
        target = runtime / name
        if target.is_symlink() or (target.exists() and not target.is_file()):
            raise ValueError('Lifecycle records must be ordinary private files')
    recorded = runtime / 'backend-process.json'
    if recorded.exists():
        old = json.loads(read_private(recorded))
        if process_identity(old['pid']) is not None: raise ValueError('A recorded backend PID is still live; stop explicitly first')
    with socket.socket() as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        probe.bind(('127.0.0.1', load_ports(runtime)['backend']))
    log = runtime / 'logs' / ('snapshot-backend-' + uuid4().hex[:12] + '.log')
    private_write(log, b'')
    args = [str(java_home / 'bin/java'), '-Xms256m', '-Xmx1g', '-jar', str(jar),
            '--spring.profiles.active=dev,localtest', config_argument(runtime)]
    with log.open('ab') as output:
        process = subprocess.Popen(args, cwd=runtime / 'webapp', stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
    identity = process_identity(process.pid)
    if identity is None: raise RuntimeError('Backend exited immediately; inspect its private log')
    metadata = {'pid': process.pid, 'identity': identity, 'jar_path': str(jar), 'jar_sha256': expected_sha256,
                'profile': 'dev,localtest', 'config_argument': config_argument(runtime), 'log_path': str(log),
                'snapshot_manifest_sha256': verified['manifest_sha256']}
    # Lifecycle records can be replaced after a clean prior exit. Fixture data,
    # source files, manifest and private credentials are never rewritten here.
    try:
        for name, content in [('backend-process.json', json.dumps(metadata, indent=2) + '\n'), ('backend.pid', str(process.pid) + '\n')]:
            target = runtime / name
            temporary = runtime / (name + '.' + uuid4().hex + '.tmp')
            private_write(temporary, content); os.replace(temporary, target)
    except OSError:
        process.terminate(); process.wait(timeout=20)
        raise
    return {'pid': process.pid, 'jar_sha256': expected_sha256, 'backend_port': load_ports(runtime)['backend'],
            'launched': True, 'healthy': False, 'business_verified': False}


def stop(runtime):
    runtime = local_path(runtime)
    record_path = runtime / 'backend-process.json'
    if not record_path.exists(): return {'stopped': False, 'reason': 'no recorded backend'}
    record = json.loads(read_private(record_path))
    if (record.get('profile') != 'dev,localtest' or record.get('config_argument') != config_argument(runtime)
            or record.get('snapshot_manifest_sha256') != sha256(runtime / 'snapshot-manifest.json')):
        raise ValueError('Backend record belongs to another snapshot runtime')
    identity = process_identity(record['pid'])
    if identity is None: return {'stopped': False, 'reason': 'recorded backend already exited'}
    if (identity != record.get('identity') or record['jar_path'] not in identity
            or '--spring.profiles.active=dev,localtest' not in identity or config_argument(runtime) not in identity):
        raise ValueError('Recorded PID identity changed; refusing to stop an unknown process')
    os.kill(record['pid'], signal.SIGTERM)
    for _ in range(80):
        if process_identity(record['pid']) is None: return {'stopped': True, 'pid': record['pid']}
        time.sleep(.25)
    raise RuntimeError('Snapshot backend did not exit after SIGTERM; inspect its private log')
