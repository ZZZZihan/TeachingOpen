#!/usr/bin/env python3
"""Real partial-feedback updates on task-owned fixtures; never use production data."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import threading
import json
from pathlib import Path

from local_http import FixtureApi
from local_recovery import database_inventory, file_inventory, private_write, sql


def verify(args):
    cases = []
    prefix = 'fixture_feedback_preserve_'
    work = prefix + 'work'
    fault_work = prefix + 'atomic'
    trigger = prefix + 'daily_failure'
    trigger_created = False
    marker = 'departLog:courseWorkCorrect:fixture_class_a'
    marker_changed = False
    def check(name, value):
        cases.append({'case': name, 'passed': bool(value)})
        print(('PASS ' if value else 'FAIL ') + name, flush=True)
        if not value:
            raise AssertionError(name)

    with FixtureApi(args.runtime, args.jar) as api:
        before = database_inventory(api.runtime)
        files = file_inventory(api.runtime / 'uploads')
        def query(text):
            return sql(api.runtime, 'USE teachingopen_dev;\n' + text)
        for table in ('teaching_work', 'teaching_work_correct', 'teaching_work_comment'):
            if query("SELECT COUNT(*) FROM " + table + " WHERE id LIKE '" + prefix + "%'") != '0':
                raise RuntimeError('Preserve existing probe rows')
        if query('SELECT COUNT(*) FROM teaching_depart_day_log') != '0':
            raise RuntimeError('This probe requires the unused synthetic daily-log fixture')
        if api.cache('TYPE', marker) != 'none':
            raise RuntimeError('Preserve existing correction marker data')
        if query("SELECT COUNT(*) FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA=DATABASE() AND TRIGGER_NAME='" + trigger + "'") != '0':
            raise RuntimeError('Preserve existing failure trigger')
        def snapshot():
            return {t: query("SELECT * FROM " + t + " WHERE " + ('id' if t == 'teaching_work' else 'work_id') + "='" + work + "' ORDER BY id")
                    for t in ('teaching_work', 'teaching_work_correct', 'teaching_work_comment')}
        def seed():
            query("DELETE FROM teaching_work_correct WHERE work_id='" + work + "'; DELETE FROM teaching_work_comment WHERE work_id='" + work + "';"
                  "INSERT INTO teaching_work_correct (id,work_id,score,comment,create_by,create_time) VALUES ('" + prefix + "score','" + work + "',3,'earlier feedback','fixture_teacher_a','2026-10-01 09:00:00');"
                  "INSERT INTO teaching_work_comment (id,work_id,user_id,comment,create_by,create_time) VALUES ('" + prefix + "comment','" + work + "','fixture_student_a','student discussion','fixture_student_a','2026-10-01 10:00:00')")
        def edit(body, actor='teacher_a', allowed=True):
            status, result, _ = api.request('PUT', '/teaching/teachingWork/edit', actor, {'id': work, **body})
            if allowed:
                check('edit accepted: ' + ','.join(body), status == 200 and result and result.get('success'))
            else:
                # Existing Shiro business denials use HTTP 200 / code 510;
                # missing authentication is HTTP 401 / code 401.
                check('edit denied for ' + str(actor), status == (200 if actor else 401)
                      and result and result.get('success') is False
                      and result.get('code') == (510 if actor else 401) and not result.get('result'))
            return status, result
        try:
            for actor in ('teacher_a', 'teacher_b', 'student_a', 'admin'):
                api.login(actor)
            query("INSERT INTO teaching_work (id,user_id,depart_id,work_name,work_file,work_type,work_status,work_scene,course_id,del_flag,create_by,create_time) VALUES ('" + work + "','fixture_student_a','fixture_class_a','feedback preservation probe','fixture_file_a','0','1','course','fixture_unit_a',0,'fixture_student_a','2026-10-01 08:00:00')")
            seed()
            initial = snapshot()
            edit({'workStatus': '2', 'teachingWorkCorrectList': [{'score': 0, 'comment': 'zero is a valid score'}]})
            current = snapshot()
            check('zero-score feedback persisted', query("SELECT CONCAT(score,':',comment) FROM teaching_work_correct WHERE work_id='" + work + "'") == '0:zero is a valid score')
            check('legacy grade deletes omitted comments' if args.expect_legacy else 'grade preserves omitted comments including IDs and metadata',
                  current['teaching_work_comment'] == '' if args.expect_legacy else current['teaching_work_comment'] == initial['teaching_work_comment'])
            seed()
            initial = snapshot()
            edit({'workName': 'renamed feedback probe'})
            current = snapshot()
            if args.expect_legacy:
                check('legacy metadata edit deletes feedback and comments', current['teaching_work_correct'] == '' and current['teaching_work_comment'] == '')
            else:
                check('metadata-only edit preserves both child collections', all(current[t] == initial[t] for t in ('teaching_work_correct', 'teaching_work_comment')))
                edit({'teachingWorkCorrectList': None, 'teachingWorkCommentList': None})
                current = snapshot()
                check('explicit null means unchanged for both collections', all(current[t] == initial[t] for t in ('teaching_work_correct', 'teaching_work_comment')))

                # A student posts after the teacher loaded the work. The grade body
                # deliberately omits comments rather than replaying a stale snapshot.
                status, result, _ = api.request('POST', '/teaching/teachingWork/saveComment', 'student_a', {'workId': work, 'comment': 'new discussion after teacher load'})
                check('student discussion accepted through actual endpoint', status == 200 and result and result.get('success'))
                comments = snapshot()['teaching_work_comment']
                edit({'workStatus': '2', 'teachingWorkCorrectList': [{'score': 5, 'comment': 'latest feedback'}]})
                check('grading does not erase discussion posted since initial read', snapshot()['teaching_work_comment'] == comments)
                status, feedback, _ = api.request('GET', '/teaching/teachingWork/queryTeachingWorkCorrectByMainId?id=' + work, 'student_a')
                check('owner reads committed feedback', status == 200 and feedback['result'][0]['score'] == 5)

                saved = snapshot()
                for actor in ('student_a', 'teacher_b', None):
                    edit({'workStatus': '2', 'teachingWorkCommentList': [], 'teachingWorkCorrectList': []}, actor, False)
                    check('denied mutation preserves parent and children for ' + str(actor), snapshot() == saved)

                edit({'teachingWorkCommentList': [{'userId': 'fixture_teacher_a', 'comment': 'authorized replacement'}]}, 'admin')
                check('explicit comments replace only comments', query("SELECT comment FROM teaching_work_comment WHERE work_id='" + work + "'") == 'authorized replacement' and snapshot()['teaching_work_correct'] == saved['teaching_work_correct'])
                correct = snapshot()['teaching_work_correct']
                edit({'teachingWorkCommentList': []})
                check('explicit empty comments clears only comments', snapshot()['teaching_work_comment'] == '' and snapshot()['teaching_work_correct'] == correct)
                seed()
                comments = snapshot()['teaching_work_comment']
                edit({'teachingWorkCorrectList': []})
                check('explicit empty feedback clears only feedback', snapshot()['teaching_work_correct'] == '' and snapshot()['teaching_work_comment'] == comments)
                edit({'teachingWorkCorrectList': [{'score': 4, 'comment': 'both feedback'}], 'teachingWorkCommentList': [{'userId': 'fixture_teacher_a', 'comment': 'both discussion'}]})
                check('explicit two-collection update persists both', query("SELECT CONCAT(score,':',comment) FROM teaching_work_correct WHERE work_id='" + work + "'") == '4:both feedback' and query("SELECT comment FROM teaching_work_comment WHERE work_id='" + work + "'") == 'both discussion')

                for child in ('teachingWorkCorrectList', 'teachingWorkCommentList'):
                    saved = snapshot()
                    duplicate = {'id': prefix + 'duplicate', 'score': 1, 'comment': 'rollback probe', 'userId': 'fixture_teacher_a'}
                    body = {'id': work, 'workName': 'must roll back', child: [duplicate, duplicate]}
                    # First insert succeeds, second collides: exercise the existing
                    # actual database transaction after deleting that collection.
                    status, result, _ = api.request('PUT', '/teaching/teachingWork/edit', 'teacher_a', body)
                    check('second insert fails: ' + child, status >= 400 or not (result and result.get('success')))
                    check('failed replace restores all parent and child columns: ' + child, snapshot() == saved)
                query("INSERT INTO teaching_work (id,user_id,depart_id,course_id,work_name,work_type,work_file,work_status,del_flag,create_by,create_time) VALUES ('" + fault_work + "','fixture_student_a','fixture_class_a','fixture_unit_a','atomic statistics','2','fixture_file_a','1',0,'fixture_student_a','2026-10-01 08:00:00')")
                def grade(body):
                    return api.request('PUT', '/teaching/teachingWork/edit', 'teacher_a', {'id': fault_work, **body})[:2]
                def atomic_snapshot():
                    return {t: query('SELECT * FROM ' + t + (' ORDER BY work_id,event_type' if t == 'teaching_work_event' else ' ORDER BY id'))
                            for t in ('teaching_work', 'teaching_work_correct', 'teaching_work_comment', 'teaching_work_event', 'teaching_depart_day_log')}
                status, result = grade({'workName': 'rename only'})
                check('task-bound rename succeeds without correction event', status == 200 and result.get('success') and query("SELECT COUNT(*) FROM teaching_work_event WHERE work_id='" + fault_work + "'") == '0')
                saved = atomic_snapshot()
                query("DELIMITER //\nCREATE TRIGGER " + trigger + " BEFORE UPDATE ON teaching_depart_day_log FOR EACH ROW BEGIN IF OLD.depart_id='fixture_class_a' THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='synthetic grading statistics failure'; END IF; END//\nDELIMITER ;")
                trigger_created = True
                body = {'workName': 'graded', 'workStatus': '2', 'teachingWorkCorrectList': [{'score': 0, 'comment': 'zero is valid'}]}
                status, result = grade(body)
                check('real daily SQL failure rejects grading', result and result.get('success') is False)
                check('real daily failure rolls back parent feedback event and statistics', atomic_snapshot() == saved)
                query('DROP TRIGGER ' + trigger); trigger_created = False
                api.cache('SET', marker, 'synthetic-statistics-cache-unavailable'); marker_changed = True
                status, result = grade(body)
                check('grading succeeds with unusable obsolete Redis marker', status == 200 and result.get('success'))
                barrier = threading.Barrier(8)
                def concurrent_grade(_):
                    barrier.wait(timeout=10)
                    return grade(body)
                with ThreadPoolExecutor(max_workers=8) as pool:
                    responses = list(pool.map(concurrent_grade, range(8)))
                check('eight concurrent grading retries succeed', all(status == 200 and value and value.get('success') for status, value in responses))
                check('one persistent correction event after concurrent retries', query("SELECT COUNT(*) FROM teaching_work_event WHERE work_id='" + fault_work + "' AND event_type='CORRECT' AND event_state='COUNTED'") == '1')
                check('original and atomic works each count once', query("SELECT SUM(course_work_correct_count) FROM teaching_depart_day_log WHERE depart_id='fixture_class_a'") == '2')
                check('statistics never read or write obsolete Redis marker', api.cache('GET', marker) == 'synthetic-statistics-cache-unavailable')
                api.cache('DEL', marker); marker_changed = False
                grade(body)
                check('lost Redis marker cannot recount committed correction', query("SELECT SUM(course_work_correct_count) FROM teaching_depart_day_log WHERE depart_id='fixture_class_a'") == '2')
        finally:
            if trigger_created:
                query('DROP TRIGGER ' + trigger)
            if marker_changed:
                api.cache('DEL', marker)
            query("DELETE FROM teaching_work_correct WHERE work_id='" + fault_work + "'; DELETE FROM teaching_work_comment WHERE work_id='" + fault_work + "'; DELETE FROM teaching_work WHERE id='" + fault_work + "'; DELETE FROM teaching_work_event WHERE work_id IN ('" + work + "','" + fault_work + "'); DELETE FROM teaching_depart_day_log WHERE depart_id='fixture_class_a'")
            query("DELETE FROM teaching_work_correct WHERE work_id='" + work + "'; DELETE FROM teaching_work_comment WHERE work_id='" + work + "'; DELETE FROM teaching_work WHERE id='" + work + "'")
        after = database_inventory(api.runtime)
        check('all 68 non-audit database tables restored', all(before[t] == after[t] for t in before if t != 'sys_log'))
        check('all attachment bytes unchanged', files == file_inventory(api.runtime / 'uploads'))
        result = {'cases': cases, 'passed': sum(c['passed'] for c in cases), 'total': len(cases), 'expected_legacy': args.expect_legacy,
                  'jar_sha256': api.jar_sha256, 'changed_tables': [t for t in before if before[t] != after[t]],
                  'scope': 'Actual synthetic HTTP, MySQL transaction failures and readback. Eight concurrent grading retries and unusable/lost Redis marker covered; no authenticated browser or classroom load test.'}
    private_write(args.output, json.dumps(result, indent=2) + '\n')
    return result['passed'] == result['total']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('runtime', 'jar', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--expect-legacy', action='store_true')
    raise SystemExit(0 if verify(parser.parse_args()) else 1)
