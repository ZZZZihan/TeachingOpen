#!/usr/bin/env python3
"""Package, activate, roll back, or recover local synthetic candidates."""
import argparse
import json
from pathlib import Path
from local_candidate import activate, package, reference, status, stop


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('package', 'activate', 'rollback', 'recover', 'stop', 'status'))
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--bundle', type=Path)
    parser.add_argument('--backend-repo', type=Path)
    parser.add_argument('--frontend-repo', type=Path)
    parser.add_argument('--java-home', type=Path)
    parser.add_argument('--timeout', type=int, default=45)
    args = parser.parse_args()
    if not 1 <= args.timeout <= 120: parser.error('timeout must be 1..120 seconds')
    runtime = args.runtime.absolute()
    if args.action == 'package':
        if not all((args.bundle, args.backend_repo, args.frontend_repo)): parser.error('package needs bundle, backend-repo, frontend-repo')
        result = package(runtime, args.bundle, args.backend_repo, args.frontend_repo)
    elif args.action == 'status': result = status(runtime)
    else:
        if not args.java_home: parser.error('provide java-home')
        if args.action == 'stop': result = stop(runtime, args.java_home)
        else:
            if args.action == 'activate':
                if not args.bundle: parser.error('activate needs bundle')
                target = reference(args.bundle.absolute())
            else:
                target = None
            result = activate(runtime, target, args.java_home, args.timeout, recover=args.action == 'recover', rollback=args.action == 'rollback')
    print(json.dumps(result, indent=2))
    if result.get('status', '').startswith('failed_'): raise SystemExit(1)


if __name__ == '__main__': main()
