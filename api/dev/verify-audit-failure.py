#!/usr/bin/env python3
"""Synthetic HTTP/MySQL audit-write failure and metadata-minimization regression."""
import argparse
import json
from pathlib import Path

from local_http import FixtureApi
from local_recovery import database_inventory, file_inventory, private_write, sql


def verify(args):
    prefix = 'fixture_autolog_failure_'
    work = prefix + 'work'
    marker = prefix + 'private_feedback'
    name = prefix + 'committed'
    trigger = prefix + 'insert'
    method = 'org.jeecg.modules.teaching.controller.TeachingWorkController.edit()'
    cases = []
    trigger_created = False
    def check(label, value):
        cases.append({'case': label, 'passed': bool(value)})
        print(('PASS ' if value else 'FAIL ') + label, flush=True)
        if not value:
            raise AssertionError(label)

    with FixtureApi(args.runtime, args.jar) as api:
        def query(statement):
            return sql(api.runtime, 'USE teachingopen_dev;\n' + statement)
        before = database_inventory(api.runtime)
        attachments = file_inventory(api.runtime / 'uploads')
        if query("SELECT COUNT(*) FROM teaching_work WHERE id LIKE '" + prefix + "%' OR work_name='" + name + "'") != '0':
            raise RuntimeError('Preserve existing probe data')
        if query('SELECT COUNT(*) FROM teaching_depart_day_log') != '0':
            raise RuntimeError('This isolated probe requires the unused synthetic daily-log fixture')
        if query("SELECT COUNT(*) FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA=DATABASE() AND TRIGGER_NAME='" + trigger + "'") != '0':
            raise RuntimeError('Preserve an existing trigger')
        def audit_ids():
            return set(query("SELECT id FROM sys_log WHERE userid='fixture_teacher_a' AND method='" + method + "' ORDER BY id").splitlines())
        process = json.loads((api.runtime / 'backend-process.json').read_text())
        log_path = Path(process['log_path'])
        if log_path.resolve().parent != (api.runtime / 'logs').resolve():
            raise RuntimeError('Backend log is outside the owned synthetic runtime')
        response = None
        warning_lines = []
        try:
            api.login('teacher_a')
            query("INSERT INTO teaching_work (id,user_id,depart_id,course_id,work_name,work_file,work_type,work_status,work_scene,del_flag,create_by,create_time) VALUES ('" + work + "','fixture_student_a','fixture_class_a','fixture_unit_a','audit probe','fixture_file_a','0','1','course',0,'fixture_student_a','2026-10-01 08:00:00')")
            # Only this synthetic teacher's edit, while this exact task-owned work
            # has the marker written by the tested request. Other logs are unaffected.
            query("DELIMITER //\nCREATE TRIGGER " + trigger + " BEFORE INSERT ON sys_log FOR EACH ROW BEGIN IF NEW.userid='fixture_teacher_a' AND NEW.method='" + method + "' AND EXISTS(SELECT 1 FROM teaching_work WHERE id='" + work + "' AND work_name='" + name + "') THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='synthetic_noncritical_audit_failure'; END IF; END//\nDELIMITER ;")
            trigger_created = True
            prior_audit = audit_ids()
            log_offset = log_path.stat().st_size
            payload = {'id': work, 'workName': name, 'workStatus': '2',
                       'teachingWorkCorrectList': [{'score': 0, 'comment': marker}]}
            status, result, _ = api.request('PUT', '/teaching/teachingWork/edit', 'teacher_a', payload)
            response = {'status': status, 'success': bool(result and result.get('success')), 'code': result.get('code') if result else None}
            if args.expect_legacy:
                check('legacy audit SQL failure changes the completed business response to failure', not response['success'])
            else:
                check('audit SQL failure preserves HTTP 200 business success', status == 200 and response['success'])
            check('parent business mutation committed exactly once', query("SELECT COUNT(*) FROM teaching_work WHERE id='" + work + "' AND work_name='" + name + "' AND work_status='2'") == '1')
            check('one zero-score feedback row committed despite audit failure', query("SELECT COUNT(*) FROM teaching_work_correct WHERE work_id='" + work + "' AND score=0 AND comment='" + marker + "'") == '1')
            check('one persistent correction event committed', query("SELECT COUNT(*) FROM teaching_work_event WHERE work_id='" + work + "' AND event_type='CORRECT' AND event_state='COUNTED'") == '1')
            check('daily correction count committed once', query("SELECT COALESCE(SUM(course_work_correct_count),0) FROM teaching_depart_day_log WHERE depart_id='fixture_class_a'") == '1')
            check('failing audit insert produced no row', audit_ids() == prior_audit)
            with log_path.open('rb') as log:
                log.seek(log_offset)
                warning_lines = [line for line in log.read().decode('utf8', errors='replace').splitlines() if 'audit_write_failed' in line]
            if not args.expect_legacy:
                check('audit failure remains observable by stable warning code', len(warning_lines) == 1 and method in warning_lines[0])
                check('audit warning excludes body and SQL exception text', marker not in warning_lines[0] and name not in warning_lines[0] and 'synthetic_noncritical_audit_failure' not in warning_lines[0])
            query('DROP TRIGGER ' + trigger)
            trigger_created = False
            status, result, _ = api.request('PUT', '/teaching/teachingWork/edit', 'teacher_a', payload)
            check('normal retry succeeds', status == 200 and result and result.get('success'))
            check('normal retry cannot recount the durable event', query("SELECT COALESCE(SUM(course_work_correct_count),0) FROM teaching_depart_day_log WHERE depart_id='fixture_class_a'") == '1')
            new_ids = audit_ids() - prior_audit
            check('successful audit writes one metadata row', len(new_ids) == 1)
            audit_id = next(iter(new_ids))
            params = query("SELECT COALESCE(request_param,'<NULL>') FROM sys_log WHERE id='" + audit_id + "'")
            if args.expect_legacy:
                check('legacy audit duplicates private feedback and work-name fields', marker in params and name in params)
            else:
                check('audit does not duplicate any request arguments', params == '<NULL>')
                check('audit retains operation method and actor metadata', query("SELECT COUNT(*) FROM sys_log WHERE id='" + audit_id + "' AND method='" + method + "' AND userid='fixture_teacher_a' AND log_content='作业列表-编辑' AND log_type=2 AND operate_type=3 AND cost_time IS NOT NULL AND create_time IS NOT NULL") == '1')
        finally:
            if trigger_created:
                query('DROP TRIGGER ' + trigger)
            query("DELETE FROM teaching_work_correct WHERE work_id='" + work + "'; DELETE FROM teaching_work_comment WHERE work_id='" + work + "'; DELETE FROM teaching_work_event WHERE work_id='" + work + "'; DELETE FROM teaching_work WHERE id='" + work + "'; DELETE FROM teaching_depart_day_log WHERE depart_id='fixture_class_a'")
        after = database_inventory(api.runtime)
        check('probe trigger removed', query("SELECT COUNT(*) FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA=DATABASE() AND TRIGGER_NAME='" + trigger + "'") == '0')
        check('all non-audit database tables restored', all(before[table] == after[table] for table in before if table != 'sys_log'))
        check('attachment bytes unchanged', attachments == file_inventory(api.runtime / 'uploads'))
        evidence = {'cases': cases, 'passed': sum(case['passed'] for case in cases), 'total': len(cases),
                    'expected_legacy': args.expect_legacy, 'jar_sha256': api.jar_sha256,
                    'injected_failure_response': response, 'audit_warning_lines': warning_lines,
                    'changed_tables': [table for table in before if before[table] != after[table]],
                    'scope': 'Actual synthetic HTTP/MySQL INSERT trigger failure after committed grading, durable event and daily counter. No production changes and no claim of durable/strongly consistent audit delivery.'}
    private_write(args.output, json.dumps(evidence, indent=2) + '\n')
    return evidence['passed'] == evidence['total']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('runtime', 'jar', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--expect-legacy', action='store_true')
    raise SystemExit(0 if verify(parser.parse_args()) else 1)
