"""Frozen local artifacts and recoverable switching; macOS synthetic runtimes only."""
import contextlib
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time
from urllib.request import urlopen
from uuid import uuid4
import zipfile

from local_recovery import file_inventory, local_path, private_write, quote, sha256, sql
from local_runtime import assert_app_config, assert_database, load_ports


def schema_inventory(runtime):
    tables = sql(runtime, "SELECT TABLE_NAME FROM information_schema.tables WHERE TABLE_SCHEMA='teachingopen_dev' ORDER BY TABLE_NAME").splitlines()
    # AUTO_INCREMENT counters are data, not a schema migration.
    return {name: hashlib.sha256(re.sub(r' AUTO_INCREMENT=\d+', '', sql(runtime, 'SHOW CREATE TABLE teachingopen_dev.' + quote(name))).encode()).hexdigest() for name in tables}


def revision(repo):
    if subprocess.check_output(['git', '-C', str(repo), 'status', '--porcelain'], text=True).strip():
        raise ValueError('Package only clean source worktrees; preserve and commit changes first')
    return subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip()


def package(runtime, destination, backend_repo, frontend_repo):
    runtime, destination = local_path(runtime), local_path(destination, new=True)
    assert_app_config(runtime); assert_database(runtime)
    backend_repo, frontend_repo = Path(backend_repo).resolve(), Path(frontend_repo).resolve()
    provenance = {'backend_commit': revision(backend_repo), 'frontend_commit': revision(frontend_repo)}
    jar = backend_repo / 'api/jeecg-boot-module-system/target/teaching-open-2.8.0.jar'
    dist = frontend_repo / 'web/dist'
    if jar.is_symlink() or not zipfile.is_zipfile(jar) or not (dist / 'index.html').is_file():
        raise ValueError('Provide a built JAR and frontend index.html')
    before = file_inventory(dist); jar_hash = sha256(jar)
    schema = schema_inventory(runtime)
    destination.mkdir(mode=0o700)
    shutil.copy2(jar, destination / 'app.jar')
    shutil.copytree(dist, destination / 'web')
    (destination / 'runner').mkdir()
    for name in ('serve-frontend.py', 'local_runtime.py'):
        shutil.copy2(Path(__file__).with_name(name), destination / 'runner' / name)
    if (file_inventory(dist) != before or file_inventory(destination / 'web') != before
            or sha256(jar) != jar_hash or sha256(destination / 'app.jar') != jar_hash
            or revision(backend_repo) != provenance['backend_commit']
            or revision(frontend_repo) != provenance['frontend_commit']
            or schema_inventory(runtime) != schema):
        raise RuntimeError('Build inputs changed during packaging; incomplete directory retained')
    manifest = {'format': 1, 'kind': 'teachingopen-local-candidate', 'provenance': provenance,
                'build_provenance_note': 'Commits identify supplied clean worktrees; verify their build records separately. Packaging does not build or attest provenance.',
                'database_schema': schema, 'files': file_inventory(destination)}
    private_write(destination / 'candidate.json', json.dumps(manifest, indent=2) + '\n')
    # Discourage accidental rebuilds over the selected artifacts. This is not a
    # security boundary against their owner, who can deliberately chmod them.
    for directory, dirs, files in os.walk(destination, topdown=False):
        for name in files: (Path(directory) / name).chmod(0o400)
        Path(directory).chmod(0o500)
    return reference(destination)


def reference(bundle):
    return {'path': str(bundle), 'manifest_sha256': sha256(bundle / 'candidate.json')}


def inspect_bundle(ref):
    bundle = local_path(ref['path'])
    files = file_inventory(bundle)
    if files.get('candidate.json', {}).get('sha256') != ref['manifest_sha256']:
        raise ValueError('Candidate manifest changed')
    manifest = json.loads((bundle / 'candidate.json').read_text())
    files.pop('candidate.json')
    if (manifest.get('format') != 1 or manifest.get('kind') != 'teachingopen-local-candidate'
            or files != manifest.get('files') or not manifest.get('database_schema')
            or not {'app.jar', 'web/index.html', 'runner/serve-frontend.py', 'runner/local_runtime.py'} <= set(files)):
        raise ValueError('Candidate incomplete or artifact hashes changed')
    return manifest


def write_state(runtime, state):
    temporary = runtime / ('candidate-state-' + uuid4().hex + '.tmp')
    private_write(temporary, json.dumps(state, indent=2) + '\n')
    os.replace(temporary, runtime / 'candidate-state.json')


def read_state(runtime):
    path = runtime / 'candidate-state.json'
    return json.loads(path.read_text()) if path.exists() else {'status': 'stopped', 'active': None, 'previous': None}


