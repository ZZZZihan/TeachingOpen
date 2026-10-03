#!/usr/bin/env python3
"""Create/verify opt-in synthetic UI flows in a fresh, cold role-flow-* runtime."""
import argparse
import json
from pathlib import Path
import sys

from role_flow_fixture import create, verify


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('create', 'verify'))
    parser.add_argument('--runtime', type=Path, required=True)
    args = parser.parse_args()
    try:
        result = (create if args.action == 'create' else verify)(args.runtime)
    except (ValueError, RuntimeError, OSError) as error:
        print('Role-flow fixture refused: ' + str(error), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
