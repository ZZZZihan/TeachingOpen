#!/usr/bin/env python3
"""Verify like counters and fixed save/withdraw races over real HTTP and MySQL."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import select
import subprocess
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from local_http import FixtureApi
from local_recovery import file_inventory, private_write, quote, sql
from local_runtime import mysql_command

PREFIX = 'fixture_starprobe_'
TABLE = 'teachingopen_dev.teaching_work'
BASE = '/teaching/teachingWork/starWork?workId='


def verify(args):
    cases = []

    def check(name, passed):
        cases.append({'case': name, 'passed': bool(passed)})
        print(('PASS ' if passed else 'FAIL ') + name, flush=True)

    def success(response):
        return response[0] == 200 and response[1] and response[1].get('success') is True

    with FixtureApi(args.runtime, args.jar) as api:
        def query(statement):
            return sql(api.runtime, statement)

        definitions = [row.split('\t') for row in query('SHOW COLUMNS FROM ' + TABLE).splitlines()]
        columns = [row[0] for row in definitions]
        star_nullable = next(row[2] == 'YES' for row in definitions if row[0] == 'star_num')

        def rows(suffix=None, exclude=()):
            fields = ','.join("IFNULL(HEX(CAST(" + quote(c) + " AS BINARY)),'~')" for c in columns if c not in exclude)
            where = " WHERE id='" + PREFIX + suffix + "'" if suffix else ''
            return query("SELECT 'ROW'," + fields + ' FROM ' + TABLE + where + ' ORDER BY id')

        def star(suffix, actor=None):
            return api.request('GET', BASE + PREFIX + suffix, actor)

        def count(suffix):
            return query('SELECT star_num FROM ' + TABLE + " WHERE id='" + PREFIX + suffix + "'")

        original, files = rows(), file_inventory(api.runtime / 'uploads')
        if query('SELECT COUNT(*) FROM ' + TABLE + " WHERE id LIKE '" + PREFIX + "%' ") != '0':
            raise RuntimeError('Existing probe works; refusing overwrite')
        if api.cache('KEYS', 'starWork:' + PREFIX + '*'):
            raise RuntimeError('Existing probe like keys; refusing overwrite')
        try:
            for actor in ('student_a', 'teacher_a', 'admin'):
                api.login(actor)
            for suffix, status, deleted in [('public', '3', 0), ('featured', '4', 0), ('private', '0', 0),
                                             ('deleted', '3', 1), ('save', '3', 0), ('withdraw', '3', 0),
                                             ('parallel', '3', 0), ('limit', '3', 0)]:
                query('INSERT INTO ' + TABLE + ' (id,user_id,depart_id,work_name,work_type,work_status,work_file,'
                      'del_flag,view_num,star_num,collect_num,create_by,create_time,update_by,update_time)'
                      " VALUES ('" + PREFIX + suffix + "','fixture_student_a','fixture_class_a','star-probe-" + suffix
                      + "','1','" + status + "','fixture_file_a'," + str(deleted)
                      + ",20,7,4,'fixture_student_a','2026-09-01 01:02:03','fixture_teacher_a','2026-09-02 04:05:06')")
            for suffix in ('public', 'featured'):
                before = rows(suffix, ('star_num',))
                initial_counter = 'NULL' if star_nullable else '0'
                query('UPDATE ' + TABLE + ' SET star_num=' + initial_counter + " WHERE id='" + PREFIX + suffix + "'")
                check(suffix + ' public like succeeds from ' + initial_counter + ' counter', success(star(suffix)) and count(suffix) == '1')
                check(suffix + ' like changes no other work column', rows(suffix, ('star_num',)) == before)
                check(suffix + ' duplicate like does not increment again', success(star(suffix)) and count(suffix) == '1')
            for suffix, actor in [('private', 'student_a'), ('private', 'admin'), ('deleted', 'admin'), ('missing', None)]:
                before = rows()
                check(str(actor) + ' cannot like ' + suffix, not success(star(suffix, actor)) and rows() == before)

            # Keep a real writer transaction uncommitted. The controller's plain
            # SELECT sees the old published version; its UPDATE waits for this
            # row lock. Commit the edit only after observing the real lock wait.
            for suffix, new_status in [('save', '3'), ('withdraw', '1')]:
                untouched = rows(suffix, ('star_num', 'work_file', 'work_status', 'update_by', 'update_time'))
                writer = subprocess.Popen(mysql_command(api.runtime) + ['--unbuffered', 'teachingopen_dev'],
                                          stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                          text=True, bufsize=1)
                pool = ThreadPoolExecutor(max_workers=1)
                try:
                    writer.stdin.write("START TRANSACTION; UPDATE teaching_work SET work_file='fixture_file_b',"
                                       "work_status='" + new_status + "',update_by='saved-editor',"
                                       "update_time='2026-10-04 05:06:07' WHERE id='" + PREFIX + suffix
                                       + "'; SELECT 'WRITER_LOCKED';\n")
                    writer.stdin.flush()
                    if not select.select([writer.stdout], [], [], 10)[0] or writer.stdout.readline().strip() != 'WRITER_LOCKED':
                        raise RuntimeError('Could not establish the synthetic writer barrier')
                    future = pool.submit(star, suffix)
                    waiting = False
                    until = time.monotonic() + 10
                    while time.monotonic() < until and not future.done():
                        waiting = query("SELECT COUNT(*) FROM information_schema.innodb_trx WHERE trx_state='LOCK WAIT' "
                                        "AND LOWER(trx_query) LIKE '%update teaching_work%'") != '0'
                        if waiting:
                            break
                        time.sleep(0.05)
                    check(suffix + ' HTTP like read precedes the concurrent writer commit', waiting)
                    writer.stdin.write('COMMIT;\n'); writer.stdin.flush()
                    response = future.result(timeout=20)
                    check(suffix + ' like reports the final publication state', success(response) == (new_status == '3'))
                    check(suffix + ' persisted save and audit metadata survive the like',
                          query("SELECT CONCAT_WS('|',work_file,work_status,user_id,update_by,update_time) FROM " + TABLE
                                + " WHERE id='" + PREFIX + suffix + "'")
                          == 'fixture_file_b|' + new_status + '|fixture_student_a|saved-editor|2026-10-04 05:06:07')
                    check(suffix + ' counter reflects only a successful public like', count(suffix) == ('8' if new_status == '3' else '7'))
                    check(suffix + ' keeps every other work column unchanged',
                          rows(suffix, ('star_num', 'work_file', 'work_status', 'update_by', 'update_time')) == untouched)
                    if new_status != '3':
                        check('withdrawn failed like does not set a deduplication key', not api.cache('KEYS', 'starWork:' + PREFIX + suffix + '*'))
                finally:
                    if writer.poll() is None:
                        writer.stdin.write('ROLLBACK; quit\n'); writer.stdin.flush()
                        writer.communicate(timeout=10)
                    pool.shutdown(wait=True)

            before = rows('parallel', ('star_num',))
            def like_from_address(number):
                url = 'http://127.0.0.1:' + str(api.ports['backend']) + '/api' + BASE + PREFIX + 'parallel'
                request = Request(url, headers={'X-Forwarded-For': '198.18.0.' + str(number + 1)})
                try:
                    response = urlopen(request, timeout=20)
                except HTTPError as error:
                    response = error
                with response:
                    return success((response.status, json.loads(response.read())))
            with ThreadPoolExecutor(max_workers=8) as pool:
                replies = list(pool.map(like_from_address, range(32)))
            check('32 concurrent distinct-client likes all persist', all(replies) and count('parallel') == '39')
            check('parallel likes preserve every non-like column', rows('parallel', ('star_num',)) == before)
            query('UPDATE ' + TABLE + " SET star_num=2147483647 WHERE id='" + PREFIX + "limit'")
            before = rows()
            check('failed counter write cannot report success or change other fields', not success(star('limit')) and rows() == before)
            check('failed counter write does not set a deduplication key', not api.cache('KEYS', 'starWork:' + PREFIX + 'limit*'))
            jar_hash = api.jar_sha256
        finally:
            query('DELETE FROM ' + TABLE + " WHERE id LIKE '" + PREFIX + "%'")
            for key in api.cache('KEYS', 'starWork:' + PREFIX + '*').splitlines():
                api.cache('DEL', key)
        check('all original work columns restored', rows() == original)
        check('all original attachment bytes unchanged', file_inventory(api.runtime / 'uploads') == files)
    result = {'checked_at': datetime.now(timezone.utc).isoformat(), 'scope': 'synthetic local HTTP and MySQL',
              'jar_sha256': jar_hash, 'cases': cases, 'passed': all(case['passed'] for case in cases),
              'production_verified': False, 'browser_verified': False}
    private_write(args.output, json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    return result['passed']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--jar', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    raise SystemExit(0 if verify(parser.parse_args()) else 1)
