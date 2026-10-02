#!/usr/bin/env python3
"""Real HTTP business reads after a successful isolated synthetic restore."""
import argparse
import hashlib
import json
from pathlib import Path
import re
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from local_http import FixtureApi
from local_recovery import inspect_snapshot, private_write, sha256, sql, file_inventory, quote


def verify(args):
    manifest = inspect_snapshot(args.snapshot)
    restored = json.loads((args.runtime / 'restore-result.json').read_text())
    if (restored['snapshot_manifest_sha256'] != sha256(args.snapshot / 'manifest.json')
            or restored['runtime'] != str(args.runtime) or not restored['database_equal']
            or not restored['attachments_equal']):
        raise RuntimeError('Target has no matching successful restore result')
    cases = []

    def check(name, passed):
        cases.append({'case': name, 'passed': bool(passed)})
        print(('PASS ' if passed else 'FAIL ') + name, flush=True)

    def success(response):
        return response[0] == 200 and response[1] and response[1].get('success') is True

    with FixtureApi(args.runtime, args.jar) as api:
        if api.ports != restored['ports']:
            raise RuntimeError('Target ports changed after restore')
        view_counts = {suffix: sql(args.runtime, "SELECT IFNULL(view_num,'NULL') FROM teachingopen_dev.teaching_work WHERE id='fixture_work_" + suffix + "'") for suffix in ('a', 'b')}
        if any(not (v == 'NULL' or v.isdecimal()) for v in view_counts.values()):
            raise RuntimeError('Expected the two original synthetic works')
        def audit_values(suffix):
            return sql(args.runtime, "SELECT IFNULL(HEX(CAST(update_by AS BINARY)),'NULL'),IFNULL(HEX(CAST(update_time AS BINARY)),'NULL') FROM teachingopen_dev.teaching_work WHERE id='fixture_work_" + suffix + "'").split('\t')

        original_audit = {suffix: audit_values(suffix) for suffix in view_counts}
        if any(len(values) != 2 or any(v != 'NULL' and not re.fullmatch('[0-9A-F]*', v) for v in values) for values in original_audit.values()):
            raise RuntimeError('Unexpected original work audit fields')
        columns = [line.split('\t')[0] for line in sql(args.runtime, 'SHOW COLUMNS FROM teachingopen_dev.teaching_work').splitlines()]
        work_query = "SELECT 'ROW'," + ','.join("IFNULL(HEX(CAST(" + quote(c) + " AS BINARY)),'~')" for c in columns) + ' FROM teachingopen_dev.teaching_work ORDER BY id'
        original_work_hash = hashlib.sha256(sql(args.runtime, work_query).encode()).hexdigest()
        try:
            cookies = {}
            for actor in ('admin', 'teacher_a', 'teacher_b', 'student_a', 'student_b'):
                api.login(actor)
                check('restored account login ' + actor, actor in api.tokens)
                headers = api.last_response_headers.get_all('Set-Cookie', [])
                cookies[actor] = next((h.split(';')[0] for h in headers if h.startswith('teaching_media_' + str(api.ports['backend']) + '=')), '')
                check('restored runtime issues port-scoped media cookie ' + actor, bool(cookies[actor]))

            for suffix in ('a', 'b'):
                actor = 'student_' + suffix
                response = api.request('GET', '/teaching/teachingCourse/queryById?id=fixture_course_' + suffix, actor)
                check('assigned course readable ' + actor, success(response) and response[1]['result']['id'] == 'fixture_course_' + suffix)
                response = api.request('GET', '/teaching/teachingWork/studentWorkInfo?workId=fixture_work_' + suffix, actor)
                key = 'fixture-work-' + suffix + '.txt'
                check('restored work references restored attachment ' + actor, success(response) and response[1]['result']['id'] == 'fixture_work_' + suffix and response[1]['result'].get('workFileKey_url', '').endswith('/' + key))
                # A native cookie-only download exercises the same media authorization
                # used by browser elements without injecting browser login state.
                request = Request('http://127.0.0.1:' + str(api.ports['backend']) + '/api/sys/common/static/' + key, headers={'Cookie': cookies[actor]})
                with urlopen(request, timeout=15) as download:
                    payload = download.read()
                    check('restored attachment bytes readable with media cookie ' + actor, download.status == 200 and hashlib.sha256(payload).hexdigest() == manifest['uploads'][key]['sha256'] and download.headers.get('Cache-Control') == 'no-store')

            for actor in ('teacher_a', 'admin'):
                check('authorized private work read ' + actor, success(api.request('GET', '/teaching/teachingWork/studentWorkInfo?workId=fixture_work_a', actor)))
            for actor in (None, 'student_b', 'teacher_b'):
                response = api.request('GET', '/teaching/teachingWork/studentWorkInfo?workId=fixture_work_a', actor)
                check('private work denied ' + str(actor), not success(response) and response[1] and response[1].get('result') is None)
                headers = {'X-Access-Token': api.tokens[actor]} if actor else {}
                request = Request('http://127.0.0.1:' + str(api.ports['backend']) + '/api/sys/common/static/fixture-work-a.txt', headers=headers)
                try:
                    download = urlopen(request, timeout=15)
                except HTTPError as error:
                    download = error
                with download:
                    check('private restored attachment denied ' + str(actor), download.status in (401, 403, 404) and b'synthetic work a' not in download.read())
            check('restored work views persist in target database', sql(args.runtime, "SELECT view_num FROM teachingopen_dev.teaching_work WHERE id='fixture_work_a'") == str((0 if view_counts['a'] == 'NULL' else int(view_counts['a'])) + 3))
            for suffix, values in original_audit.items():
                check('work modification actor and time unchanged by reads ' + suffix, audit_values(suffix) == values)
        finally:
            # Preserve the baseline even when testing a regressed backend. Check
            # audit fields before cleanup rather than masking the regression.
            for suffix, count in view_counts.items():
                assignments = [field + '=' + ('NULL' if value == 'NULL' else "UNHEX('" + value + "')")
                               for field, value in zip(('update_by', 'update_time'), original_audit[suffix])]
                sql(args.runtime, "UPDATE teachingopen_dev.teaching_work SET view_num=" + count + ',' + ','.join(assignments) + " WHERE id='fixture_work_" + suffix + "'")
        check('all work columns and rows unchanged after counter cleanup', hashlib.sha256(sql(args.runtime, work_query).encode()).hexdigest() == original_work_hash)
        check('attachment files unchanged by business reads', file_inventory(args.runtime / 'uploads') == manifest['uploads'])
        result = {'jar_sha256': api.jar_sha256, 'snapshot_manifest_sha256': restored['snapshot_manifest_sha256'], 'cases': cases, 'total': len(cases), 'passed': sum(x['passed'] for x in cases), 'business_read_verified': all(x['passed'] for x in cases), 'browser_e2e': False, 'audit_logs_retained': True}
    private_write(args.output, json.dumps(result, indent=2) + '\n')
    if not result['business_read_verified']:
        raise SystemExit(1)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--snapshot', type=Path, required=True)
    parser.add_argument('--jar', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.runtime, args.snapshot = args.runtime.resolve(), args.snapshot.resolve()
    verify(args)
