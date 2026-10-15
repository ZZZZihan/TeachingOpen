"""Accept only successful required jobs or explicitly planned unaffected skips."""

import json
import os
import sys


JOBS = ('frontend', 'backend', 'tools')


def normalize_plan(plan):
    """Validate outside GitHub expressions, whose string comparisons ignore case."""
    plan = plan if isinstance(plan, dict) else {}
    outputs = plan.get('outputs', {})
    outputs = outputs if isinstance(outputs, dict) else {}
    valid = (plan.get('outcome') == 'success' and outputs.get('mode') == 'selective'
             and all(outputs.get(name) in ('true', 'false') for name in JOBS))
    return {'selective': str(valid).lower(),
            **{name: outputs[name] if valid else 'true' for name in JOBS}}


def check(event_name, needs):
    if not isinstance(needs, dict):
        raise ValueError('Missing job results')
    changes = needs.get('changes', {})
    changes = changes if isinstance(changes, dict) else {}
    outputs = changes.get('outputs', {})
    outputs = outputs if isinstance(outputs, dict) else {}
    selective = (
        event_name == 'pull_request' and changes.get('result') == 'success'
        and outputs.get('selective') == 'true'
        and all(outputs.get(name) in ('true', 'false') for name in JOBS)
    )
    failures = []
    for name in JOBS:
        job = needs.get(name, {})
        result = job.get('result') if isinstance(job, dict) else None
        required = not selective or outputs[name] == 'true'
        if result != 'success' and not (not required and result == 'skipped'):
            failures.append(name + ': ' + str(result)
                            + (' (required)' if required else ' (unaffected)'))
    if failures:
        raise ValueError('CI required rejected: ' + '; '.join(failures))


def main():
    if sys.argv[1:] == ['--normalize']:
        try:
            plan = json.loads(os.environ.get('CI_PLAN_JSON', ''))
        except (ValueError, TypeError):
            plan = None
        outputs = normalize_plan(plan)
        print(json.dumps(outputs, sort_keys=True))
        if os.environ.get('GITHUB_OUTPUT'):
            with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as stream:
                stream.writelines(name + '=' + value + '\n'
                                  for name, value in outputs.items())
        return 0
    try:
        check(os.environ.get('CI_EVENT_NAME', ''),
              json.loads(os.environ.get('CI_NEEDS_JSON', '')))
    except (ValueError, TypeError) as error:
        print(str(error), file=sys.stderr)
        return 1
    print('Every required job succeeded; any skips were explicitly planned.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
