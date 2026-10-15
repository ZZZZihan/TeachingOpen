"""Select PR checks from their inputs; uncertainty always means the full suite."""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys


JOBS = ('frontend', 'backend', 'tools')
ROOT = Path(__file__).resolve().parents[1]
SHA = re.compile(r'[0-9a-f]{40}\Z')


def all_jobs():
    return dict.fromkeys(JOBS, True)


def classify_paths(paths):
    """Keep cross-directory readers together, including removed/renamed inputs.

    This is deliberately a conservative dependency map, not a test selector.
    A selected job still runs its complete existing checks. Unknown paths must
    not acquire an implicit exemption when new repository inputs are added.
    """
    if not paths:
        return all_jobs()
    selected = dict.fromkeys(JOBS, False)
    for path in paths:
        if (not isinstance(path, str) or not path or '\0' in path
                or any(part in ('', '.', '..') for part in path.split('/'))):
            return all_jobs()
        root = path.split('/')[0]
        if '/' not in path or root not in {
                'web', 'api', 'ci', 'deploy', 'examples', '资料', 'docs', 'evidence'}:
            return all_jobs()
        if root == 'ci':
            return all_jobs()
        if root in ('api', 'deploy'):
            # Python tools enumerate Java tests and load the actual HTTP probes;
            # backend setup and proxy checks also consume deployment inputs.
            selected['backend'] = selected['tools'] = True
        elif root in ('web', 'examples'):
            selected['frontend'] = True
            # The API probe imports this web-side live HTTP implementation.
            if path == 'web/tests/public-boundaries-live.py':
                selected['backend'] = True
            # HTTPS/candidate tests and the global-rule SQL test read these.
            if (path.startswith('web/nginx/')
                    or path == 'web/src/views/system/modules/DepartModal.vue'):
                selected['tools'] = True
        elif root == '资料':
            # The isolated HTTPS checks read the historical nginx example.
            selected['tools'] = True
        # docs/ and evidence/ are not inputs to the current CI jobs.
    return selected


def full_plan(reason):
    return {'mode': 'full', 'reason': reason, 'jobs': all_jobs(), 'paths': []}


def git(repository, *arguments):
    return subprocess.run(
        ['git', *arguments], cwd=repository, check=True, capture_output=True,
        timeout=60,
    ).stdout


def select_for_event(event_name, event, repository, ref):
    if event_name != 'pull_request':
        return full_plan('Only pull_request events may skip jobs')
    try:
        pr = event['pull_request']
        base, head = pr['base']['sha'], pr['head']['sha']
        if not all(isinstance(value, str) and SHA.fullmatch(value)
                   for value in (base, head, ref)):
            raise ValueError('Missing or invalid immutable commit identifiers')
        checked_out = git(repository, 'rev-parse', 'HEAD').decode().strip()
        parents = git(repository, 'show', '-s', '--format=%P', ref).decode().split()
        if checked_out != ref or parents != [base, head]:
            raise ValueError('Checkout is not the merge candidate for this PR event')
        if len(git(repository, 'merge-base', '--all', base, head).split()) != 1:
            raise ValueError('PR does not have one unambiguous merge base')
        # NUL separators preserve spaces/newlines/non-ASCII names. Disabling
        # rename detection includes both deleted and added paths across domains.
        raw = git(repository, 'diff', '--name-only', '-z', '--no-renames',
                  base + '...' + head, '--')
        if raw and not raw.endswith(b'\0'):
            raise ValueError('Incomplete changed-path data')
        paths = [os.fsdecode(path) for path in raw.split(b'\0') if path]
        if not paths:
            return full_plan('Empty diff is not proof that checks are unnecessary')
        return {'mode': 'selective', 'reason': 'Verified PR merge candidate',
                'jobs': classify_paths(paths), 'paths': paths}
    except (KeyError, TypeError, ValueError, OSError, subprocess.SubprocessError) as error:
        # Do not emit exception text: it may include filenames or event content.
        return full_plan('Cannot safely classify PR (' + type(error).__name__ + ')')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--event-name', default=os.environ.get('GITHUB_EVENT_NAME', ''))
    parser.add_argument('--event-path', default=os.environ.get('GITHUB_EVENT_PATH'))
    parser.add_argument('--repository', type=Path, default=ROOT)
    parser.add_argument('--ref', default=os.environ.get('GITHUB_SHA', ''))
    args = parser.parse_args()
    try:
        event = json.loads(Path(args.event_path).read_text()) if args.event_path else {}
        plan = select_for_event(args.event_name, event, args.repository, args.ref)
    except (OSError, ValueError, TypeError):
        plan = full_plan('Cannot read the PR event; running all checks')
    print(json.dumps(plan, ensure_ascii=True, sort_keys=True))
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as output:
            output.write('mode=' + plan['mode'] + '\n')
            output.writelines(name + '=' + str(plan['jobs'][name]).lower() + '\n'
                              for name in JOBS)
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8') as summary:
            summary.write('### CI job selection\n\n' + plan['reason'] + '\n\n')
            summary.write('Changed paths: ' + str(len(plan['paths'])) + '\n\n')
            for name in JOBS:
                summary.write('- ' + name + ': '
                              + ('run' if plan['jobs'][name] else 'unaffected') + '\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
