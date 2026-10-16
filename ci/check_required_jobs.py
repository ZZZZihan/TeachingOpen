"""Accept only successful required jobs or explicitly planned unaffected skips."""

import json
import os
import re
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


def check(event_name, needs, *, reuse_proof=None, target_sha=None):
    if not isinstance(needs, dict):
        raise ValueError('Missing job results')
    if all(isinstance(needs.get(name), dict) and needs[name].get('result') == 'success' for name in JOBS):
        return
    # A source run is verified again online by main(), never by a boolean alone.
    if reuse_proof is not None:
        from ci_reuse import JOB_NAMES, positive, sha
        reuse = needs.get('reuse', {})
        proof = reuse_proof if isinstance(reuse_proof, dict) else {}
        ids = proof.get('source_job_ids', {})
        outputs = reuse.get('outputs', {}) if isinstance(reuse, dict) else {}
        valid = (event_name == 'push' and sha(target_sha) and type(proof.get('schema')) is int and proof['schema'] == 1
                 and proof.get('mode') == 'reused' and proof.get('target_sha') == target_sha
                 and sha(proof.get('source_sha')) and sha(proof.get('tree'))
                 and positive(proof.get('source_run_id')) and type(proof.get('source_run_attempt')) is int
                 and proof['source_run_attempt'] == 1
                 and isinstance(proof.get('source_url'), str)
                 and re.fullmatch(r'https://github.com/[\w.-]+/[\w.-]+/actions/runs/'
                                  + str(proof['source_run_id']), proof['source_url']) is not None
                 and positive(proof.get('pr_number')) and isinstance(ids, dict)
                 and set(ids) == set(JOB_NAMES) and all(positive(v) for v in ids.values())
                 and len(set(ids.values())) == len(JOB_NAMES)
                 and isinstance(reuse, dict) and reuse.get('result') == 'success'
                 and isinstance(outputs, dict) and outputs.get('reuse') == 'true')
        # Reuse can waive only tools/backend. The live dependency release gate
        # runs inside frontend and must succeed on this push.
        fresh_frontend = (isinstance(needs.get('frontend'), dict)
                          and needs['frontend'].get('result') == 'success')
        if not valid or not fresh_frontend or any(
                not isinstance(needs.get(name), dict)
                or needs[name].get('result') not in ('success', 'skipped')
                for name in ('backend', 'tools')):
            raise ValueError('CI required rejected invalid or mixed reuse evidence')
        return
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
        event = os.environ.get('CI_EVENT_NAME', '')
        needs = json.loads(os.environ.get('CI_NEEDS_JSON', ''))
        proof = None
        if event == 'push' and isinstance(needs, dict) and any(
                isinstance(needs.get(name), dict) and needs[name].get('result') == 'skipped'
                for name in JOBS):
            from ci_reuse import authorize
            proof = authorize(needs)
        check(event, needs, reuse_proof=proof, target_sha=os.environ.get('GITHUB_SHA'))
    except Exception as error:
        print(str(error) if isinstance(error, (ValueError, TypeError)) else type(error).__name__, file=sys.stderr)
        return 1
    print('CI required accepted successful jobs, unaffected PR skips, or fresh frontend plus revalidated tools/backend evidence.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
