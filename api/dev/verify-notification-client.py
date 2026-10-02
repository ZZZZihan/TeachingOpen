#!/usr/bin/env python3
"""Run the shipped JS notification client against the guarded synthetic backend."""
import argparse
import json
from pathlib import Path
import subprocess
from local_http import FixtureApi
from local_recovery import database_inventory, file_inventory, private_write

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--runtime', type=Path, required=True)
parser.add_argument('--jar', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
with FixtureApi(args.runtime, args.jar) as api:
    before, files = database_inventory(api.runtime), file_inventory(api.runtime / 'uploads')
    api.login('admin'); api.login('student_a')
    script = Path(__file__).resolve().parents[2] / 'web/tests/notification-client-live.mjs'
    process = subprocess.run(['node', str(script)], input=json.dumps({'baseUrl': 'http://127.0.0.1:' + str(api.ports['backend']) + '/api',
                              'userId': 'fixture_student_a', 'token': api.tokens['student_a'], 'adminToken': api.tokens['admin']}),
                             capture_output=True, text=True, timeout=20)
    if process.returncode:
        # Never echo a failed child output which might contain a credential.
        raise RuntimeError('Live notification client failed with exit ' + str(process.returncode))
    result = json.loads(process.stdout)
    result['jar_sha256'] = api.jar_sha256
    after = database_inventory(api.runtime)
    result['cases'].append({'case': 'all non-audit-log tables unchanged', 'passed': all(before[t] == after[t] for t in before if t != 'sys_log')})
    result['cases'].append({'case': 'all attachment bytes unchanged', 'passed': files == file_inventory(api.runtime / 'uploads')})
    result['total'] = len(result['cases']); result['passed'] = sum(c['passed'] for c in result['cases'])
private_write(args.output, json.dumps(result, indent=2) + '\n')
print(str(result['passed']) + '/' + str(result['total']) + ' real client checks passed')
raise SystemExit(0 if result['passed'] == result['total'] else 1)