@contextlib.contextmanager
def operation_lock(runtime):
    with os.fdopen(os.open(runtime / 'candidate.lock', os.O_RDWR | os.O_CREAT, 0o600), 'a') as lock:
        try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: raise RuntimeError('Another candidate operation is running')
        try: yield
        finally: fcntl.flock(lock, fcntl.LOCK_UN)


def process(pid):
    result = subprocess.run(['ps', '-p', str(pid), '-o', 'stat=', '-o', 'lstart=', '-o', 'command='], capture_output=True, text=True)
    fields = result.stdout.strip().split(None, 6)
    if result.returncode or not fields or fields[0].startswith('Z'): return None
    if len(fields) != 7: raise RuntimeError('Cannot identify process')
    return {'start': ' '.join(fields[1:6]), 'command': fields[6]}


def listeners(port):
    result = subprocess.run(['lsof', '-nP', '-iTCP:' + str(port), '-sTCP:LISTEN', '-Fp'], capture_output=True, text=True)
    if result.returncode not in (0, 1): raise RuntimeError('Cannot inspect local listener ownership')
    return {int(line[1:]) for line in result.stdout.splitlines() if re.fullmatch(r'p\d+', line)}


def owned_children(runtime, allowed):
    """Validate both processes/listeners before stopping either one."""
    found = {}
    ports = load_ports(runtime)
    for kind in ('backend', 'frontend'):
        path = runtime / (kind + '-process.json')
        meta = json.loads(path.read_text()) if path.exists() else None
        live = process(meta['pid']) if meta else None
        if live:
            bundle = next((Path(ref['path']) for ref in allowed if ref and (
                meta.get('jar_path') == str(Path(ref['path']) / 'app.jar') if kind == 'backend'
                else meta.get('dist_path') == str(Path(ref['path']) / 'web'))), None)
            if not bundle or meta.get('process_start') != live['start']:
                raise RuntimeError('Unowned or reused ' + kind + ' PID; refusing to stop it')
            needles = ([str(bundle / 'app.jar'), '--spring.profiles.active=dev,localtest', '--spring.config.additional-location=file:' + str(runtime / 'config') + '/'] if kind == 'backend'
                       else [str(bundle / 'runner/serve-frontend.py'), '--dist ' + str(bundle / 'web'), '--runtime ' + str(runtime)])
            if not all(n in live['command'] for n in needles): raise RuntimeError('Process command escaped candidate runtime')
            found[kind] = meta
        actual = listeners(ports[kind])
        if actual and actual != ({meta['pid']} if live else set()):
            raise RuntimeError('Port belongs to another process; refusing candidate operation')
    return found


def backend_run(runtime, java, action, jar):
    spec = importlib.util.spec_from_file_location('candidate_backend', Path(__file__).with_name('run-backend.py'))
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    module.run(runtime, java, action, None, jar=jar)


def stop_children(runtime, allowed, java):
    found = owned_children(runtime, allowed)
    if 'frontend' in found:
        pid = found['frontend']['pid']; os.kill(pid, signal.SIGTERM)
        for _ in range(40):
            if not process(pid): break
            time.sleep(.1)
        else: raise RuntimeError('Frontend did not stop; inspect its private log')
    if 'backend' in found:
        backend_run(runtime, java, 'stop', Path(found['backend']['jar_path']))
    if any(listeners(load_ports(runtime)[kind]) for kind in ('backend', 'frontend')):
        raise RuntimeError('Application ports did not close')


