#!/usr/bin/env python3
"""Verify new clone identity, task conflicts, and whole-batch rollback on MySQL."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
from threading import Barrier

from local_http import FixtureApi
from local_recovery import file_inventory, private_write, quote, sql

PREFIX = 'fixture_cloneprobe_'
NAME = 'clone-probe-'
TRIGGER = PREFIX + 'reject_insert'
TABLES = ('teaching_work', 'teaching_course', 'teaching_course_unit', 'teaching_course_dept',
          'teaching_additional_work', 'teaching_work_correct', 'teaching_work_comment', 'sys_file', 'sys_user_depart', 'sys_user')
BASE = '/teaching/teachingWork/'


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

        columns = {table: [line.split('\t')[0] for line in query('SHOW COLUMNS FROM teachingopen_dev.' + table).splitlines()]
                   for table in TABLES}

        def rows(table, where=''):
            fields = ','.join("IFNULL(HEX(CAST(" + quote(c) + " AS BINARY)),'~')" for c in columns[table])
            return query("SELECT 'ROW'," + fields + ' FROM teachingopen_dev.' + table + where + ' ORDER BY id')

        def snapshot():
            return {table: rows(table) for table in TABLES}

        def clone(source, recipients, actor='admin'):
            return api.request('POST', BASE + 'sendWork', actor,
                               {'sendWorkId': PREFIX + source, 'userIdList': recipients})

        def create_work(suffix, owner, department, unit='', additional='', file_id='fixture_file_b'):
            query('INSERT INTO teachingopen_dev.teaching_work '
                  '(id,user_id,depart_id,course_id,additional_id,work_name,work_type,work_file,work_cover,work_status,'
                  'has_cloud_data,del_flag,view_num,star_num,collect_num,create_by,create_time,update_by,update_time)'
                  " VALUES ('" + PREFIX + suffix + "','" + owner + "','" + department + "','" + unit + "','" + additional
                  + "','" + NAME + ('same' if suffix in ('source', 'old') else suffix)
                  + "','1','" + file_id + "','" + file_id + "','4',1,0,23,17,9,'fixture_teacher_b',"
                  "'2026-09-01 01:02:03','source-editor','2026-09-02 04:05:06')")

        original, files = snapshot(), file_inventory(api.runtime / 'uploads')
        original_teacher_depart = query("SELECT IFNULL(HEX(depart_ids),'~') FROM teachingopen_dev.sys_user WHERE id='fixture_teacher_b'")
        original_org_codes = query("SELECT HEX(id),IFNULL(HEX(org_code),'~') FROM teachingopen_dev.sys_user ORDER BY id").splitlines()
        for table in TABLES:
            if query('SELECT COUNT(*) FROM teachingopen_dev.' + table + " WHERE id LIKE '" + PREFIX + "%'") != '0':
                raise RuntimeError('Existing probe rows; refusing overwrite')
        if query("SELECT COUNT(*) FROM teachingopen_dev.teaching_work WHERE work_name LIKE '" + NAME + "%'") != '0':
            raise RuntimeError('Existing clone probe names; refusing overwrite')
        if query("SELECT COUNT(*) FROM information_schema.triggers WHERE trigger_schema='teachingopen_dev' AND trigger_name='" + TRIGGER + "'") != '0':
            raise RuntimeError('Existing probe trigger; refusing overwrite')
        try:
            for actor in ('admin', 'teacher_a', 'teacher_b', 'student_a'):
                api.login(actor)
            # The recipient attends both courses, but its existing course A work
            # must keep its identity, attachment and teaching feedback.
            query("INSERT INTO teachingopen_dev.sys_user_depart (id,user_id,dep_id) VALUES ('" + PREFIX
                  + "membership','fixture_student_a','fixture_class_b')")
            for side in ('a', 'b'):
                query("INSERT INTO teachingopen_dev.teaching_course (id,course_name,del_flag,is_shared) VALUES ('"
                      + PREFIX + "course_" + side + "','clone probe course',0,0)")
                query("INSERT INTO teachingopen_dev.teaching_course_dept (id,course_id,dept_id) VALUES ('"
                      + PREFIX + "assignment_" + side + "','" + PREFIX + "course_" + side + "','fixture_class_" + side + "')")
                query("INSERT INTO teachingopen_dev.teaching_course_unit (id,course_id,unit_name,del_flag) VALUES ('"
                      + PREFIX + "unit_" + side + "','" + PREFIX + "course_" + side + "','clone probe unit',0)")
            create_work('old', 'fixture_student_a', 'fixture_class_a', PREFIX + 'unit_a', file_id='fixture_file_a')
            create_work('source', 'fixture_teacher_b', 'fixture_class_b', PREFIX + 'unit_b')
            create_work('independent', 'fixture_teacher_b', 'fixture_class_b')
            create_work('additional', 'fixture_teacher_b', 'fixture_class_b', additional='fixture_additional_b')
            create_work('fail', 'fixture_teacher_b', 'fixture_class_b')
            for suffix in ('old', 'source'):
                query("INSERT INTO teachingopen_dev.teaching_work_correct (id,work_id,score,comment) VALUES ('"
                      + PREFIX + 'correct_' + suffix + "','" + PREFIX + suffix + "',4,'source private grading')")
                query("INSERT INTO teachingopen_dev.teaching_work_comment (id,work_id,user_id,comment) VALUES ('"
                      + PREFIX + 'comment_' + suffix + "','" + PREFIX + suffix + "','fixture_teacher_b','source private comment')")
            old_row = rows('teaching_work', " WHERE id='" + PREFIX + "old'")
            source_row = rows('teaching_work', " WHERE id='" + PREFIX + "source'")
            check('authorized teacher creates a new clone despite another-course same name',
                  success(clone('source', ['fixture_student_a'], 'teacher_b')))
            clone_id = query("SELECT id FROM teachingopen_dev.teaching_work WHERE work_name='" + NAME
                             + "same' AND user_id='fixture_student_a' AND course_id='" + PREFIX + "unit_b'")
            check('same-name clone receives a new identity', bool(clone_id) and '\n' not in clone_id and clone_id not in (PREFIX + 'old', PREFIX + 'source'))
            check('other-course work and source preserve all their columns',
                  rows('teaching_work', " WHERE id='" + PREFIX + "old'") == old_row
                  and rows('teaching_work', " WHERE id='" + PREFIX + "source'") == source_row)
            if clone_id and '\n' not in clone_id:
                state = query("SELECT CONCAT_WS('|',work_file,work_cover,course_id,depart_id,work_status,view_num,star_num,collect_num,"
                              "has_cloud_data,create_by,COALESCE(update_by,'NULL'),COALESCE(update_time,'NULL')) FROM teachingopen_dev.teaching_work WHERE id='" + clone_id + "'")
                check('clone keeps content and task while starting a clean draft with actual creator',
                      state == 'fixture_file_b|fixture_file_b|' + PREFIX + 'unit_b|fixture_class_b|0|0|0|0|0|fixture_teacher_b|NULL|NULL')
                check('clone has no copied grading or comments',
                      all(query("SELECT COUNT(*) FROM teachingopen_dev." + table + " WHERE work_id='" + clone_id + "'") == '0'
                          for table in ('teaching_work_correct', 'teaching_work_comment')))
                response = api.request('GET', BASE + 'queryById?id=' + clone_id, 'student_a')
                check('recipient can read its actual newly created draft', success(response) and response[1]['result']['id'] == clone_id)
            check('clone changes neither file metadata nor attachment bytes',
                  rows('sys_file') == original['sys_file'] and file_inventory(api.runtime / 'uploads') == files)

            # The actor can manage both classes, but recipients must qualify for
            # the source task in its saved class, even when the task spans A/B.
            query("UPDATE teachingopen_dev.sys_user SET depart_ids='fixture_class_a,fixture_class_b' WHERE id='fixture_teacher_b'")
            query("INSERT INTO teachingopen_dev.sys_user_depart (id,user_id,dep_id) VALUES ('" + PREFIX
                  + "teacher_dept','fixture_teacher_b','fixture_class_a')")
            # Refresh actual login data, which carries the teacher's managed scope.
            api.request('GET', '/sys/logout', 'teacher_b'); api.login('teacher_b')
            query("INSERT INTO teachingopen_dev.teaching_course_unit (id,course_id,unit_name,del_flag) VALUES ('"
                  + PREFIX + "unit_eligible','" + PREFIX + "course_a','clone eligibility unit',0)")
            query("INSERT INTO teachingopen_dev.teaching_additional_work (id,work_name,work_dept,status,code_type) VALUES ('"
                  + PREFIX + "additional_a','clone eligibility task','fixture_class_a',1,0)")
            create_work('eligible_c', 'fixture_teacher_a', 'fixture_class_a', PREFIX + 'unit_eligible')
            create_work('eligible_a', 'fixture_teacher_a', 'fixture_class_a', additional=PREFIX + 'additional_a')
            def rejected_without_writes(label, source, recipients, actor='teacher_b'):
                before = snapshot()
                check(label, not success(clone(source, recipients, actor)) and snapshot() == before)
            for alias in ('FIXTURE_STUDENT_A', 'fixture_student_a '):
                rejected_without_writes('noncanonical recipient cannot create an unusable draft ' + repr(alias),
                                        'independent', [alias], 'admin')
                rejected_without_writes('noncanonical recipient rejects a mixed batch without writes ' + repr(alias),
                                        'independent', ['fixture_student_b', alias], 'admin')
            for source in ('eligible_c', 'eligible_a'):
                rejected_without_writes('multi-class teacher cannot clone A task to B-only recipient ' + source, source, ['fixture_student_b'])
                rejected_without_writes('administrator also checks recipient task eligibility ' + source, source, ['fixture_student_b'], 'admin')
                rejected_without_writes('one eligible and one ineligible recipient rejects the entire batch ' + source,
                                        source, ['fixture_student_a', 'fixture_student_b'])
            query("INSERT INTO teachingopen_dev.teaching_course_dept (id,course_id,dept_id) VALUES ('"
                  + PREFIX + "assign_shared','" + PREFIX + "course_a','fixture_class_b')")
            query("UPDATE teachingopen_dev.teaching_additional_work SET work_dept='fixture_class_a,fixture_class_b' WHERE id='"
                  + PREFIX + "additional_a'")
            for source in ('eligible_c', 'eligible_a'):
                rejected_without_writes('A source remains bound to A when task also spans B ' + source, source, ['fixture_student_b'])
            query("UPDATE teachingopen_dev.teaching_course_unit SET del_flag=1 WHERE id='" + PREFIX + "unit_eligible'")
            rejected_without_writes('deleted unit rejects task clone', 'eligible_c', ['fixture_student_a'])
            query("UPDATE teachingopen_dev.teaching_course_unit SET del_flag=0 WHERE id='" + PREFIX + "unit_eligible'")
            query("UPDATE teachingopen_dev.teaching_course SET del_flag=1 WHERE id='" + PREFIX + "course_a'")
            rejected_without_writes('deleted parent course rejects task clone', 'eligible_c', ['fixture_student_a'])
            query("UPDATE teachingopen_dev.teaching_course SET del_flag=0 WHERE id='" + PREFIX + "course_a'")
            query("UPDATE teachingopen_dev.teaching_additional_work SET status=0 WHERE id='" + PREFIX + "additional_a'")
            rejected_without_writes('inactive additional task rejects clone', 'eligible_a', ['fixture_student_a'])
            query("UPDATE teachingopen_dev.teaching_additional_work SET status=1 WHERE id='" + PREFIX + "additional_a'")
            query("DELETE FROM teachingopen_dev.teaching_course_dept WHERE id='" + PREFIX + "assignment_a'")
            rejected_without_writes('removed A course assignment rejects A source despite valid B assignment', 'eligible_c', ['fixture_student_a'])
            query("INSERT INTO teachingopen_dev.teaching_course_dept (id,course_id,dept_id) VALUES ('"
                  + PREFIX + "assignment_a','" + PREFIX + "course_a','fixture_class_a')")
            check('eligible task recipient still receives a usable new draft', success(clone('eligible_c', ['fixture_student_a'], 'teacher_b')))
            eligibility_id = query("SELECT id FROM teachingopen_dev.teaching_work WHERE work_name='" + NAME
                                   + "eligible_c' AND user_id='fixture_student_a'")
            response = api.request('POST', BASE + 'submit', 'student_a', {'id': eligibility_id, 'workStatus': '0'})
            check('recipient can actually save the task clone through student submission', success(response))
            # Restore management scope before the original denied-scope checks.
            query("UPDATE teachingopen_dev.sys_user SET depart_ids=" + ("NULL" if original_teacher_depart == '~'
                  else "CONVERT(X'" + original_teacher_depart + "' USING utf8mb4)") + " WHERE id='fixture_teacher_b'")
            query("DELETE FROM teachingopen_dev.sys_user_depart WHERE id='" + PREFIX + "teacher_dept'")
            api.request('GET', '/sys/logout', 'teacher_b'); api.login('teacher_b')

            before = snapshot()
            response = clone('source', ['fixture_student_a'])
            check('same task is rejected with an actionable conflict', not success(response) and response[1]
                  and '已有该任务' in response[1].get('message', '') and snapshot() == before)
            response = clone('source', ['fixture_student_b', 'fixture_teacher_b'])
            check('late task conflict rejects the entire batch before any write', not success(response) and snapshot() == before)
            for recipients, actor, label in [(['fixture_student_a', 'z_missing_probe'], 'admin', 'missing recipient'),
                                               (['fixture_student_a', 'fixture_student_a'], 'admin', 'duplicate recipient'),
                                               (['fixture_student_a', 'fixture_teacher_a'], 'teacher_b', 'out-of-scope recipient'),
                                               (['fixture_student_a'], 'student_a', 'student management')]:
                response = clone('independent', recipients, actor)
                check(label + ' rejects without partial writes', not success(response) and snapshot() == before)

            query("UPDATE teachingopen_dev.teaching_work SET del_flag=1 WHERE id='" + PREFIX + "independent'")
            before = snapshot()
            check('deleted source cannot create any clone', not success(clone('independent', ['fixture_student_a'])) and snapshot() == before)
            query("UPDATE teachingopen_dev.teaching_work SET del_flag=0 WHERE id='" + PREFIX + "independent'")

            check('additional-task clone can create its first draft', success(clone('additional', ['fixture_student_a'], 'teacher_b')))
            before = snapshot()
            check('additional-task duplicate also fails without writes', not success(clone('additional', ['fixture_student_a'], 'teacher_b')) and snapshot() == before)
            barrier = Barrier(2, timeout=10)
            def clone_together(_):
                barrier.wait()
                return clone('additional', ['fixture_student_b'], 'teacher_b')
            with ThreadPoolExecutor(max_workers=2) as pool:
                replies = list(pool.map(clone_together, range(2)))
            check('concurrent clones for the same task produce one draft and one conflict',
                  sum(bool(success(response)) for response in replies) == 1
                  and query("SELECT COUNT(*) FROM teachingopen_dev.teaching_work WHERE additional_id='fixture_additional_b' AND user_id='fixture_student_b'") == '1')
            independent_before = rows('teaching_work', " WHERE id='" + PREFIX + "independent'")
            check('standalone clone permits another new identity on repeated requests',
                  success(clone('independent', ['fixture_student_a'], 'teacher_b'))
                  and success(clone('independent', ['fixture_student_a'], 'teacher_b'))
                  and query("SELECT COUNT(*) FROM teachingopen_dev.teaching_work WHERE work_name='" + NAME + "independent' AND user_id='fixture_student_a'") == '2'
                  and rows('teaching_work', " WHERE id='" + PREFIX + "independent'") == independent_before)

            # Synthetic-only failure on the second sorted recipient. The first
            # INSERT has already run, so equality proves the service transaction
            # rolled it back instead of silently returning a successful count.
            query("CREATE TRIGGER teachingopen_dev." + TRIGGER + " BEFORE INSERT ON teachingopen_dev.teaching_work FOR EACH ROW "
                  "SET NEW.work_type = IF(NEW.work_name='" + NAME + "fail' AND NEW.user_id='fixture_teacher_b', REPEAT('x',100), NEW.work_type)")
            before = snapshot()
            response = clone('fail', ['fixture_student_a', 'fixture_teacher_b'])
            check('second INSERT failure returns no success and rolls back the first INSERT', not success(response) and snapshot() == before)
            query('DROP TRIGGER teachingopen_dev.' + TRIGGER)
            check('batch can be retried successfully after the synthetic failure is removed',
                  success(clone('fail', ['fixture_student_a', 'fixture_teacher_b']))
                  and query("SELECT COUNT(*) FROM teachingopen_dev.teaching_work WHERE work_name='" + NAME + "fail' AND user_id IN ('fixture_student_a','fixture_teacher_b')") == '3')
            jar_hash = api.jar_sha256
        finally:
            query('DROP TRIGGER IF EXISTS teachingopen_dev.' + TRIGGER)
            for table in ('teaching_work_correct', 'teaching_work_comment'):
                query('DELETE FROM teachingopen_dev.' + table + " WHERE id LIKE '" + PREFIX + "%'")
            query("DELETE FROM teachingopen_dev.teaching_work WHERE work_name LIKE '" + NAME + "%'")
            query("DELETE FROM teachingopen_dev.teaching_course_unit WHERE id LIKE '" + PREFIX + "%'")
            query("DELETE FROM teachingopen_dev.teaching_course_dept WHERE id LIKE '" + PREFIX + "%'")
            query("DELETE FROM teachingopen_dev.teaching_course WHERE id LIKE '" + PREFIX + "%'")
            query("DELETE FROM teachingopen_dev.teaching_additional_work WHERE id LIKE '" + PREFIX + "%'")
            query("DELETE FROM teachingopen_dev.sys_user_depart WHERE id LIKE '" + PREFIX + "%'")
            query("UPDATE teachingopen_dev.sys_user SET depart_ids=" + ("NULL" if original_teacher_depart == '~'
                  else "CONVERT(X'" + original_teacher_depart + "' USING utf8mb4)") + " WHERE id='fixture_teacher_b'")
            for row in original_org_codes:
                user_id, org_code = row.split('\t')
                query("UPDATE teachingopen_dev.sys_user SET org_code=" + ("NULL" if org_code == '~'
                      else "CONVERT(X'" + org_code + "' USING utf8mb4)") + " WHERE id=CONVERT(X'" + user_id + "' USING utf8mb4)")
        check('all original business rows restored', snapshot() == original)
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
