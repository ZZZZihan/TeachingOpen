#!/usr/bin/env python3
"""Release gate for editor dependencies and emitted browser runtime packages."""
import argparse
import hashlib
from datetime import date
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def dependency_paths(lock, roots):
    packages = lock['packages']
    found, pending = set(), ['node_modules/' + name for name in roots]
    while pending:
        path = pending.pop()
        if path in found:
            continue
        if path not in packages:
            raise ValueError('Missing locked runtime dependency: ' + path)
        found.add(path)
        node = packages[path]
        for name in set(node.get('dependencies', {})) | set(node.get('peerDependencies', {})):
            parent = path
            while True:
                candidate = (parent + '/' if parent else '') + 'node_modules/' + name
                if candidate in packages:
                    pending.append(candidate)
                    break
                if not parent:
                    if not node.get('peerDependenciesMeta', {}).get(name, {}).get('optional'):
                        raise ValueError('Unresolved rich-text dependency: ' + name)
                    break
                parent = parent.rsplit('/node_modules/', 1)[0] if '/node_modules/' in parent else ''
    return found


def check(lock, policy, audit, today=None, bundled=None):
    today = today or date.today()
    if audit.get('error') or not isinstance(audit.get('vulnerabilities'), dict):
        raise ValueError('Dependency audit did not produce a complete result')
    packages = lock['packages']
    for path in packages:
        if path.endswith('/tinymce') or path.endswith('/@tinymce/tinymce-vue'):
            raise ValueError('Removed vulnerable editor must not return to the release lockfile')
    graph = dependency_paths(lock, policy['runtime_roots'])
    if bundled is not None:
        if not isinstance(bundled, list) or not bundled or any(not isinstance(path, str) or path not in packages for path in bundled):
            raise ValueError('Invalid or empty production runtime inventory')
        graph.update(bundled)
    exceptions = {}
    for item in policy.get('exceptions', []):
        if not all(item.get(key) for key in ('package', 'advisory', 'owner', 'reason', 'expires')):
            raise ValueError('Dependency exception requires package, advisory, owner, reason and expiry')
        if date.fromisoformat(item['expires']) <= today:
            raise ValueError('Expired dependency exception: ' + item['package'])
        exceptions[(item['package'], item['advisory'])] = item
    blocked = []
    for name, finding in audit['vulnerabilities'].items():
        if finding.get('severity') not in ('high', 'critical') or not graph.intersection(finding.get('nodes', [])):
            continue
        via = finding.get('via', [])
        if not via or any(isinstance(item, str) and item not in audit['vulnerabilities'] for item in via):
            blocked.append(name)
            continue
        if any(isinstance(item, dict) and item.get('severity', finding['severity']) in ('high', 'critical') and not item.get('url') for item in via):
            blocked.append(name)
            continue
        # npm's aggregate severity can come solely from build-only dependencies.
        # Every emitted dependency is checked separately against its own advisories.
        advisories = [item['url'] for item in via if isinstance(item, dict)
                      and item.get('severity', finding['severity']) in ('high', 'critical') and item.get('url')]
        if any((name, url) not in exceptions for url in advisories):
            blocked.append(name)
    if blocked:
        raise ValueError('High-risk browser runtime dependencies: ' + ', '.join(sorted(blocked)))
    return {'status': 'passed', 'scope': 'editor graph and production browser modules' if bundled is not None else 'editor graph', 'locked_packages': len(graph),
            'exceptions': len(exceptions), 'whole_application_audit': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit-report', type=Path)
    parser.add_argument('--runtime-report', type=Path, default=ROOT / 'web/dist/runtime-dependencies.json')
    args = parser.parse_args()
    if args.audit_report:
        audit = json.loads(args.audit_report.read_text())
    else:
        result = subprocess.run(['npm', 'audit', '--json'], cwd=ROOT / 'web',
                                capture_output=True, text=True, timeout=180)
        if result.returncode not in (0, 1):
            raise RuntimeError('Registry audit failed')
        audit = json.loads(result.stdout)
    lock_bytes = (ROOT / 'web/package-lock.json').read_bytes()
    runtime = json.loads(args.runtime_report.read_text())
    if runtime.get('lock_sha256') != hashlib.sha256(lock_bytes).hexdigest():
        raise ValueError('Production runtime inventory does not match the current lockfile')
    if not isinstance(runtime.get('packages'), list) or not runtime['packages']:
        raise ValueError('Production runtime inventory requires a nonempty package list')
    result = check(json.loads(lock_bytes), json.loads((ROOT / 'ci/richtext-dependency-policy.json').read_text()),
                   audit, bundled=runtime.get('packages'))
    print(json.dumps(result))


if __name__ == '__main__':
    main()
