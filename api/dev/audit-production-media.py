#!/usr/bin/env python3
"""Offline bounded media metadata audit of a private production fixture."""
import argparse
import json
from pathlib import Path
import sys

from production_media_audit import AuditFailure, audit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--ffprobe', type=Path, required=True, help='Exact ordinary executable real path')
    parser.add_argument('--pdfinfo', type=Path, required=True, help='Exact ordinary executable real path')
    args = parser.parse_args()
    try:
        result = audit(args.runtime, args.ffprobe, args.pdfinfo)
        print(json.dumps(result, sort_keys=True, indent=2))
        return 0 if result['passed'] else 1
    except AuditFailure as error:
        print(json.dumps({'completed': False, 'passed': False, 'error_code': error.code}), file=sys.stderr)
        return 1
    except (OSError, ValueError):
        # Paths, credentials, content, and child diagnostics are never printed.
        print(json.dumps({'completed': False, 'passed': False, 'error_code': 'audit_guard_or_io'}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
