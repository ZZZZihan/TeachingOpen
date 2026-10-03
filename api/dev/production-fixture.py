#!/usr/bin/env python3
"""Import or verify a private sanitized source copy; never start the application."""
import argparse
import json
from pathlib import Path
import sys
from production_fixture import create, verify

parser = argparse.ArgumentParser(description=__doc__)
commands = parser.add_subparsers(dest='action', required=True)
new = commands.add_parser('create')
new.add_argument('--source', type=Path, required=True)
new.add_argument('--runtime', type=Path, required=True)
new.add_argument('--tools', type=Path, required=True)
for name, port in {'mysql': 13346, 'redis': 16419, 'backend': 18141, 'frontend': 18142}.items():
    new.add_argument('--' + name + '-port', type=int, default=port)
check = commands.add_parser('verify')
check.add_argument('--runtime', type=Path, required=True)
args = parser.parse_args()
try:
    if args.action == 'create':
        result = create(args.source, args.runtime, args.tools,
                        {name: getattr(args, name + '_port') for name in ('mysql', 'redis', 'backend', 'frontend')})
    else:
        result = verify(args.runtime)
    print(json.dumps(result, indent=2))
except (ValueError, RuntimeError, OSError) as error:
    print(type(error).__name__ + ': ' + str(error), file=sys.stderr)
    sys.exit(1)
