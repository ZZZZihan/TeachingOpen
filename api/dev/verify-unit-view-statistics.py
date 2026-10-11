#!/usr/bin/env python3
"""Ordinary legal unit-view HTTP regression on an owned synthetic candidate.

No database/network failure injection. Back up and restore affected business
rows and the two legacy sets; retain normal login/request audit records.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
from threading import Barrier
from urllib.parse import urlencode
from uuid import uuid4

from local_http import FixtureApi
from local_runtime import mysql_command
from media_index_fixture import media_index_snapshot, rebuild_media_index_after_sql

BASE = '/teaching/teachingDepartDayLog/unitViewLog?'
CLASSES = ('fixture_class_a', 'fixture_class_b')
TABLES = {'teaching_course_unit': 'id', 'teaching_course_dept': 'id',
          'sys_user_depart': 'ID', 'teaching_depart_day_log': 'id',
          'teaching_unit_view_event': 'depart_id,unit_id'}


def literal(value):
    return 'CONVERT(0x' + str(value).encode().hex() + ' USING utf8mb4)'


def verify(args):
    output = args.output.resolve()
    if output.exists():
        raise RuntimeError('Preserve existing unit-view evidence')
    output.parent.mkdir(parents=True, exist_ok=True)
    checks = []
    report = {'observed_utc': datetime.now(timezone.utc).isoformat(),
        'scope': 'ordinary legal Shiro HTTP, synthetic MySQL and Redis; no failure injection',
        'production_connected': False, 'checks': checks, 'audit_logs_retained': True,
        'counting_identity': 2, 'counting_identity_meaning': 'superior; ordinary student identity 1 remains a no-op'}

    def check(name, passed):
        checks.append({'case': name, 'passed': bool(passed)})
        print(('PASS ' if passed else 'FAIL ') + name, flush=True)
        if not passed:
            raise AssertionError(name)

    try:
        with FixtureApi(args.runtime.resolve(), args.jar) as api:
            has_media_index = not getattr(args, 'expect_legacy', False)
            report['jar_sha256'] = api.jar_sha256
            def sql(statement):
                result = subprocess.run(mysql_command(api.runtime) + ['teachingopen_dev'],
                    input=statement, text=True, capture_output=True, timeout=30)
                if result.returncode:
                    raise RuntimeError('Owned unit-view fixture SQL failed')
                if has_media_index:
                    rebuild_media_index_after_sql(api, statement)
                return result.stdout.strip()

            def rows(table):
                return sql('SELECT * FROM ' + table + ' ORDER BY ' + TABLES[table])

            def db_snapshot():
                return {table: hashlib.sha256(rows(table).encode()).hexdigest() for table in TABLES}

            def dump(key):
                # Return a binary-safe snapshot without printing business values.
                script = "local v=redis.call('DUMP',KEYS[1]);if not v then return '' end;return (v:gsub('.',function(c)return string.format('%02x',string.byte(c))end))"
                value = api.cache('EVAL', script, '1', key)
                if not re.fullmatch(r'(?:[0-9a-fA-F]{2})*', value):
                    raise RuntimeError('Owned unit-view Redis snapshot returned an invalid binary encoding')
                return value

            keys = ['departLog:unitView:' + department for department in CLASSES]
            original_cache = {}
            for key in keys:
                if api.cache('TYPE', key) not in ('none', 'set') or api.cache('PTTL', key) not in ('-1', '-2'):
                    raise RuntimeError('Expected a persistent legacy set or an absent owned fixture key')
                original_cache[key] = dump(key)
            original = db_snapshot()
            original_media_index = media_index_snapshot(sql) if has_media_index else None
            report['baseline_sha256'] = original
            report['initial_ledger_rows'] = int(sql('SELECT COUNT(*) FROM teaching_unit_view_event'))
            audit_count = int(sql('SELECT COUNT(*) FROM sys_log'))
            if sql("SELECT id,user_identity FROM sys_user WHERE id IN ('fixture_teacher_a','fixture_teacher_b','fixture_student_a','fixture_student_b') ORDER BY id") != 'fixture_student_a\t1\nfixture_student_b\t1\nfixture_teacher_a\t2\nfixture_teacher_b\t2':
                raise RuntimeError('The canonical fixture identity contract changed')
            if sql("SELECT COUNT(*) FROM sys_depart WHERE id IN ('fixture_class_a','fixture_class_b') AND del_flag='0'") != '2':
                raise RuntimeError('The exact active class fixtures are required')
            fields = [row.split('\t')[0] for row in sql('SHOW COLUMNS FROM teaching_depart_day_log').splitlines()]
            if any(not re.fullmatch('[A-Za-z_][A-Za-z0-9_]*', column) for column in fields):
                raise RuntimeError('Unexpected statistics column name')
            saved_logs = sql('SELECT ' + ','.join("IFNULL(HEX(CAST(`" + column + "` AS BINARY)),'NULL')" for column in fields)
                + " FROM teaching_depart_day_log WHERE depart_id IN ('fixture_class_a','fixture_class_b') ORDER BY id").splitlines()
            prefix = 'unitview_' + uuid4().hex[:12]
            units = {kind: prefix + '_' + kind for kind in ('first', 'parallel', 'cross', 'legacy')}
            membership = prefix + '_member'; assignment = prefix + '_assignment'
            def counter(department):
                return int(sql('SELECT COALESCE(SUM(unit_open_count),0) FROM teaching_depart_day_log WHERE depart_id=' + literal(department)))
            before_counts = {department: counter(department) for department in CLASSES}

            def state(unit):
                return sql("SELECT depart_id,event_state,COALESCE(CAST(counted_day AS CHAR),'NULL') FROM teaching_unit_view_event WHERE unit_id="
                    + literal(unit) + ' ORDER BY depart_id')
            def send(unit, actor):
                return api.request('GET', BASE + urlencode({'unitId': unit}), actor)
            def accepted(response):
                return response[0] == 200 and isinstance(response[1], dict) and response[1].get('success') is True and response[1].get('code') == 200
            def conflict(response):
                return response[0] == 200 and isinstance(response[1], dict) and response[1].get('success') is False and response[1].get('code') == 409
            def concurrent(unit, actors):
                barrier = Barrier(len(actors))
                def request(actor):
                    barrier.wait(timeout=10)
                    return send(unit, actor)
                with ThreadPoolExecutor(max_workers=len(actors)) as pool:
                    replies = list(pool.map(request, actors))
                return all(accepted(response) for response in replies)

            try:
                for actor in ('teacher_a','teacher_b','student_a','student_b'):
                    api.login(actor)
                for kind, unit in units.items():
                    sql('INSERT INTO teaching_course_unit(id,course_id,unit_name,unit_intro,course_video,show_course_plan,del_flag) VALUES('
                        + literal(unit) + ",'fixture_course_a'," + literal('合成统计验收 ' + kind) + ",'正文阅读不依赖统计','[]',0,0)")
                sql('INSERT INTO teaching_course_dept(id,dept_id,course_id,open_time) VALUES (' + literal(assignment)
                    + ",'fixture_class_b','fixture_course_a','2026-01-01 00:00:00')")

                # Run independent departments before any other probe ledger insert.
                # On a fresh fixture this also covers MySQL's empty-index gap behavior.
                check('12 concurrent first views across two assigned classes all succeed', concurrent(units['cross'], ['teacher_a','teacher_b'] * 6))
                check('cross-class concurrency commits one event per class', state(units['cross']).count('COUNTED') == 2 and counter(CLASSES[0]) == before_counts[CLASSES[0]] + 1 and counter(CLASSES[1]) == before_counts[CLASSES[1]] + 1)
                cross_stable = (state(units['cross']), counter(CLASSES[0]), counter(CLASSES[1]))
                check('committed cross-class retries all succeed', concurrent(units['cross'], ['teacher_a','teacher_b'] * 6))
                check('committed cross-class retries do not count twice', (state(units['cross']), counter(CLASSES[0]), counter(CLASSES[1])) == cross_stable)
                sql('INSERT INTO sys_user_depart(ID,user_id,dep_id) VALUES (' + literal(membership)
                    + ",'fixture_teacher_b','fixture_class_a')")

                check('identity 2 class member first view succeeds', accepted(send(units['first'], 'teacher_a')))
                check('first view persists one completed lifetime event', state(units['first']).startswith('fixture_class_a\tCOUNTED\t') and state(units['first']).count('\n') == 0)
                check('first view adds one class counter', counter(CLASSES[0]) == before_counts[CLASSES[0]] + 2)
                check('event and statistics use the same Shanghai DATE', sql('SELECT COUNT(*) FROM teaching_unit_view_event e JOIN teaching_depart_day_log d ON d.depart_id=e.depart_id AND d.create_time=e.counted_day WHERE e.unit_id=' + literal(units['first'])) == '1')
                stable = (state(units['first']), counter(CLASSES[0]))
                check('ordinary retries and another eligible class member succeed', all(accepted(send(units['first'], actor)) for actor in ['teacher_a','teacher_b'] * 4))
                check('retries and another eligible member leave event and count unchanged', (state(units['first']), counter(CLASSES[0])) == stable)
                student_before = db_snapshot()
                check('ordinary students retain their legal non-counting response', accepted(send(units['first'], 'student_a')) and accepted(send('fixture_unit_b', 'student_b')))
                check('ordinary student requests write no business rows', db_snapshot() == student_before)
                check('12 concurrent first views in one class all succeed', concurrent(units['parallel'], ['teacher_a','teacher_b'] * 6))
                check('same-class concurrency persists one event and one increment', state(units['parallel']).startswith('fixture_class_a\tCOUNTED\t') and state(units['parallel']).count('\n') == 0 and counter(CLASSES[0]) == before_counts[CLASSES[0]] + 3)
                check('new events never write legacy Redis sets', all(dump(key) == value for key,value in original_cache.items()))

                sql('DELETE FROM sys_user_depart WHERE ID=' + literal(membership))
                check('same unit in another assigned class succeeds', accepted(send(units['parallel'], 'teacher_b')))
                check('different classes have independent lifetime events', state(units['parallel']).count('COUNTED') == 2 and counter(CLASSES[1]) == before_counts[CLASSES[1]] + 2)

                legacy_key = keys[0]; member = json.dumps(units['legacy'])
                api.cache('SADD', legacy_key, member)
                legacy_cache = dump(legacy_key); legacy_counts = {department: counter(department) for department in CLASSES}
                check('old serialized Redis marker produces explicit business 409', conflict(send(units['legacy'],'teacher_a')))
                check('old marker persists unresolved with no counted day', state(units['legacy']) == 'fixture_class_a\tLEGACY_UNRESOLVED\tNULL')
                check('legacy response changes no counters or old Redis bytes', {department: counter(department) for department in CLASSES} == legacy_counts and dump(legacy_key) == legacy_cache)
                check('ordinary legacy retry remains 409 without changing history', conflict(send(units['legacy'],'teacher_a')) and state(units['legacy']) == 'fixture_class_a\tLEGACY_UNRESOLVED\tNULL' and dump(legacy_key) == legacy_cache)
                content = api.request('GET','/teaching/teachingCourseUnit/mineUnit?' + urlencode({'courseId':'fixture_course_a','pageSize':100}), 'teacher_a')
                check('course content remains readable after legacy statistics conflict', accepted(content) and units['legacy'] in {row['id'] for row in content[1]['result']['records']})
            finally:
                restore = ['START TRANSACTION;', 'DELETE FROM teaching_unit_view_event WHERE unit_id IN (' + ','.join(map(literal, units.values())) + ');',
                    'DELETE FROM teaching_course_unit WHERE id IN (' + ','.join(map(literal, units.values())) + ');',
                    'DELETE FROM teaching_course_dept WHERE id=' + literal(assignment) + ';',
                    'DELETE FROM sys_user_depart WHERE ID=' + literal(membership) + ';',
                    "DELETE FROM teaching_depart_day_log WHERE depart_id IN ('fixture_class_a','fixture_class_b');"]
                for row in saved_logs:
                    values = ['NULL' if value == 'NULL' else "CONVERT(X'" + value + "' USING utf8mb4)" for value in row.split('\t')]
                    restore.append('INSERT INTO teaching_depart_day_log(' + ','.join('`' + column + '`' for column in fields) + ') VALUES(' + ','.join(values) + ');')
                sql('\n'.join(restore + ['COMMIT;']))
                for key, value in original_cache.items():
                    if value:
                        script = "local v=ARGV[1]:gsub('..',function(h)return string.char(tonumber(h,16))end);return redis.call('RESTORE',KEYS[1],0,v,'REPLACE')"
                        if api.cache('EVAL', script, '1', key, value) != 'OK':
                            raise RuntimeError('Owned unit-view Redis restore did not confirm success')
                    else:
                        if api.cache('DEL', key) not in ('0', '1'):
                            raise RuntimeError('Owned unit-view Redis cleanup did not confirm success')
                report['restored_sha256'] = db_snapshot()
                report['business_rows_restored'] = report['restored_sha256'] == original
                if has_media_index:
                    report['media_index_restored'] = media_index_snapshot(sql) == original_media_index
                report['legacy_cache_restored'] = all(dump(key) == value for key,value in original_cache.items())
            check('all affected fixture business rows are restored', report['business_rows_restored'])
            if has_media_index:
                check('original media reference index and state restored', report['media_index_restored'])
            check('both legacy cache keys are restored byte for byte', report['legacy_cache_restored'])
            check('normal request audit rows are retained', int(sql('SELECT COUNT(*) FROM sys_log')) >= audit_count)
    except Exception as failure:
        report['exception'] = type(failure).__name__
        raise
    finally:
        report.update(passed=sum(case['passed'] for case in checks), failed=sum(not case['passed'] for case in checks), total=len(checks))
        output.write_text(json.dumps(report,ensure_ascii=False,indent=2) + '\n')
        output.chmod(0o600)


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime',type=Path,required=True)
    parser.add_argument('--jar',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    verify(parser.parse_args())
