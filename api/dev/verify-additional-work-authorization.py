#!/usr/bin/env python3
"""Additional-work HTTP/SQL checks for an owned, five-account synthetic runtime.

Does not provision or start the runtime. Only task-named probe records and one
temporary database-failure trigger are created; existing task rows are preserved.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
from queue import Empty, Queue
from threading import Thread
import time
from uuid import uuid4
from zoneinfo import ZoneInfo

from local_http import FixtureApi
from local_runtime import mysql_command


BASE = '/teaching/teachingAdditionalWork'
BUSINESS_ZONE = ZoneInfo('Asia/Shanghai')


class MySqlSession:
    """Keep a real SQL transaction open; query markers avoid timing-based lock setup."""
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
        marker = 'query_complete_' + uuid4().hex
        self.process.stdin.write(statement + ";\nSELECT '" + marker + "';\n")
        self.process.stdin.flush()
        rows = []
        deadline = time.monotonic() + 10
        while True:
            try:
                line = self.lines.get(timeout=max(0.01, deadline - time.monotonic()))
            except Empty:
                raise RuntimeError('Owned SQL session did not finish its query')
            if line is None:
                raise RuntimeError('Owned SQL session failed')
            if line == marker:
                return rows
            rows.append(line)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, value, traceback):
        # Closing a connection rolls back any unreleased fixture lock.
        self.process.stdin.close()
        try:
            self.process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=3)
        self.process.stdout.close()


def verify(args):
    runtime = args.runtime.resolve()
    checks = []
    with FixtureApi(runtime, args.jar) as api:
        def sql(statement):
            result = subprocess.run(mysql_command(runtime) + ['teachingopen_dev', '-e', statement],
                                    capture_output=True, text=True, timeout=20)
            if result.returncode:
                raise RuntimeError('Owned additional-work fixture SQL failed')
            return result.stdout.strip()

        def check(name, passed):
            checks.append({'case': name, 'passed': bool(passed)})
            print(('PASS ' if passed else 'FAIL ') + name, flush=True)
            if not passed:
                raise AssertionError(name)

        def snapshot():
            # Task rows and both kinds of assignment counters are covered.
            state = {table: hashlib.sha256(sql('SELECT * FROM ' + table + ' ORDER BY id').encode()).hexdigest()
                     for table in ('teaching_additional_work', 'teaching_depart_day_log')}
            for department in ('fixture_class_a', 'fixture_class_b'):
                marker = 'departLog:addiWorkAssign:' + department
                state[marker] = hashlib.sha256('\n'.join(sorted(api.cache('SMEMBERS', marker).splitlines())).encode()).hexdigest()
            return state

        def send(method, route, actor, body=None):
            return api.request(method, BASE + route, actor, body)[1]

        def allowed(name, method, route, actor, body=None):
            result = send(method, route, actor, body)
            check(name, result is not None and result.get('success') is True)

        def denied(name, method, route, actor, body=None):
            before = snapshot()
            result = send(method, route, actor, body)
            check(name, result is not None and result.get('success') is False)
            check(name + ' leaves tasks statistics and Redis unchanged', snapshot() == before)

        for actor in ('admin', 'teacher_a', 'teacher_b', 'student_a', 'student_b'):
            api.login(actor)
        if sql("SELECT COUNT(*) FROM sys_depart WHERE id IN ('fixture_class_a','fixture_class_b') AND del_flag='0'") != '2':
            raise RuntimeError('Expected exact synthetic class fixtures')
        for suffix in ('a', 'b'):
            if sql("SELECT depart_ids FROM sys_user WHERE id='fixture_teacher_" + suffix + "'") != 'fixture_class_' + suffix:
                raise RuntimeError('Teacher fixture management scope changed')

        prefix = 'additional_auth_' + uuid4().hex[:12]
        trigger = prefix + '_reject'
        created = []
        new_a, new_b = prefix + '_a', prefix + '_b'
        existing_snapshot = hashlib.sha256(sql('SELECT * FROM teaching_additional_work ORDER BY id').encode()).hexdigest()
        original_logs = sql('SELECT * FROM teaching_depart_day_log ORDER BY id')
        # Restore only the owned class statistics after this isolated acceptance.
        columns = sql('SHOW COLUMNS FROM teaching_depart_day_log').splitlines()
        if any(not row.split('\t')[0].replace('_', '').isalnum() for row in columns):
            raise RuntimeError('Unexpected class statistics schema')
        log_columns = [row.split('\t')[0] for row in columns]
        saved_logs = sql('SELECT ' + ','.join("IFNULL(HEX(CAST(`" + column + "` AS BINARY)),'NULL')" for column in log_columns)
                         + " FROM teaching_depart_day_log WHERE depart_id IN ('fixture_class_a','fixture_class_b') ORDER BY id").splitlines()
        unit_marker = 'departLog:unitView:fixture_class_a'
        unit_member = json.dumps('fixture_unit_a')
        original_unit_marker = api.cache('SISMEMBER', unit_marker, unit_member) == '1'

        def body(name, department='fixture_class_a', **extra):
            return {'workName': name, 'workDept': department, 'status': 1, 'codeType': 0,
                    'workDesc': '仅合成权限验收', **extra}

        def business_day():
            return "'" + datetime.now(BUSINESS_ZONE).date().isoformat() + "'"

        original_day_assignments = int(sql("SELECT COALESCE(SUM(additional_work_assign_count),0) "
                                           "FROM teaching_depart_day_log WHERE depart_id='fixture_class_a' "
                                           "AND create_time=" + business_day()))

        def concurrent_assignments(label, initial_count, mixed=False):
            day = business_day()
            # Both distinct writers establish their role-read RR snapshot before
            # waiting on this class lock. One cannot publish before both waiters
            # are observed in actual InnoDB lock metadata.
            sql("DELETE FROM teaching_depart_day_log WHERE depart_id='fixture_class_a' AND create_time=" + day)
            first_day = label in ('first-day', 'mix-first')
            if not first_day:
                sql("INSERT INTO teaching_depart_day_log (id,depart_id,depart_name,create_time,additional_work_assign_count,"
                    "unit_open_count,course_work_assign_count,course_work_correct_count,course_work_submit_count,"
                    "additional_work_correct_count,additional_work_submit_count) VALUES ('" + prefix + '_' + label
                    + "','fixture_class_a','合成并发验收'," + day + ',' + ('NULL' if initial_count is None else str(initial_count))
                    + ',2,3,4,5,6,7)')
            if mixed:
                # Exercise the actual legacy addLog caller, preserving its owned marker afterward.
                api.cache('SREM', unit_marker, unit_member)
            with MySqlSession(runtime) as guard, ThreadPoolExecutor(max_workers=2) as pool:
                connection_id = guard.run('SELECT CONNECTION_ID()')[0]
                check(label + ' probe uses MySQL REPEATABLE READ', guard.run('SELECT @@transaction_isolation') == ['REPEATABLE-READ'])
                guard.run('START TRANSACTION')
                guard.run("SELECT id FROM sys_depart WHERE id='fixture_class_a' FOR UPDATE")
                requests = [pool.submit(send, 'POST', '/add', 'admin', body(prefix + '_concurrent_' + label + '_admin'))]
                if mixed:
                    requests.append(pool.submit(lambda: api.request('GET', '/teaching/teachingDepartDayLog/unitViewLog?unitId=fixture_unit_a', 'teacher_a')[1]))
                else:
                    requests.append(pool.submit(send, 'POST', '/add', 'teacher_a', body(prefix + '_concurrent_' + label + '_teacher_a')))
                try:
                    deadline = time.monotonic() + 8
                    waiting = '0'
                    while time.monotonic() < deadline:
                        waiting = sql('SELECT COUNT(DISTINCT w.REQUESTING_ENGINE_TRANSACTION_ID) '
                                      'FROM performance_schema.data_lock_waits w '
                                      'JOIN performance_schema.threads t ON t.THREAD_ID=w.BLOCKING_THREAD_ID '
                                      'JOIN performance_schema.data_locks l ON l.ENGINE_LOCK_ID=w.REQUESTING_ENGINE_LOCK_ID '
                                      'WHERE t.PROCESSLIST_ID=' + connection_id + " AND l.OBJECT_NAME='sys_depart'")
                        if waiting == '2':
                            break
                        if any(request.done() for request in requests):
                            break
                        time.sleep(0.025)
                    check(label + ' both HTTP writers wait on the same real class lock', waiting == '2')
                finally:
                    guard.run('COMMIT')
                results = [request.result(timeout=20) for request in requests]
            task_ids = sql("SELECT id FROM teaching_additional_work WHERE work_name IN ("
                           + ','.join("'" + prefix + '_concurrent_' + label + '_' + actor + "'" for actor in ('admin', 'teacher_a'))
                           + ') ORDER BY id').splitlines()
            created.extend(task_ids)
            assignments = 1 if mixed else 2
            check(label + ' administrator and teacher both complete their events successfully',
                  len(task_ids) == assignments and all(result and result.get('success') is True for result in results))
            check(label + ' concurrent events preserve exactly one day row and assignment increments',
                  sql("SELECT COUNT(*),SUM(additional_work_assign_count) FROM teaching_depart_day_log "
                      "WHERE depart_id='fixture_class_a' AND create_time=" + day)
                  == '1\t' + str((initial_count or 0) + assignments))
            expected_units = (0 if first_day else 2) + (1 if mixed else 0)
            check(label + ' unit event increments only its counter and other statistics are preserved',
                  sql("SELECT unit_open_count,course_work_assign_count,course_work_correct_count,course_work_submit_count,"
                      "additional_work_correct_count,additional_work_submit_count FROM teaching_depart_day_log "
                      "WHERE depart_id='fixture_class_a' AND create_time=" + day)
                  == str(expected_units) + ('\t0\t0\t0\t0\t0' if first_day else '\t3\t4\t5\t6\t7'))
            check(label + ' committed assignments have Redis markers',
                  all(api.cache('SISMEMBER', 'departLog:addiWorkAssign:fixture_class_a', json.dumps(task_id)) == '1'
                      for task_id in task_ids))

        try:
            denied('student cannot add task', 'POST', '/add', 'student_a', body(prefix))
            denied('teacher cannot assign another class', 'POST', '/add', 'teacher_a', body(prefix, 'fixture_class_b'))
            denied('teacher cannot assign a mixed class set', 'POST', '/add', 'teacher_a', body(prefix, 'fixture_class_a,fixture_class_b'))
            allowed('teacher creates task in own class with legacy fields', 'POST', '/add', 'teacher_a',
                    body(new_a, id='fixture_additional_b', createBy='fixture_teacher_b', sysOrgCode='forged-org', createTime='2000-01-01 00:00:00'))
            task_a = sql("SELECT id FROM teaching_additional_work WHERE work_name='" + new_a + "'")
            if not task_a or '\n' in task_a or not task_a.isdigit():
                raise RuntimeError('Expected a newly generated task ID')
            created.append(task_a)
            check('client cannot choose task id or owner', sql("SELECT create_by FROM teaching_additional_work WHERE id='" + task_a + "'") == 'fixture_teacher_a')
            check('task receives server creation time', sql("SELECT COUNT(*) FROM teaching_additional_work WHERE id='" + task_a + "' AND create_time>'2000-01-01'") == '1')
            check('assignment Redis marker contains generated id', api.cache('SISMEMBER', 'departLog:addiWorkAssign:fixture_class_a', json.dumps(task_a)) == '1')
            for actor in ('student_a', 'teacher_b'):
                denied(actor + ' cannot edit another task', 'PUT', '/edit', actor, body(new_a, id=task_a, createBy='fixture_' + actor))
                denied(actor + ' cannot delete another task', 'DELETE', '/delete?id=' + task_a, actor)
                denied(actor + ' cannot batch delete another task', 'DELETE', '/deleteBatch?ids=' + task_a, actor)
            denied('teacher cannot move own task to another class', 'PUT', '/edit', 'teacher_a', body(new_a, 'fixture_class_b', id=task_a))
            before_edit = sql("SELECT create_by,create_time,IFNULL(sys_org_code,'~') FROM teaching_additional_work WHERE id='" + task_a + "'")
            allowed('owner edits ordinary fields from legacy whole entity', 'PUT', '/edit', 'teacher_a',
                    body(new_a + '_edited', id=task_a, createBy='fixture_admin', sysOrgCode='forged-org', createTime='2000-01-01 00:00:00'))
            check('edit preserves owner creation time and organization', sql("SELECT create_by,create_time,IFNULL(sys_org_code,'~') FROM teaching_additional_work WHERE id='" + task_a + "'") == before_edit)
            allowed('other teacher creates own task', 'POST', '/add', 'teacher_b', body(new_b, 'fixture_class_b'))
            task_b = sql("SELECT id FROM teaching_additional_work WHERE work_name='" + new_b + "'")
            if not task_b or '\n' in task_b or not task_b.isdigit():
                raise RuntimeError('Expected other teacher generated task ID')
            created.append(task_b)
            denied('mixed-owner batch deletes nothing', 'DELETE', '/deleteBatch?ids=' + task_a + ',' + task_b, 'teacher_a')
            denied('mixed-existing-and-missing batch deletes nothing', 'DELETE', '/deleteBatch?ids=' + task_a + ',' + prefix + '_missing', 'teacher_a')
            sql("UPDATE teaching_additional_work SET work_dept='fixture_class_a,fixture_class_b' WHERE id='" + task_a + "'")
            denied('old out-of-scope class blocks moving task back', 'PUT', '/edit', 'teacher_a', body(new_a, id=task_a))
            denied('old out-of-scope class blocks deletion', 'DELETE', '/delete?id=' + task_a, 'teacher_a')
            sql("UPDATE teaching_additional_work SET work_dept='fixture_class_a' WHERE id='" + task_a + "'")
            check('sequential events use one explicit Shanghai business date',
                  sql("SELECT COUNT(*),SUM(additional_work_assign_count) FROM teaching_depart_day_log "
                      "WHERE depart_id='fixture_class_a' AND create_time=" + business_day())
                  == '1\t' + str(original_day_assignments + 1))
            # The task INSERT fails in the actual MySQL transaction, not a stub.
            sql('CREATE TRIGGER ' + trigger + " BEFORE INSERT ON teaching_additional_work FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='synthetic task failure'")
            try:
                denied('database task failure leaves counters and tasks unchanged', 'POST', '/add', 'teacher_a', body(prefix + '_fail'))
            finally:
                sql('DROP TRIGGER ' + trigger)
            sql('CREATE TRIGGER ' + trigger + " BEFORE UPDATE ON teaching_depart_day_log FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='synthetic assignment log failure'")
            try:
                denied('log failure rolls back previously inserted task', 'POST', '/add', 'teacher_a', body(prefix + '_logfail'))
            finally:
                sql('DROP TRIGGER ' + trigger)
            concurrent_assignments('existing', 7)
            concurrent_assignments('first-day', 0)
            concurrent_assignments('null-count', None)
            concurrent_assignments('mix-exist', 7, mixed=True)
            concurrent_assignments('mix-first', 0, mixed=True)
            # First-day log INSERT must also roll back the preceding task INSERT.
            sql("DELETE FROM teaching_depart_day_log WHERE depart_id='fixture_class_a' AND create_time=" + business_day())
            sql('CREATE TRIGGER ' + trigger + " BEFORE INSERT ON teaching_depart_day_log FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='synthetic first-day log failure'")
            try:
                denied('first-day log failure rolls back task and Redis', 'POST', '/add', 'teacher_a', body(prefix + '_firstlogfail'))
            finally:
                sql('DROP TRIGGER ' + trigger)
            for actor in ('student_a', 'student_b'):
                status, result, _ = api.request('GET', '/teaching/teachingWork/mineAdditionalWork', actor)
                check(actor + ' can still read assigned additional work', status == 200 and result is not None and result.get('success') is True)
            status, result, _ = api.request('POST', BASE + '/importExcel', 'student_a', {})
            check('legacy additional-work import route remains unavailable', status in (404, 405))
            allowed('owner batch delete accepts legacy trailing comma', 'DELETE', '/deleteBatch?ids=' + task_a + ',', 'teacher_a')
            allowed('administrator may delete another teachers task', 'DELETE', '/delete?id=' + task_b, 'admin')
            check('both authorized deletions persisted', sql("SELECT COUNT(*) FROM teaching_additional_work WHERE id IN ('" + task_a + "','" + task_b + "')") == '0')
        finally:
            if sql("SELECT COUNT(*) FROM information_schema.triggers WHERE trigger_schema=DATABASE() AND trigger_name='" + trigger + "'") == '1':
                sql('DROP TRIGGER ' + trigger)
            # Discover also a successful concurrent request if a later assertion failed.
            created = sorted(set(created + sql("SELECT id FROM teaching_additional_work WHERE LEFT(work_name,"
                                              + str(len(prefix)) + ")='" + prefix + "'").splitlines()))
            if created:
                sql("DELETE FROM teaching_additional_work WHERE id IN (" + ','.join("'" + item + "'" for item in created) + ')')
                for department in ('fixture_class_a', 'fixture_class_b'):
                    api.cache('SREM', 'departLog:addiWorkAssign:' + department, *[json.dumps(item) for item in created])
            if original_unit_marker:
                api.cache('SADD', unit_marker, unit_member)
            else:
                api.cache('SREM', unit_marker, unit_member)
            sql("DELETE FROM teaching_depart_day_log WHERE depart_id IN ('fixture_class_a','fixture_class_b')")
            if saved_logs:
                sql('INSERT INTO teaching_depart_day_log (' + ','.join('`' + column + '`' for column in log_columns) + ') VALUES '
                    + ','.join('(' + ','.join('NULL' if value == 'NULL' else "CONVERT(X'" + value + "' USING utf8mb4)" for value in row.split('\t')) + ')' for row in saved_logs))
        check('original additional-work tasks preserved', hashlib.sha256(sql('SELECT * FROM teaching_additional_work ORDER BY id').encode()).hexdigest() == existing_snapshot)
        check('original class statistics restored', sql('SELECT * FROM teaching_depart_day_log ORDER BY id') == original_logs)
        report = {'observed_utc': datetime.now(timezone.utc).isoformat(), 'scope': 'owned synthetic HTTP/MySQL',
                  'jar_sha256': api.jar_sha256, 'business_timezone': 'Asia/Shanghai', 'production_connected': False, 'checks': checks,
                  'passed': len(checks), 'failed': 0}
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--jar', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    verify(parser.parse_args())
