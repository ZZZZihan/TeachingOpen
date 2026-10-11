#!/usr/bin/env python3
"""Owned-fixture HTTP file deletion/reference races with real MySQL lock barriers.

Temporary triggers affect only this probe's rows. Every barrier has a bounded
wait; finally releases locks, drops triggers and removes probe data. No backend
or database setting is changed. No production or external storage is contacted.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from queue import Empty, Queue
import shutil
import subprocess
from threading import Thread
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

from local_http import FixtureApi
from local_runtime import mysql_command

TABLES = ('teaching_work', 'teaching_work_correct', 'teaching_work_comment', 'sys_file',
          'sys_data_log', 'teaching_additional_work', 'teaching_depart_day_log')


class MySqlSession:
    def __init__(self, runtime):
        self.process = subprocess.Popen(mysql_command(runtime) + ['--unbuffered', 'teachingopen_dev'],
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.DEVNULL, text=True, bufsize=1)
        self.lines = Queue()
        def receive():
            for line in self.process.stdout:
                self.lines.put(line.rstrip('\n'))
            self.lines.put(None)
        Thread(target=receive, daemon=True).start()

    def run(self, statement):
        marker = 'done_' + uuid4().hex
        self.process.stdin.write(statement + ";\nSELECT '" + marker + "';\n")
        self.process.stdin.flush()
        rows, deadline = [], time.monotonic() + 10
        while True:
            try:
                line = self.lines.get(timeout=max(.01, deadline - time.monotonic()))
            except Empty:
                raise RuntimeError('Fixture lock session timed out')
            if line is None:
                raise RuntimeError('Fixture lock session failed')
            if line == marker:
                return rows
            rows.append(line)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.process.stdin.close()
        try:
            self.process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=3)
        self.process.stdout.close()


def verify(args):
    cases, error = [], None
    with FixtureApi(args.runtime.resolve(), args.jar) as api:
        def sql(statement):
            output = subprocess.run(mysql_command(api.runtime) + ['teachingopen_dev', '-e', statement],
                                    capture_output=True, text=True, timeout=20)
            if output.returncode:
                raise RuntimeError('Owned file-deletion fixture SQL failed: ' + output.stderr[:500])
            return output.stdout.strip()

        def literal(value):
            return 'NULL' if value is None else "CONVERT(0x" + str(value).encode().hex() + " USING utf8mb4)" if str(value) else "''"

        def check(name, passed, fatal=True):
            cases.append({'case': name, 'passed': bool(passed)})
            print(('PASS ' if passed else 'FAIL ') + name, flush=True)
            if not passed and fatal:
                raise AssertionError(name)

        def rows():
            return {table: hashlib.sha256(sql('SELECT * FROM ' + table + ' ORDER BY id').encode()).hexdigest() for table in TABLES}

        def disk():
            return {str(p.relative_to(api.runtime / 'uploads')): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in (api.runtime / 'uploads').rglob('*') if p.is_file()}

        prefix = 'file_race_' + uuid4().hex[:12]
        folder = api.runtime / 'uploads' / prefix
        trigger = prefix + '_barrier'
        lock = prefix + '_lock'
        ident, work_id = prefix + '_file', prefix + '_work'
        key = prefix + '/attachment.txt'
        path = api.runtime / 'uploads' / key
        content = b'synthetic concurrent attachment\n'
        work_route = '/teaching/teachingWork/edit'
        delete_route = '/system/sysFile/delete?id=' + ident

        def success(response):
            status, result, _ = response
            return status == 200 and result and result.get('success') is True

        def denied(response):
            status, result, _ = response
            return status == 200 and result and result.get('success') is False and result.get('code') == 510

        def failed_cleanup(response):
            status, result, _ = response
            return (status == 200 and result and result.get('success') is False and result.get('code') == 409
                    and result.get('message') == '文件清理未完成，已保留记录，请稍后重试删除')

        def edit():
            return api.request('PUT', work_route, 'teacher_a', {'id': work_id, 'workFile': ident, 'workStatus': '0'})

        def delete():
            return api.request('DELETE', delete_route, 'teacher_a')

        def reset():
            sql('DROP TRIGGER IF EXISTS ' + trigger)
            sql('DELETE FROM teaching_work WHERE id=' + literal(work_id))
            sql('DELETE FROM sys_file WHERE id=' + literal(ident))
            path.write_bytes(content)
            sql('INSERT INTO sys_file(id,file_name,file_path,file_location,create_by,create_time,del_flag) VALUES ('
                + ','.join(literal(v) for v in (ident, 'attachment.txt', key, 1, 'fixture_teacher_a', '2026-10-11 00:00:00', 0)) + ')')
            sql('INSERT INTO teaching_work(id,user_id,depart_id,work_name,work_type,work_status,del_flag,create_by,create_time) VALUES ('
                + ','.join(literal(v) for v in (work_id, 'fixture_student_a', 'fixture_class_a', prefix, '2', '0', 0,
                                                'fixture_teacher_a', '2026-10-11 00:00:00')) + ')')

        def wait_for(query, pending):
            deadline = time.monotonic() + 6
            while time.monotonic() < deadline:
                if int(sql(query) or '0') > 0:
                    return True
                if any(f.done() for f in pending):
                    return False
                time.sleep(.025)
            return False

        def add_barrier(table, condition):
            sql('CREATE TRIGGER ' + trigger + ' BEFORE UPDATE ON ' + table
                + ' FOR EACH ROW BEGIN IF ' + condition + ' THEN '
                + 'IF GET_LOCK(' + literal(lock) + ",8) <> 1 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='fixture barrier timed out'; END IF; "
                + 'DO RELEASE_LOCK(' + literal(lock) + '); END IF; END')

        def first_writer_wins(label):
            reset()
            add_barrier('teaching_work', 'NEW.id=' + literal(work_id) + ' AND NEW.work_file=' + literal(ident))
            with MySqlSession(api.runtime) as guard, ThreadPoolExecutor(max_workers=2) as pool:
                check(label + ' acquires named barrier', guard.run('SELECT GET_LOCK(' + literal(lock) + ',0)') == ['1'])
                writer = pool.submit(edit)
                try:
                    waiting = wait_for("SELECT COUNT(*) FROM performance_schema.metadata_locks WHERE OBJECT_TYPE='USER LEVEL LOCK' "
                                       + 'AND OBJECT_NAME=' + literal(lock) + " AND LOCK_STATUS='PENDING'", [writer])
                    check(label + ' actual teacher edit reached post-authorization row-write barrier', waiting)
                    deletion = pool.submit(delete)
                    waiting = wait_for('SELECT COUNT(*) FROM performance_schema.data_lock_waits w '
                                       'JOIN performance_schema.data_locks l ON l.ENGINE_LOCK_ID=w.REQUESTING_ENGINE_LOCK_ID '
                                       "WHERE l.OBJECT_SCHEMA='teachingopen_dev' AND l.OBJECT_NAME='sys_file'", [writer, deletion])
                    check(label + ' deletion is waiting on the actual referenced file row', waiting)
                    check(label + (' baseline erases bytes while writer still holds file lock' if args.expect_legacy
                                   else ' waiting deletion has not erased physical bytes'),
                          not path.exists() if args.expect_legacy else path.exists() and path.read_bytes() == content)
                finally:
                    guard.run('SELECT RELEASE_LOCK(' + literal(lock) + ')')
                saved, removed = writer.result(timeout=15), deletion.result(timeout=15)
            check(label + ' authorized writer completes', success(saved))
            check(label + (' baseline delete also reports success' if args.expect_legacy else ' delete reports referenced-file refusal'),
                  success(removed) if args.expect_legacy else failed_cleanup(removed))
            check(label + ' work stores the committed reference', sql('SELECT work_file FROM teaching_work WHERE id=' + literal(work_id)) == ident)
            check(label + (' baseline saved reference points to missing bytes and metadata' if args.expect_legacy
                           else ' referenced bytes and live metadata survive'),
                  (not path.exists() and sql('SELECT COUNT(*) FROM sys_file WHERE id=' + literal(ident)) == '0') if args.expect_legacy
                  else (path.read_bytes() == content and sql('SELECT del_flag FROM sys_file WHERE id=' + literal(ident)) == '0'))

        def deletion_wins(label):
            reset()
            add_barrier('sys_file', 'NEW.id=' + literal(ident) + ' AND NEW.del_flag=1 AND OLD.del_flag=0')
            with MySqlSession(api.runtime) as guard, ThreadPoolExecutor(max_workers=2) as pool:
                check(label + ' acquires deletion barrier', guard.run('SELECT GET_LOCK(' + literal(lock) + ',0)') == ['1'])
                deletion = pool.submit(delete)
                try:
                    waiting = wait_for("SELECT COUNT(*) FROM performance_schema.metadata_locks WHERE OBJECT_TYPE='USER LEVEL LOCK' "
                                       + 'AND OBJECT_NAME=' + literal(lock) + " AND LOCK_STATUS='PENDING'", [deletion])
                    check(label + ' actual delete holds file row before tombstone commit', waiting)
                    writer = pool.submit(edit)
                    waiting = wait_for('SELECT COUNT(*) FROM performance_schema.data_lock_waits w '
                                       'JOIN performance_schema.data_locks l ON l.ENGINE_LOCK_ID=w.REQUESTING_ENGINE_LOCK_ID '
                                       "WHERE l.OBJECT_SCHEMA='teachingopen_dev' AND l.OBJECT_NAME='sys_file'", [writer, deletion])
                    check(label + ' actual reference writer waits on same file row', waiting)
                    check(label + ' uncommitted deletion preserves bytes', path.read_bytes() == content)
                finally:
                    guard.run('SELECT RELEASE_LOCK(' + literal(lock) + ')')
                removed, saved = deletion.result(timeout=15), writer.result(timeout=15)
            check(label + ' deletion completes', success(removed))
            check(label + ' first reference is rejected with authorization response', denied(saved))
            check(label + ' rejected writer leaves work unmodified', sql('SELECT COALESCE(work_file,\'\') FROM teaching_work WHERE id=' + literal(work_id)) == '')
            check(label + ' bytes and metadata are fully reclaimed', not path.exists() and sql('SELECT COUNT(*) FROM sys_file WHERE id=' + literal(ident)) == '0')

        def tombstone_denials(label):
            check(label + ' pending record remains available to owner management list',
                  any(record.get('id') == ident and record.get('delFlag') == 1 for record in
                      api.request('GET', '/system/sysFile/list?fileName=attachment.txt', 'teacher_a')[1]['result']['records']))
            check(label + ' metadata read is refused', denied(api.request('GET', '/system/sysFile/queryById?id=' + ident, 'teacher_a')))
            for actor in ('teacher_a', 'admin', None):
                request = Request('http://127.0.0.1:' + str(api.ports['backend']) + '/api/sys/common/static/' + key,
                                  headers={'X-Access-Token': api.tokens[actor]} if actor else {})
                try:
                    response = urlopen(request, timeout=10)
                except HTTPError as failure:
                    response = failure
                with response:
                    check(label + ' pending bytes refused for ' + str(actor), response.status == (403 if actor else 401))
            check(label + ' new work reference refused', denied(edit()))
            check(label + ' other owner cannot perform cleanup retry', denied(api.request('DELETE', delete_route, 'teacher_b')))

        original_rows, original_disk = rows(), disk()
        if folder.exists():
            raise RuntimeError('Refusing to overwrite existing file-race probe folder')
        try:
            for actor in ('teacher_a', 'teacher_b', 'student_a', 'admin'):
                api.login(actor)
            folder.mkdir()
            for iteration in range(1 if args.expect_legacy else 3):
                first_writer_wins('writer-first-' + str(iteration + 1))
                if not args.expect_legacy:
                    deletion_wins('delete-first-' + str(iteration + 1))
            if not args.expect_legacy:
                reset()
                folder.chmod(0o555)
                try:
                    check('actual local unlink failure reports failed cleanup', failed_cleanup(delete()))
                    check('unlink failure leaves bytes and committed tombstone', path.read_bytes() == content
                          and sql('SELECT del_flag FROM sys_file WHERE id=' + literal(ident)) == '1')
                    tombstone_denials('local I/O failure')
                finally:
                    folder.chmod(0o755)
                check('same owner retries failed local cleanup successfully', success(delete()))
                check('local cleanup retry removes bytes and metadata', not path.exists() and sql('SELECT COUNT(*) FROM sys_file WHERE id=' + literal(ident)) == '0')

                reset()
                sql('CREATE TRIGGER ' + trigger + ' BEFORE DELETE ON sys_file FOR EACH ROW BEGIN IF OLD.id=' + literal(ident)
                    + " THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='synthetic metadata cleanup failure'; END IF; END")
                check('metadata DELETE SQL failure reports failed cleanup', failed_cleanup(delete()))
                check('SQL cleanup failure retains tombstone after physical deletion', not path.exists()
                      and sql('SELECT del_flag FROM sys_file WHERE id=' + literal(ident)) == '1')
                check('SQL-failure tombstone cannot be referenced', denied(edit()))
                sql('DROP TRIGGER ' + trigger)
                check('same owner retries missing-object metadata cleanup', success(delete()))
                check('metadata retry completes', sql('SELECT COUNT(*) FROM sys_file WHERE id=' + literal(ident)) == '0')
        except Exception as failure:
            error = type(failure).__name__ + ': ' + str(failure)
        finally:
            if folder.exists():
                folder.chmod(0o755)
            sql('DROP TRIGGER IF EXISTS ' + trigger)
            sql('DELETE FROM teaching_work_correct WHERE work_id=' + literal(work_id))
            sql('DELETE FROM teaching_work_comment WHERE work_id=' + literal(work_id))
            sql('DELETE FROM sys_data_log WHERE data_id=' + literal(work_id))
            sql('DELETE FROM teaching_work WHERE id=' + literal(work_id))
            sql('DELETE FROM sys_file WHERE id=' + literal(ident))
            if folder.exists():
                shutil.rmtree(folder)
        check('all original business rows restored', original_rows == rows(), fatal=False)
        check('all original upload bytes restored', original_disk == disk(), fatal=False)
        check('temporary barrier trigger removed', sql("SELECT COUNT(*) FROM information_schema.triggers WHERE trigger_schema=DATABASE() AND trigger_name=" + literal(trigger)) == '0', fatal=False)
        result = {'cases': cases, 'passed': sum(case['passed'] for case in cases), 'failed': sum(not case['passed'] for case in cases),
                  'total': len(cases), 'jar_sha256': api.jar_sha256, 'expected_legacy': args.expect_legacy, 'exception': error,
                  'created_at': datetime.now(timezone.utc).isoformat(),
                  'scope': 'Actual HTTP writes/deletes, MySQL triggers and named/row locks (3 repetitions per order), local unlink and metadata SQL failure, retry; owned synthetic runtime only.'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    return error is None and result['failed'] == 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('runtime', 'jar', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--expect-legacy', action='store_true')
    raise SystemExit(0 if verify(parser.parse_args()) else 1)
