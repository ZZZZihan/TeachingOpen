#!/usr/bin/env python3
"""Cold backup of owned synthetic DB/uploads/persistent Scratch hashes; never overwrite a target.

Only DB 1 scratch:cloud:* hashes are included. Expiring, orphaned, wrong-type or
oversized hashes fail explicitly. Authentication/cache keys are never restored.
Format 1 is readable, but has no cloud data. Not a production/online restore tool.
"""
import argparse
import json
from pathlib import Path
from local_recovery import create_snapshot, inspect_snapshot, restore_snapshot
from local_runtime import DEFAULT_PORTS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='action', required=True)
    create = commands.add_parser('create')
    create.add_argument('--runtime', type=Path, required=True)
    create.add_argument('--snapshot', type=Path, required=True)
    inspect = commands.add_parser('inspect')
    inspect.add_argument('--snapshot', type=Path, required=True)
    restore = commands.add_parser('restore')
    restore.add_argument('--snapshot', type=Path, required=True)
    restore.add_argument('--runtime', type=Path, required=True)
    restore.add_argument('--tools', type=Path, required=True)
    for name in DEFAULT_PORTS:
        restore.add_argument('--' + name + '-port', type=int, required=True)
    args = parser.parse_args()
    if args.action == 'create':
        result = create_snapshot(args.runtime, args.snapshot)
    elif args.action == 'restore':
        result = restore_snapshot(args.snapshot, args.runtime, args.tools, {n: getattr(args, n + '_port') for n in DEFAULT_PORTS})
    else:
        manifest = inspect_snapshot(args.snapshot)
        has_cloud = manifest['format'] == 2
        result = {'valid': True, 'format': manifest['format'], 'tables': len(manifest['database']), 'files': len(manifest['uploads']),
                  'cloud_data_present': has_cloud, 'cloud_keys': manifest['redis']['keys'] if has_cloud else 0,
                  'cloud_fields': manifest['redis']['fields'] if has_cloud else 0, 'legacy_cloud_missing': not has_cloud,
                  'redis_sessions_restored': False}
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