def start_candidate(runtime, ref, java, timeout):
    bundle = Path(ref['path']); manifest = inspect_bundle(ref)
    backend_run(runtime, java, 'start', bundle / 'app.jar')
    meta_path = runtime / 'backend-process.json'; meta = json.loads(meta_path.read_text())
    live = process(meta['pid'])
    if not live: raise RuntimeError('Candidate backend exited immediately')
    meta['process_start'] = live['start']; meta_path.write_text(json.dumps(meta, indent=2) + '\n')
    ports = load_ports(runtime); deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not process(meta['pid']): raise RuntimeError('Candidate backend exited before readiness')
        try:
            with urlopen('http://127.0.0.1:' + str(ports['backend']) + '/api/actuator/health', timeout=1) as response:
                if json.load(response).get('status') == 'UP': break
        except (OSError, ValueError): pass
        time.sleep(.25)
    else: raise RuntimeError('Candidate backend readiness timed out')
    log = runtime / 'logs' / ('candidate-frontend-' + uuid4().hex[:12] + '.log')
    with os.fdopen(os.open(log, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb') as out:
        child = subprocess.Popen([sys.executable, str(bundle / 'runner/serve-frontend.py'), '--dist', str(bundle / 'web'), '--runtime', str(runtime)], stdout=out, stderr=subprocess.STDOUT, start_new_session=True)
    live = process(child.pid)
    if not live: raise RuntimeError('Candidate frontend exited immediately')
    front = {'pid': child.pid, 'dist_path': str(bundle / 'web'), 'process_start': live['start'], 'log_path': str(log)}
    (runtime / 'frontend-process.json').write_text(json.dumps(front, indent=2) + '\n')
    deadline = time.monotonic() + min(timeout, 10)
    while time.monotonic() < deadline:
        if not process(child.pid): raise RuntimeError('Candidate frontend exited before readiness')
        try:
            with urlopen('http://127.0.0.1:' + str(ports['frontend']) + '/index.html', timeout=1) as response:
                if hashlib.sha256(response.read()).hexdigest() == manifest['files']['web/index.html']['sha256']: break
        except OSError: pass
        time.sleep(.1)
    else: raise RuntimeError('Candidate frontend readiness timed out')
    owned = owned_children(runtime, [ref])
    if set(owned) != {'backend', 'frontend'}: raise RuntimeError('Candidate processes not both live')


def activate(runtime, target, java, timeout=45, recover=False, rollback=False):
    runtime = local_path(runtime); java = Path(java).resolve()
    assert_app_config(runtime); assert_database(runtime)
    if not os.access(java / 'bin/java', os.X_OK): raise ValueError('Provide an executable Java runtime')
    with operation_lock(runtime):
        old = read_state(runtime)
        interrupted = old['status'] not in ('ready', 'stopped')
        if interrupted and not recover: raise RuntimeError('Interrupted operation; inspect status then run recover')
        if rollback:
            target = old.get('previous')
            if not target: raise ValueError('No previous candidate recorded')
        if recover:
            if not interrupted: raise ValueError('No interrupted switch to recover')
            target = old.get('active')
        if target is not None:
            manifest = inspect_bundle(target)
            if schema_inventory(runtime) != manifest['database_schema']:
                raise ValueError('Database schema differs; no automatic migration or downgrade is allowed')
        if old.get('active'):
            previous_manifest = inspect_bundle(old['active'])
            if schema_inventory(runtime) != previous_manifest['database_schema']:
                raise ValueError('Previous candidate is not schema compatible')
        allowed = [old.get('active'), old.get('target') if recover else None]
        owned_children(runtime, allowed)
        transition = dict(old, status='switching', target=target)
        write_state(runtime, transition)
        try:
            stop_children(runtime, allowed, java)
            if target: start_candidate(runtime, target, java, timeout)
        except (Exception, KeyboardInterrupt) as error:
            # Persist intent before starting anything; if killed, recover can
            # identify both old and attempted artifacts without trusting a PID.
            try:
                stop_children(runtime, allowed + [target], java)
                if old.get('active'): start_candidate(runtime, old['active'], java, timeout)
            except (Exception, KeyboardInterrupt):
                write_state(runtime, dict(transition, status='recovery-required'))
                raise RuntimeError('Switch and recovery failed; inspect private logs and run recover') from None
            write_state(runtime, dict(old, status='ready' if old.get('active') else 'stopped', last_failed=target))
            return {'status': 'failed_rolled_back' if old.get('active') else 'failed_stopped', 'active': old.get('active'), 'reason': str(error)}
        result = {'status': 'ready' if target else 'stopped', 'active': target,
                  'previous': old.get('previous') if recover or old.get('active') == target else old.get('active')}
        write_state(runtime, result)
        return result


def stop(runtime, java):
    runtime = local_path(runtime); assert_app_config(runtime)
    with operation_lock(runtime):
        state = read_state(runtime)
        if state['status'] not in ('ready', 'stopped'): raise RuntimeError('Recover interrupted operation before stopping')
        stop_children(runtime, [state.get('active')], Path(java).resolve())
        state['status'] = 'stopped'; write_state(runtime, state)
        return state


def status(runtime):
    runtime = local_path(runtime)
    state = read_state(runtime)
    children = owned_children(runtime, [state.get('active'), state.get('target')])
    ports = load_ports(runtime)
    observed = {kind: {'pid': meta['pid'], 'listening': listeners(ports[kind]) == {meta['pid']}} for kind, meta in children.items()}
    return {'recorded': state, 'observed': observed, 'both_processes_listening': len(observed) == 2 and all(p['listening'] for p in observed.values())}
