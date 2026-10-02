#!/usr/bin/env python3
"""Check view-count writes and modification metadata using real synthetic HTTP."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from threading import Barrier
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from local_http import FixtureApi
from local_recovery import file_inventory, private_write, quote, sql


PREFIX = 'fixture_viewprobe_'
TABLE = 'teachingopen_dev.teaching_work'
BASE = '/teaching/teachingWork/studentWorkInfo?workId='


def verify(args):
    cases, observations = [], []

    def check(name, passed):
        cases.append({'case': name, 'passed': bool(passed)})
        print(('PASS ' if passed else 'FAIL ') + name, flush=True)

    def success(response):
        return response[0] == 200 and response[1] and response[1].get('success') is True

    with FixtureApi(args.runtime, args.jar) as api:
        def query(statement):
            return sql(api.runtime, statement)

        columns = [line.split('\t')[0] for line in query('SHOW COLUMNS FROM ' + TABLE).splitlines()]

        def rows(suffix=None, exclude=()):
            expression = ','.join("IFNULL(HEX(CAST(" + quote(c) + " AS BINARY)),'~')"
                                  for c in columns if c not in exclude)
            where = " WHERE id='" + PREFIX + suffix + "'" if suffix else ''
            return query("SELECT 'ROW'," + expression + ' FROM ' + TABLE + where + ' ORDER BY id')

        def count(suffix):
            return int(query('SELECT view_num FROM ' + TABLE + " WHERE id='" + PREFIX + suffix + "'"))

        def detail(suffix, actor=None, token=None):
            return api.request('GET', BASE + PREFIX + suffix, actor, token=token)

        original_rows = rows()
        original_files = file_inventory(api.runtime / 'uploads')
        if query('SELECT COUNT(*) FROM ' + TABLE + " WHERE id LIKE '" + PREFIX + "%' ") != '0':
            raise RuntimeError('Probe rows already exist; do not overwrite them')
        try:
            for actor in ('admin', 'teacher_a', 'teacher_b', 'student_a', 'student_b'):
                api.login(actor)
            for suffix, state, deleted in [('private', '0', 0), ('public', '3', 0),
                                           ('featured', '4', 0), ('deleted', '3', 1),
                                           ('parallel', '3', 0), ('limit', '3', 0)]:
                query('INSERT INTO ' + TABLE + ' (id,user_id,depart_id,work_name,work_type,work_status,'
                      'work_file,work_cover,del_flag,view_num,star_num,collect_num,create_by,create_time,update_by,update_time)'
                      " VALUES ('" + PREFIX + suffix + "','fixture_student_a','fixture_class_a','view-probe-" + suffix
                      + "','1','" + state + "','fixture_file_a','fixture_file_a'," + str(deleted)
                      + ",20,7,4,'fixture_student_a','2026-09-01 01:02:03','fixture_teacher_a','2026-09-02 04:05:06')")

            for suffix, actors in [('private', ('student_a', 'teacher_a', 'admin')),
                                    ('public', (None, 'student_b', 'teacher_b')),
                                    ('featured', (None, 'student_a'))]:
                for actor in actors:
                    before_count = count(suffix)
                    before = rows(suffix, ('view_num',))
                    content = rows(suffix, ('view_num', 'update_by', 'update_time'))
                    response = detail(suffix, actor)
                    label = str(actor) + ' ' + suffix
                    check(label + ' detail succeeds and one view persists', success(response)
                          and count(suffix) == before_count + 1)
                    check(label + ' response keeps existing pre-increment count and attachment contract',
                          success(response) and response[1]['result'].get('viewNum') == before_count
                          and response[1]['result'].get('workFileKey_url', '').endswith('/fixture-work-a.txt'))
                    check(label + ' content and other counters unchanged', rows(suffix, ('view_num', 'update_by', 'update_time')) == content)
                    if not args.expect_legacy:
                        check(label + ' all non-view columns unchanged', rows(suffix, ('view_num',)) == before)
                    elif actor == 'student_a' and suffix == 'private':
                        check('legacy read replaces modification actor and time', rows(suffix, ('view_num',)) != before
                              and query('SELECT update_by FROM ' + TABLE + " WHERE id='" + PREFIX + suffix + "'") == 'fixture_student_a')

            for suffix, actors in [('private', (None, 'student_b', 'teacher_b')),
                                    ('deleted', (None, 'student_a', 'admin')),
                                    ('missing', (None, 'student_a', 'admin'))]:
                for actor in actors:
                    before = rows()
                    response = detail(suffix, actor)
                    check(str(actor) + ' denied ' + suffix + ' without changing work rows',
                          response[0] == 200 and response[1] and response[1].get('success') is False
                          and response[1].get('code') == 510 and not response[1].get('result') and rows() == before)
            for token in ('invalid-probe-token', ''):
                before = rows()
                response = detail('public', token=token)
                check(('malformed' if token else 'empty') + ' credential denied without effects',
                      response[0] == 401 and not success(response) and rows() == before)

            # A Request and response per worker; only immutable credentials are
            # shared. FixtureApi.last_response_headers is not used concurrently.
            for actor, workers, requests in [(None, 1, 16), (None, 8, 64), ('student_a', 16, 96)]:
                query('UPDATE ' + TABLE + " SET view_num=20,update_by='fixture_teacher_a',update_time='2026-09-02 04:05:06' WHERE id='" + PREFIX + "parallel'")
                before = rows('parallel', ('view_num',))
                headers = {'X-Access-Token': api.tokens[actor]} if actor else {}
                barrier = Barrier(workers, timeout=30)
                url = 'http://127.0.0.1:' + str(api.ports['backend']) + '/api' + BASE + PREFIX + 'parallel'

                def read_one(_):
                    barrier.wait()
                    request = Request(url, headers=headers)
                    try:
                        response = urlopen(request, timeout=30)
                    except HTTPError as error:
                        response = error
                    with response:
                        return success((response.status, json.loads(response.read())))

                with ThreadPoolExecutor(max_workers=workers) as pool:
                    replies = list(pool.map(read_one, range(requests)))
                persisted = count('parallel') - 20
                observations.append({'actor': actor or 'anonymous', 'workers': workers, 'requests': requests,
                                     'successful_responses': sum(bool(x) for x in replies), 'persisted_increment': persisted})
                label = str(workers) + ' workers ' + str(actor)
                check(label + ' all HTTP detail reads succeed', all(replies))
                if not args.expect_legacy or workers == 1:
                    check(label + ' persists every successful view', persisted == requests)
                if not args.expect_legacy:
                    check(label + ' all non-view columns unchanged', rows('parallel', ('view_num',)) == before)
            if args.expect_legacy:
                check('legacy concurrent reads lose increments', any(x['persisted_increment'] < x['successful_responses'] for x in observations if x['workers'] > 1))
            else:
                # An exhausted INT counter makes the real UPDATE fail. The API
                # must not claim a counted success or mutate any work field.
                query('UPDATE ' + TABLE + " SET view_num=2147483647 WHERE id='" + PREFIX + "limit'")
                before = rows()
                response = detail('limit', 'student_a')
                check('failed counter write returns no successful detail and preserves all rows',
                      not success(response) and response[1] and not response[1].get('result') and rows() == before)
                query('UPDATE ' + TABLE + " SET view_num=20 WHERE id='" + PREFIX + "limit'")
                response = detail('limit', 'student_a')
                check('detail succeeds again after counter failure removed', success(response) and count('limit') == 21)
            jar_hash = api.jar_sha256
        finally:
            query('DELETE FROM ' + TABLE + " WHERE id LIKE '" + PREFIX + "%'")
        check('all original work columns and rows restored', rows() == original_rows)
        check('all original attachment bytes unchanged', file_inventory(api.runtime / 'uploads') == original_files)
        original_hash = hashlib.sha256(original_rows.encode()).hexdigest()
    report = {'observed_utc': datetime.now(timezone.utc).isoformat(), 'jar_sha256': jar_hash,
              'expected_legacy': args.expect_legacy, 'concurrent_reads': observations,
              'original_work_rows_sha256': original_hash, 'cases': cases, 'total': len(cases),
              'passed': sum(x['passed'] for x in cases),
              'scope': 'Real synthetic HTTP/login/MySQL, dedicated temporary works; pre-increment response contract, metadata, authorization, concurrent count and failed write. No browser, capacity or concurrent publish/delete acceptance.'}
    private_write(args.output, json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(str(report['passed']) + '/' + str(report['total']) + ' checks passed')
    return report['passed'] == report['total']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--jar', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--expect-legacy', action='store_true')
    raise SystemExit(0 if verify(parser.parse_args()) else 1)
