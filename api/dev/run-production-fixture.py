#!/usr/bin/env python3
"""Explicitly launch/stop a reviewed private snapshot; default fixture guards stay intact."""
import argparse
import json
from pathlib import Path
import sys
from snapshot_backend import start, stop

parser = argparse.ArgumentParser(description=__doc__)
commands = parser.add_subparsers(dest='action', required=True)
launch = commands.add_parser('start')
launch.add_argument('--runtime', type=Path, required=True)
launch.add_argument('--java-home', type=Path, required=True)
launch.add_argument('--jar', type=Path, required=True)
launch.add_argument('--jar-sha256', required=True)
halt = commands.add_parser('stop')
halt.add_argument('--runtime', type=Path, required=True)
args = parser.parse_args()
try:
    result = start(args.runtime, args.java_home, args.jar, args.jar_sha256) if args.action == 'start' else stop(args.runtime)
    print(json.dumps(result, indent=2))
except (ValueError, RuntimeError, OSError) as error:
    print(type(error).__name__ + ': ' + str(error), file=sys.stderr); sys.exit(1)
