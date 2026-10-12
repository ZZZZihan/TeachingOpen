#!/usr/bin/env python3
"""Verify both assignment detail routes against current class/role boundaries."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
from uuid import uuid4

from local_http import FixtureApi
from local_runtime import mysql_command

BASE = '/teaching/teachingAdditionalWork/'
TABLES = ('teaching_additional_work', 'teaching_work', 'teaching_work_correct', 'teaching_work_comment',
          'sys_data_log', 'sys_file', 'teaching_course', 'teaching_course_dept', 'teaching_depart_day_log')


def verify(args):
    if args.output.exists():
        raise RuntimeError('Refusing to overwrite an existing evidence report')
    cases, error = [], None
    with FixtureApi(args.runtime.resolve(), args.jar) as api:
        def sql(statement):
            output = subprocess.run(mysql_command(api.runtime) + ['teachingopen_dev', '-e', statement],
                                    capture_output=True, text=True, timeout=20)
            if output.returncode:
                raise RuntimeError('Owned additional-work read fixture SQL failed: ' + output.stderr[:500])
            return output.stdout.strip()

        def literal(value):
            return 'NULL' if value is None else "CONVERT(0x" + str(value).encode().hex() + " USING utf8mb4)" if str(value) else "''"

        def insert(table, **values):
            sql('INSERT INTO ' + table + '(' + ','.join(values) + ') VALUES (' + ','.join(literal(v) for v in values.values()) + ')')

        def check(name, passed, fatal=True):
            cases.append({'case': name, 'passed': bool(passed)})
            print(('PASS ' if passed else 'FAIL ') + name, flush=True)
            if not passed and fatal:
                raise AssertionError(name)

        def snapshot():
            return {table: hashlib.sha256(sql('SELECT * FROM ' + table + ' ORDER BY id').encode()).hexdigest() for table in TABLES}

        def file_snapshot():
            return {str(p.relative_to(api.runtime / 'uploads')): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in (api.runtime / 'uploads').rglob('*') if p.is_file()}

        prefix = 'addi_read_' + uuid4().hex[:12]
        sentinel = 'private additional task ' + prefix
        original_rows, original_files = snapshot(), file_snapshot()
        try:
            for actor in ('teacher_a', 'teacher_b', 'student_a', 'student_b', 'admin'):
                api.login(actor)
            for suffix, assigned, state in [('a', 'fixture_class_a', 1), ('b', 'fixture_class_b', 1),
                                            ('draft', 'fixture_class_a', 0), ('multi', 'fixture_class_a, fixture_class_b ', 1),
                                            ('prefix', 'fixture_class_a_extra', 1)]:
                insert('teaching_additional_work', id=prefix + '_' + suffix, work_name=prefix + '_' + suffix,
                       work_desc=sentinel, work_dept=assigned, status=state, create_by='fixture_teacher_a',
                       create_time='2026-10-11 00:00:00')
            insert('teaching_course', id=prefix + '_course', course_name=prefix + '_public', course_desc='public synthetic course',
                   show_home=1, is_shared=1, del_flag=0, create_by='fixture_admin', create_time='2026-10-11 00:00:00')
            seeded = snapshot()

            def allowed(name, endpoint, suffix, actor):
                status, result, _ = api.request('GET', BASE + endpoint + '?id=' + prefix + '_' + suffix, actor)
                check(name, status == 200 and result and result.get('success') is True
                      and result.get('result', {}).get('id') == prefix + '_' + suffix
                      and result['result'].get('workDesc') == sentinel)

            def denied(name, endpoint, suffix, actor):
                status, result, _ = api.request('GET', BASE + endpoint + '?id=' + prefix + '_' + suffix, actor)
                check(name, status == (200 if actor else 401) and result and result.get('success') is False
                      and result.get('code') == (510 if actor else 401) and not result.get('result')
                      and sentinel not in json.dumps(result))

            for endpoint in ('queryById', 'getWorkInfo'):
                if args.expect_legacy:
                    allowed(endpoint + ' baseline exposes foreign published assignment to student', endpoint, 'b', 'student_a')
                    allowed(endpoint + ' baseline exposes draft assignment to student', endpoint, 'draft', 'student_a')
                    allowed(endpoint + ' baseline exposes foreign task to teacher', endpoint, 'b', 'teacher_a')
                    continue
                for actor in ('student_a', 'teacher_a', 'admin'):
                    allowed(endpoint + ' permits assigned ' + actor, endpoint, 'a', actor)
                allowed(endpoint + ' permits teacher draft preview', endpoint, 'draft', 'teacher_a')
                allowed(endpoint + ' permits administrator foreign draft', endpoint, 'draft', 'admin')
                for actor in ('student_a', 'student_b', 'teacher_a', 'teacher_b'):
                    allowed(endpoint + ' permits assigned multi-class ' + actor, endpoint, 'multi', actor)
                for actor in ('student_b', 'teacher_b'):
                    denied(endpoint + ' rejects cross-class ' + actor, endpoint, 'a', actor)
                denied(endpoint + ' rejects unpublished task for assigned student', endpoint, 'draft', 'student_a')
                denied(endpoint + ' does not use creator as class authorization', endpoint, 'b', 'teacher_a')
                denied(endpoint + ' requires exact class membership', endpoint, 'prefix', 'student_a')
                denied(endpoint + ' does not publish assignment anonymously', endpoint, 'a', None)
                denied(endpoint + ' rejects unknown ID', endpoint, 'missing', 'student_a')
                status, result, _ = api.request('GET', BASE + endpoint + '?id=' + (prefix + '_a').upper(), 'student_a')
                check(endpoint + ' rejects database collation ID alias', status == 200 and result and result.get('success') is False
                      and result.get('code') == 510 and not result.get('result'))

            status, result, _ = api.request('GET', '/teaching/teachingCourse/queryById?id=' + prefix + '_course', 'student_b')
            check('shared public course remains readable without class assignment', status == 200 and result
                  and result.get('success') is True and result.get('result', {}).get('id') == prefix + '_course')
            status, result, _ = api.request('GET', '/teaching/teachingCourse/getHomeCourse?courseName=' + prefix + '_public')
            check('anonymous public-course discovery remains available', status == 200 and result and result.get('success') is True
                  and any(row.get('id') == prefix + '_course' for row in result['result']['records']))
            check('allowed and rejected reads preserve all business rows', seeded == snapshot())
            check('allowed and rejected reads preserve all uploaded bytes', original_files == file_snapshot())
        except Exception as failure:
            error = type(failure).__name__ + ': ' + str(failure)
        finally:
            sql('DELETE FROM teaching_additional_work WHERE id LIKE ' + literal(prefix + '%'))
            sql('DELETE FROM teaching_course WHERE id=' + literal(prefix + '_course'))
        check('all original business rows restored', original_rows == snapshot(), fatal=False)
        check('all original upload bytes restored', original_files == file_snapshot(), fatal=False)
        result = {'cases': cases, 'passed': sum(case['passed'] for case in cases), 'failed': sum(not case['passed'] for case in cases),
                  'total': len(cases), 'jar_sha256': api.jar_sha256, 'expected_legacy': args.expect_legacy, 'exception': error,
                  'created_at': datetime.now(timezone.utc).isoformat(),
                  'scope': 'Actual HTTP assignment detail scope and unchanged public-course access; owned synthetic fixture only.'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    return error is None and result['failed'] == 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('runtime', 'jar', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--expect-legacy', action='store_true')
    raise SystemExit(0 if verify(parser.parse_args()) else 1)
