#!/usr/bin/env python3
"""Verify management workbench request contracts on an owned synthetic Java runtime."""
import argparse
import json
from pathlib import Path
import sys
from urllib.parse import urlencode
from urllib.request import Request, urlopen

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--support-repo', type=Path, required=True)
p.add_argument('--runtime', type=Path, required=True)
p.add_argument('--jar', type=Path, required=True)
p.add_argument('--output', type=Path, required=True)
a = p.parse_args()
if a.output.exists():
    raise RuntimeError('Choose a fresh evidence file')
sys.path.insert(0, str(a.support_repo / 'api/dev'))
from local_http import FixtureApi
from local_recovery import database_inventory, file_inventory, sql, private_write

prefix = 'fixture_admin_ui_'
cases = []
def check(name, ok):
    cases.append({'case': name, 'passed': bool(ok)})
    print(('PASS ' if ok else 'FAIL ') + name, flush=True)
    if not ok:
        raise AssertionError(name)

with FixtureApi(a.runtime, a.jar) as api:
    before = database_inventory(api.runtime)
    uploads = file_inventory(api.runtime / 'uploads')
    def query(s):
        return sql(api.runtime, 'USE teachingopen_dev; ' + s)
    for table in ('teaching_course', 'teaching_course_unit'):
        if query("SELECT COUNT(*) FROM " + table + " WHERE id LIKE '" + prefix + "%'") != '0':
            raise RuntimeError('Existing fixtures must be preserved')
    error = None
    try:
        for actor in ('admin', 'teacher_a', 'student_a'):
            api.login(actor)
        course = prefix + 'course'
        status, res, _ = api.request('POST', '/teaching/teachingCourse/add', 'admin', {
            'id': course, 'courseName': '工作台契约课程', 'courseType': 771,
            'courseCategory': 772, 'isShared': False, 'showHome': False,
            'orderNum': 0, 'courseDesc': '<p>表单完整内容</p>', 'departIds': ''})
        check('admin course fixture created', status == 200 and res.get('success') is True)
        for i in range(12):
            status, res, _ = api.request('POST', '/teaching/teachingCourseUnit/add', 'admin', {
                'id': prefix + 'unit_' + str(i), 'courseId': course, 'unitName': '契约单元' + str(i),
                'unitIntro': '完整单元介绍', 'orderNum': i, 'showCourseVideo': False,
                'showCourseCase': True, 'courseVideoSource': 2,
                'courseVideo': 'https://example.invalid/unit.mp4', 'courseWorkType': 2,
                'mapX': 0, 'mapY': i, 'mediaContent': '<p>完整单元内容</p>'})
            check('admin unit fixture created ' + str(i), status == 200 and res.get('success') is True)
        def listing(controller, params, actor='admin'):
            return api.request('GET', '/teaching/' + controller + '/list?' + urlencode(params), actor)
        status, res, _ = listing('teachingCourse', {'courseType': 771, 'column': 'orderNum', 'order': 'asc', 'pageNo': 1, 'pageSize': 10})
        check('course filter and zero order listing', status == 200 and res.get('success') is True and res['result']['total'] == 1)
        row = res['result']['records'][0]
        check('course row preserves full edit content and boolean flags', row['id'] == course and row['courseDesc'] == '<p>表单完整内容</p>' and row['isShared'] is False and row['showHome'] is False and row['orderNum'] == 0)
        for column, order in [('createTime', 'asc'), ('createTime', 'desc'), ('orderNum', 'asc'), ('orderNum', 'desc')]:
            status, res, _ = listing('teachingCourseUnit', {'courseId': course, 'column': column, 'order': order, 'pageNo': 1, 'pageSize': 10})
            check('unit list accepts sort ' + column + ':' + order, status == 200 and res.get('success') is True and res['result']['total'] == 12 and len(res['result']['records']) == 10)
            if column == 'orderNum':
                expected = list(range(10)) if order == 'asc' else list(range(11, 1, -1))
                check('unit order values match ' + order, [r['orderNum'] for r in res['result']['records']] == expected)
        params = {'courseId': course, 'column': 'orderNum', 'order': 'asc', 'pageNo': 2, 'pageSize': 10}
        status, res, _ = listing('teachingCourseUnit', params)
        check('unit pagination retains course filter', res.get('success') is True and [r['id'] for r in res['result']['records']] == [prefix + 'unit_10', prefix + 'unit_11'])
        row = res['result']['records'][0]
        check('actual management response includes parent course name', row.get('courseName') == '工作台契约课程' and row['courseId'] == course)
        check('unit row preserves fields for existing edit modal', row.get('unitIntro') == '完整单元介绍' and row.get('showCourseVideo') is False and row.get('showCourseCase') is True and row.get('courseWorkType') == 2 and row.get('mediaContent') == '<p>完整单元内容</p>' and row.get('mapX') == 0)
        status, res, _ = listing('teachingCourseUnit', {'courseId': course, 'unitName': '契约单元3'})
        check('unit exact name filter remains compatible', res.get('success') is True and [r['id'] for r in res['result']['records']] == [prefix + 'unit_3'])
        for controller in ('teachingCourse', 'teachingCourseUnit'):
            for actor in ('teacher_a', 'student_a', None):
                status, res, _ = listing(controller, {}, actor)
                check(controller + ' management still denied to ' + str(actor), res.get('success') is False and res.get('code') == (510 if actor else 401))
            selection = course if controller == 'teachingCourse' else prefix + 'unit_3'
            params = {'selections': selection}
            params.update({'courseType': 771} if controller == 'teachingCourse' else {'courseId': course})
            req = Request('http://127.0.0.1:' + str(api.ports['backend']) + '/api/teaching/' + controller + '/exportXls?' + urlencode(params), headers={'X-Access-Token': api.tokens['admin']})
            with urlopen(req, timeout=15) as response:
                body = response.read()
                check(controller + ' actual selected export has OLE2 workbook bytes', response.status == 200 and body.startswith(bytes([208, 207, 17, 224, 161, 177, 26, 225])))
        ids = [prefix + 'unit_10', prefix + 'unit_11']
        status, res, _ = api.request('DELETE', '/teaching/teachingCourseUnit/deleteBatch?' + urlencode({'ids': ','.join(ids)}), 'admin')
        check('unit batch deletion succeeds', res.get('success') is True)
        status, res, _ = listing('teachingCourseUnit', {'courseId': course, 'pageNo': 1, 'pageSize': 10})
        check('deleting final page leaves ten records for page recovery', res.get('success') is True and res['result']['total'] == 10 and len(res['result']['records']) == 10)
    except Exception as exc:
        error = type(exc).__name__
        raise
    finally:
        for table in ('teaching_course_unit', 'teaching_course'):
            query("DELETE FROM " + table + " WHERE id LIKE '" + prefix + "%'")
        after = database_inventory(api.runtime)
        cases.append({'case': 'all 68 non-audit tables restored', 'passed': all(before[t] == after[t] for t in before if t != 'sys_log')})
        cases.append({'case': 'attachment bytes unchanged', 'passed': uploads == file_inventory(api.runtime / 'uploads')})
        result = {'passed': sum(c['passed'] for c in cases), 'total': len(cases), 'cases': cases, 'exception': error, 'jar_sha256': api.jar_sha256, 'scope': 'Actual Java/MySQL with isolated synthetic API authentication, separate from component browser checks; not authenticated full application, workbook content, or actual spreadsheet import acceptance.'}
        private_write(a.output, json.dumps(result, ensure_ascii=False, indent=2) + '\n')
        if not all(c['passed'] for c in cases):
            raise AssertionError('Management contract check failed; evidence retained')
print(str(result['passed']) + '/' + str(result['total']) + ' checks passed')
