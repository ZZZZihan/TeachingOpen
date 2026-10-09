#!/usr/bin/env python3
"""Read backup health and retain a checksum-verified private off-host database copy.

No credentials in arguments/output; uses the already configured Workbench profile.
The server's systemd timer runs independently of this optional local copy job.
"""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time


def sha256(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''): h.update(block)
    return h.hexdigest()


def read_state(command):
    # Workbench can transiently return an empty SSH output with exit_code=0.
    # Retry only this read-only request, never downloads or remote mutations.
    for attempt in range(2):
        try:
            r = subprocess.run(command, capture_output=True, text=True, timeout=60)
            result = json.loads(r.stdout)
            if r.returncode == 0 and result.get('exit_code') == 0 and result.get('output', '').strip():
                state = json.loads(result['output'])
                if isinstance(state, dict) and 'latest.json' in state:
                    return state
        except (subprocess.TimeoutExpired, ValueError):
            pass
        if attempt == 0:
            time.sleep(0.5)
    raise RuntimeError('Server backup status unavailable after one read-only retry')


def main():
    os.umask(0o077)
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--workbench', required=True)
    p.add_argument('--instance', required=True)
    p.add_argument('--profile', required=True)
    p.add_argument('--region', required=True)
    p.add_argument('--destination', required=True, type=Path)
    a = p.parse_args()
    root = a.destination.resolve()
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if root.stat().st_mode & 0o077: raise ValueError('Local backup directory must be private')
    command = [a.workbench, '--profile', a.profile, '--region', a.region]
    remote = """import json,subprocess
from pathlib import Path
r=Path('/srv/teachingopen/backups')
out={n:json.loads((r/n).read_text()) for n in ('latest.json','last-backup.json','last-verify.json')}
out['units']={n:subprocess.run(['systemctl','is-enabled',n],capture_output=True,text=True).stdout.strip() for n in ('teachingopen-backup.timer','teachingopen-backup-verify.timer')}
out['active']={n:subprocess.run(['systemctl','is-active',n],capture_output=True,text=True).stdout.strip() for n in ('teachingopen-backup.timer','teachingopen-backup-verify.timer','teachingopen-api.service','teachingopen-mysql.service')}
print(json.dumps(out))
"""
    state = read_state(command + ['exec', '--instance-id', a.instance, '--output', 'json',
        '--command', "python3 - <<'PYREMOTE'\n" + remote + '\nPYREMOTE'])
    latest = state['latest.json']
    name = latest['snapshot']
    if not re.fullmatch(r'\d{8}T\d{6}Z-[0-9a-f]{8}', name): raise ValueError('Unexpected snapshot name')
    if latest['status'] != 'complete' or state['last-backup.json']['status'] != 'complete': raise RuntimeError('Last backup failed')
    if datetime.now(timezone.utc) - datetime.fromisoformat(latest['created_at']) > timedelta(hours=8): raise RuntimeError('Backup is stale (>8h)')
    if state['last-verify.json']['status'] != 'passed': raise RuntimeError('Restore verification failed')
    if datetime.now(timezone.utc) - datetime.fromisoformat(state['last-verify.json']['checked_at']) > timedelta(hours=28): raise RuntimeError('Restore verification is stale (>28h)')
    if any(x != 'enabled' for x in state['units'].values()): raise RuntimeError('Backup timer disabled')
    if any(x != 'active' for x in state['active'].values()): raise RuntimeError('Backup timer or application is not active')
    target = root / (name + '.sql.gz')
    if target.exists():
        if target.is_symlink() or sha256(target) != latest['database_sha256']: raise RuntimeError('Existing local copy checksum mismatch')
        target.chmod(0o600)
    else:
        partial = root / (name + '.partial')
        if partial.exists(): raise RuntimeError('Partial local copy needs inspection')
        download = subprocess.run(command + ['download', '/srv/teachingopen/backups/' + name + '/database.sql.gz',
            str(partial), '--instance-id', a.instance], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=300)
        if download.returncode: raise RuntimeError('Off-host backup download failed')
        partial.chmod(0o600)
        if sha256(partial) != latest['database_sha256']: raise RuntimeError('Downloaded backup checksum mismatch')
        partial.rename(target)
    result = {'status':'passed', 'snapshot':name, 'sha256':latest['database_sha256'],
              'bytes':target.stat().st_size, 'copied_at':datetime.now(timezone.utc).isoformat(),
              'database_only':True, 'server_health':state}
    receipt = root / (name + '.json')
    receipt.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n'); receipt.chmod(0o600)
    print(json.dumps({k:v for k,v in result.items() if k != 'server_health'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
