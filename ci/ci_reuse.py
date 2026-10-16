"""Reuse complete, recent PR evidence for an identical main tree; fail closed.

Receipts describe the original execution. They never rewrite test reports or claim
that tests ran again on the target commit. Every authorization is rechecked online.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from zoneinfo import ZoneInfo

from reuse_environment import installed_packages_digest, verify_environment_contract

JOBS = ('frontend', 'tools', 'backend')
JOB_NAMES = {'frontend': 'Frontend tests and build', 'tools': 'Backup and migration tools',
             'backend': 'Backend and MySQL registration', 'required': 'CI required'}
WORKFLOW = '.github/workflows/ci.yml'
TTL = timedelta(hours=6)
MAX_ZIP = 256 * 1024
MAX_JSON = 64 * 1024
RUNTIMES = {'frontend': {'node': 'v26.7.0', 'npm': '11.19.0'},
            'tools': {'python': '3.12.15', 'java': '1.8.0_504-b01'},
            'backend': {'python': '3.12.15', 'java': '1.8.0_504-b01',
                        'mysql': 'sha256:7dcddc01f13bab2f15cde676d44d01f61fc9f99fe7785e86196dfc07d358ae2b',
                        'redis': 'sha256:46f15cf64fdef63e483dcda99e74e3d51c017b1175547b6bb874152ee2391aad'}}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def timestamp(value):
    require(isinstance(value, str), 'Missing timestamp')
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    require(parsed.tzinfo is not None, 'Timestamp lacks timezone')
    return parsed


def sha(value):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{40}', value) is not None


def positive(value):
    return type(value) is int and value > 0


def object_pairs(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'Duplicate JSON key')
        result[key] = value
    return result


def parse_json(data):
    return json.loads(data, object_pairs_hook=object_pairs)


def _read_receipt_zip(data):
    require(len(data) <= MAX_ZIP, 'Receipt archive too large')
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        members = archive.infolist()
        require(len(members) == 1 and members[0].filename == 'receipt.json',
                'Receipt archive must contain only receipt.json')
        require(members[0].file_size <= MAX_JSON and not members[0].is_dir(),
                'Receipt too large')
        result = parse_json(archive.read(members[0]))
    require(isinstance(result, dict), 'Receipt is not an object')
    return result


def read_receipt_zip(data):
    try:
        return _read_receipt_zip(data)
    except (zipfile.BadZipFile, UnicodeError, TypeError, KeyError, RuntimeError) as error:
        raise ValueError('Malformed receipt archive') from error


def validate_evidence(target, pr, run, jobs, receipts, now):
    try:
        require(all(isinstance(obj, dict) for obj in (target, pr, run, receipts)),
                'Malformed evidence object')
        require(isinstance(now, datetime) and now.tzinfo is not None, 'Invalid verification time')
        return _validate_evidence(target, pr, run, jobs, receipts, now)
    except (TypeError, KeyError, AttributeError, OverflowError) as error:
        raise ValueError('Malformed evidence field') from error


def _validate_evidence(target, pr, run, jobs, receipts, now):
    """Pure proof validation; API discovery/download and Git validation are separate."""
    require(target.get('event') == 'push' and target.get('ref') == 'refs/heads/main',
            'Only main pushes may reuse evidence')
    require(all(sha(target.get(k)) for k in ('sha', 'tree', 'workflow_blob')),
            'Invalid target identity')
    require(positive(target.get('repository_id')) and positive(target.get('workflow_id')),
            'Invalid repository/workflow identity')
    require(re.fullmatch(r'[\w.-]+/[\w.-]+', target.get('repository', '')) is not None,
            'Invalid repository name')
    require(target.get('image_os') == 'ubuntu22' and
            re.fullmatch(r'[0-9]+(?:\.[0-9]+)+', target.get('image_version', '')) is not None,
            'Unknown runner image')
    repo = {'id': target['repository_id'], 'full_name': target['repository']}

    def same_repo(value):
        return isinstance(value, dict) and all(value.get(k) == v for k, v in repo.items())

    require(positive(pr.get('number')) and pr.get('state') == 'closed' and pr.get('merged') is True
            and pr.get('merge_commit_sha') == target['sha'], 'PR was not merged into this commit')
    require(pr.get('base', {}).get('ref') == 'main' and same_repo(pr['base'].get('repo'))
            and same_repo(pr.get('head', {}).get('repo')), 'PR must be same-repository into main')
    require(sha(pr['base'].get('sha')) and sha(pr['head'].get('sha')), 'Invalid PR commits')
    require(positive(run.get('id')) and type(run.get('run_attempt')) is int
            and run['run_attempt'] == 1, 'Only an unmixed first attempt is reusable')
    require(run.get('event') == 'pull_request' and run.get('status') == 'completed'
            and run.get('conclusion') == 'success', 'Source PR run is not successful')
    require(run.get('workflow_id') == target['workflow_id'] and run.get('path') == WORKFLOW
            and run.get('head_sha') == pr['head']['sha']
            and same_repo(run.get('repository')) and same_repo(run.get('head_repository')),
            'Source workflow/repository/head mismatch')
    created, finished = timestamp(run.get('created_at')), timestamp(run.get('updated_at'))
    require(created <= finished <= now and now - created <= TTL, 'Source run expired or future-dated')
    require(created.astimezone(ZoneInfo('Asia/Shanghai')).date()
            == now.astimezone(ZoneInfo('Asia/Shanghai')).date(), 'Business date changed')
    require(isinstance(jobs, list) and isinstance(receipts, dict), 'Missing source evidence')
    require(set(receipts) == set(JOBS), 'Incomplete receipt set')
    allowed = set(JOB_NAMES.values()) | {'Select affected PR jobs', 'Verify identical-tree PR evidence'}
    require(all(isinstance(j, dict) and j.get('name') in allowed for j in jobs),
            'Unknown additional source jobs require a fresh suite')
    job_ids, source_sha, source_base = {}, None, None
    for key, name in JOB_NAMES.items():
        matches = [j for j in jobs if isinstance(j, dict) and j.get('name') == name]
        require(len(matches) == 1, 'Missing or duplicate source job: ' + key)
        job = matches[0]
        require(positive(job.get('id')) and job.get('status') == 'completed'
                and job.get('conclusion') == 'success' and job.get('run_id') == run['id']
                and type(job.get('run_attempt')) is int and job['run_attempt'] == 1,
                'Source job did not execute successfully in this attempt: ' + key)
        start, end = timestamp(job.get('started_at')), timestamp(job.get('completed_at'))
        require(created <= start <= end <= finished, 'Source job time mismatch')
        job_ids[key] = job['id']
        if key == 'required':
            continue
        receipt = receipts[key]
        require(isinstance(receipt, dict), 'Invalid receipt')
        base_sha = receipt.get('base_sha')
        require(sha(base_sha) and (source_base is None or source_base == base_sha),
                'Inconsistent original PR base commit')
        source_base = base_sha
        expected = dict(schema=1, mode='fresh', job=key, repository=target['repository'],
                        repository_id=target['repository_id'], run_id=run['id'], run_attempt=1,
                        event='pull_request', pr_number=pr['number'], head_sha=pr['head']['sha'],
                        base_sha=base_sha, tree=target['tree'],
                        parents=[base_sha, pr['head']['sha']],
                        workflow_blob=target['workflow_blob'], image_os=target['image_os'],
                        image_version=target['image_version'], runtimes=RUNTIMES[key])
        require(all(type(receipt.get(k)) is type(v) and receipt[k] == v
                    for k, v in expected.items()), 'Receipt mismatch: ' + key)
        actual = receipt.get('checkout_sha')
        require(sha(actual) and (source_sha is None or source_sha == actual),
                'Inconsistent actual tested merge commit')
        source_sha = actual
        require(start <= timestamp(receipt.get('recorded_at')) <= end,
                'Receipt is outside its job execution')
    require(len(set(job_ids.values())) == len(job_ids), 'Duplicate source job IDs')
    return dict(schema=1, mode='reused', target_sha=target['sha'], source_sha=source_sha,
                tree=target['tree'], source_run_id=run['id'], source_run_attempt=1,
                pr_number=pr['number'], source_job_ids=job_ids,
                source_url='https://github.com/' + target['repository'] + '/actions/runs/' + str(run['id']))


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class GitHub:
    def __init__(self):
        require(os.environ.get('GITHUB_API_URL') == 'https://api.github.com', 'Unsupported GitHub host')
        token = os.environ.get('GH_TOKEN', '')
        require(bool(token), 'Missing Actions read token')
        self.headers = {'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.github+json',
                        'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'TeachingOpen-CI-evidence'}
        self.opener = urllib.request.build_opener(NoRedirect())

    def request(self, path, limit=2 * 1024 * 1024):
        require(path.startswith('/repos/') and '\n' not in path, 'Invalid API path')
        req = urllib.request.Request('https://api.github.com' + path, headers=self.headers)
        with self.opener.open(req, timeout=30) as response:
            data = response.read(limit + 1)
        require(len(data) <= limit, 'API response too large')
        return parse_json(data)

    def download(self, path):
        req = urllib.request.Request('https://api.github.com' + path, headers=self.headers)
        try:
            self.opener.open(req, timeout=30)
        except urllib.error.HTTPError as error:
            require(error.code == 302, 'Artifact redirect unavailable')
            url = error.headers.get('Location', '')
        else:
            raise ValueError('Artifact download did not redirect')
        parts = urllib.parse.urlsplit(url)
        require(parts.scheme == 'https' and parts.hostname and not parts.username and not parts.password,
                'Invalid artifact download URL')
        # A signed storage URL receives no GitHub authorization header. No further redirects.
        with self.opener.open(urllib.request.Request(url), timeout=30) as response:
            data = response.read(MAX_ZIP + 1)
        require(len(data) <= MAX_ZIP, 'Artifact too large')
        return data

    def bounded_list(self, path, field=None):
        data = self.request(path + ('&' if '?' in path else '?') + 'per_page=100')
        result = data[field] if field else data
        require(isinstance(result, list) and len(result) < 100, 'Incomplete or oversized API page')
        if field:
            require(data.get('total_count') == len(result), 'Incomplete API result')
        return result


def command(*args):
    return subprocess.check_output(args, text=True, stderr=subprocess.PIPE).strip()


def local_identity():
    actual = command('git', 'rev-parse', 'HEAD')
    require(actual == os.environ.get('GITHUB_SHA') and sha(actual), 'Checkout does not match event SHA')
    require(os.environ.get('GITHUB_WORKFLOW_SHA') == actual, 'Executed workflow does not match checkout')
    return {'sha': actual, 'tree': command('git', 'rev-parse', 'HEAD^{tree}'),
            'workflow_blob': command('git', 'rev-parse', 'HEAD:' + WORKFLOW),
            'image_os': os.environ.get('ImageOS', ''), 'image_version': os.environ.get('ImageVersion', ''),
            'repository': os.environ.get('GITHUB_REPOSITORY', ''),
            'repository_id': int(os.environ.get('GITHUB_REPOSITORY_ID', '0'))}


def event_payload():
    return parse_json(Path(os.environ['GITHUB_EVENT_PATH']).read_text())


def target_context(api):
    require(os.environ.get('GITHUB_EVENT_NAME') == 'push' and
            os.environ.get('GITHUB_REF') == 'refs/heads/main', 'Not a main push')
    target = local_identity()
    payload = event_payload()
    require(payload.get('after') == target['sha'] and payload.get('deleted') is False
            and payload.get('forced') is False, 'Unknown or forced push')
    require(payload.get('repository', {}).get('id') == target['repository_id'], 'Event repository mismatch')
    verify_environment_contract(Path.cwd())
    current = api.request('/repos/' + target['repository'] + '/actions/runs/' + os.environ['GITHUB_RUN_ID'])
    require(current.get('head_sha') == target['sha'] and current.get('event') == 'push'
            and current.get('path') == WORKFLOW, 'Current workflow mismatch')
    target.update(event='push', ref='refs/heads/main', workflow_id=current['workflow_id'])
    return target


def resolve(api, target, source_run_id=None):
    prefix = '/repos/' + target['repository']
    associated = api.bounded_list(prefix + '/commits/' + target['sha'] + '/pulls')
    candidates = [p for p in associated if p.get('merge_commit_sha') == target['sha']
                  and p.get('merged_at') and p.get('base', {}).get('ref') == 'main']
    require(len(candidates) == 1, 'No unique merged PR for target')
    pr = api.request(prefix + '/pulls/' + str(candidates[0]['number']))
    runs = api.bounded_list(prefix + '/actions/workflows/' + str(target['workflow_id'])
                           + '/runs?event=pull_request&head_sha=' + pr['head']['sha'], 'workflow_runs')
    require(bool(runs), 'No PR run')
    # Do not filter by success: a newer failed/incomplete run supersedes old green evidence.
    run = max(runs, key=lambda r: (timestamp(r['created_at']), r['id']))
    if source_run_id is not None:
        require(run['id'] == source_run_id, 'Source run changed after selection')
    run = api.request(prefix + '/actions/runs/' + str(run['id']))
    require(run.get('run_attempt') == 1, 'Rerun evidence is deliberately not reused')
    base = prefix + '/actions/runs/' + str(run['id'])
    jobs = api.bounded_list(base + '/attempts/1/jobs', 'jobs')
    artifacts = api.bounded_list(base + '/artifacts', 'artifacts')
    receipts = {}
    for job in JOBS:
        name = 'ci-fresh-' + job + '-' + str(run['id']) + '-1'
        matches = [a for a in artifacts if a.get('name') == name]
        require(len(matches) == 1, 'Missing/duplicate receipt artifact: ' + job)
        artifact = matches[0]
        origin = artifact.get('workflow_run', {})
        require(artifact.get('expired') is False and 0 < artifact.get('size_in_bytes', 0) <= MAX_ZIP
                and origin.get('id') == run['id'] and origin.get('repository_id') == target['repository_id']
                and origin.get('head_repository_id') == target['repository_id']
                and origin.get('head_sha') == pr['head']['sha'], 'Artifact origin mismatch')
        data = api.download(prefix + '/actions/artifacts/' + str(artifact['id']) + '/zip')
        require(artifact.get('digest') == 'sha256:' + hashlib.sha256(data).hexdigest(),
                'Artifact digest mismatch')
        receipts[job] = read_receipt_zip(data)
    proof = validate_evidence(target, pr, run, jobs, receipts, datetime.now(timezone.utc))
    commit = api.request(prefix + '/git/commits/' + proof['source_sha'])
    require(commit.get('sha') == proof['source_sha'] and commit.get('tree', {}).get('sha') == target['tree']
            and [p.get('sha') for p in commit.get('parents', [])]
            == receipts['frontend']['parents'], 'Actual source Git commit does not match receipt')
    # Match the actual apt-resolved environment, including transitive client packages.
    # This cost is incurred only after a complete candidate proof was found.
    expected_packages = receipts['backend'].get('apt_packages')
    require(isinstance(expected_packages, str) and re.fullmatch('[0-9a-f]{64}', expected_packages),
            'Missing backend package manifest')
    subprocess.run(['sudo', 'apt-get', 'update', '-qq'], check=True, timeout=90,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(['sudo', 'apt-get', 'install', '-y', '--no-install-recommends',
                    'mysql-client', 'redis-tools'], check=True, timeout=90,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    require(installed_packages_digest() == expected_packages, 'Resolved system packages changed')
    # Close the download window against a source rerun/replacement.
    latest = api.request(base)
    require(all(latest.get(k) == run.get(k) for k in ('run_attempt', 'status', 'conclusion', 'updated_at')),
            'Source run changed during verification')
    current_runs = api.bounded_list(prefix + '/actions/workflows/' + str(target['workflow_id'])
                                    + '/runs?event=pull_request&head_sha=' + pr['head']['sha'], 'workflow_runs')
    require(bool(current_runs) and max(current_runs, key=lambda r: (timestamp(r['created_at']), r['id']))['id']
            == run['id'], 'New source run appeared during verification')
    # Installation/API work may cross the TTL or business-date boundary.
    return validate_evidence(target, pr, run, jobs, receipts, datetime.now(timezone.utc))


def record_receipt(job):
    require(job in JOBS and os.environ.get('GITHUB_EVENT_NAME') == 'pull_request', 'PR receipts only')
    require(os.environ.get('GITHUB_JOB') == job, 'Receipt job does not match execution')
    identity = local_identity()
    verify_environment_contract(Path.cwd())
    payload = event_payload()
    pr = payload['pull_request']
    parents = [line.split()[1] for line in command('git', 'cat-file', '-p', 'HEAD').splitlines()
               if line.startswith('parent ')]
    require(parents == [pr['base']['sha'], pr['head']['sha']], 'Checkout is not the actual PR merge')
    runtimes = {}
    if job == 'frontend':
        runtimes.update(node=command('node', '--version'), npm=command('npm', '--version'))
    else:
        version = subprocess.run(['java', '-version'], capture_output=True, text=True, check=True)
        match = re.search(r'\(build (1\.8\.0_[0-9]+-b[0-9]+)\)', version.stderr)
        require(match is not None, 'Cannot identify Java runtime')
        runtimes.update(python=command('python3', '-c', 'import platform; print(platform.python_version())'),
                        java=match.group(1))
    if job == 'backend':
        for service in ('mysql', 'redis'):
            container = os.environ['CI_' + service.upper() + '_CONTAINER']
            image_id = command('docker', 'inspect', '--format', '{{.Image}}', container)
            digests = parse_json(command('docker', 'image', 'inspect', '--format', '{{json .RepoDigests}}', image_id))
            expected = RUNTIMES[job][service]
            require(any(d.endswith('@' + expected) for d in digests), 'Unexpected service image')
            runtimes[service] = expected
    require(runtimes == RUNTIMES[job], 'Installed runtime versions do not match contract')
    receipt = dict(schema=1, mode='fresh', job=job, event='pull_request',
                   run_id=int(os.environ['GITHUB_RUN_ID']), run_attempt=int(os.environ['GITHUB_RUN_ATTEMPT']),
                   pr_number=payload['number'], head_sha=pr['head']['sha'], base_sha=pr['base']['sha'],
                   parents=parents, checkout_sha=identity.pop('sha'), runtimes=runtimes,
                   recorded_at=datetime.now(timezone.utc).isoformat(), **identity)
    if job == 'backend':
        receipt['apt_packages'] = installed_packages_digest()
    path = Path('ci-results/reuse/' + job + '/receipt.json')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(receipt, indent=2) + '\n')


def write_summary(message):
    print(message)
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as stream:
            stream.write(message + '\n')


def authorize(needs):
    reuse = needs.get('reuse', {})
    require(reuse.get('result') == 'success' and reuse.get('outputs', {}).get('reuse') == 'true',
            'No successful reuse decision')
    raw_id = reuse['outputs'].get('source_run_id', '')
    require(isinstance(raw_id, str) and re.fullmatch('[1-9][0-9]*', raw_id), 'Invalid source run ID')
    api = GitHub()
    proof = resolve(api, target_context(api), int(raw_id))
    write_summary('Historical full-suite evidence revalidated: [' + str(proof['source_run_id'])
                  + '](' + proof['source_url'] + '). Original tested SHA `' + proof['source_sha']
                  + '` → target SHA `' + proof['target_sha'] + '`, tree `' + proof['tree']
                  + '`. Tests were not executed again on this push; original reports retain their SHA.')
    return proof


def normalize_decision(step):
    step = step if isinstance(step, dict) else {}
    outputs = step.get('outputs', {})
    outputs = outputs if isinstance(outputs, dict) else {}
    source = outputs.get('source_run_id', '')
    valid = (step.get('outcome') == 'success' and outputs.get('reuse') == 'true'
             and isinstance(source, str) and re.fullmatch('[1-9][0-9]*', source) is not None)
    return {'reuse': 'true' if valid else 'false', 'source_run_id': source if valid else ''}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--record', choices=JOBS)
    parser.add_argument('--normalize', action='store_true')
    args = parser.parse_args()
    if args.normalize:
        try:
            step = parse_json(os.environ.get('CI_REUSE_STEP', ''))
        except (ValueError, TypeError):
            step = None
        outputs = normalize_decision(step)
        with open(os.environ['GITHUB_OUTPUT'], 'a') as stream:
            stream.writelines(key + '=' + value + '\n' for key, value in outputs.items())
        return 0
    if args.record:
        # Receipts are optional optimization metadata; a missing one can never waive tests.
        try:
            record_receipt(args.record)
        except Exception as error:
            print('No reusable receipt: ' + (str(error) if isinstance(error, ValueError) else type(error).__name__), file=sys.stderr)
        return 0
    proof = None
    try:
        api = GitHub()
        proof = resolve(api, target_context(api))
        write_summary('Reuse candidate: [' + str(proof['source_run_id']) + '](' + proof['source_url']
                      + '), tested `' + proof['source_sha'] + '`, target `' + proof['target_sha']
                      + '`, identical tree `' + proof['tree'] + '`. CI required will revalidate this evidence.')
    except Exception as error:
        # No remote content, signed URLs or credentials are logged on transport failures.
        reason = str(error) if isinstance(error, ValueError) else type(error).__name__
        write_summary('Run the complete suite: ' + reason)
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a') as stream:
            stream.write('reuse=' + ('true' if proof else 'false') + '\n')
            stream.write('source_run_id=' + (str(proof['source_run_id']) if proof else '') + '\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
