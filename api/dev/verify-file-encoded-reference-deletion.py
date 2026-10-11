#!/usr/bin/env python3
"""Real HTTP checks for encoded local attachment references in an owned fixture.

The teacher edits a synthetic assigned task. The exact same URL/HTML/JSON values
must keep its local bytes readable to the assigned student and undeletable while
referenced. Only probe rows and bytes are changed; no remote storage is accessed.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

from local_http import FixtureApi
from local_runtime import mysql_command


TABLES = ('sys_file', 'teaching_additional_work', 'teaching_depart_day_log', 'teaching_work',
          'teaching_work_correct', 'teaching_work_comment', 'sys_data_log')


def verify(args):
    if args.output.exists():
        raise RuntimeError('Refusing to overwrite an existing evidence report')
    cases, error = [], None
    with FixtureApi(args.runtime.resolve(), args.jar) as api:
        def sql(statement):
            result = subprocess.run(mysql_command(api.runtime) + ['teachingopen_dev', '-e', statement],
                                    capture_output=True, text=True, timeout=20)
            if result.returncode:
                raise RuntimeError('Owned encoded-reference fixture SQL failed: ' + result.stderr[:500])
            return result.stdout.strip()

        def literal(value):
            return 'NULL' if value is None else 'CONVERT(0x' + str(value).encode().hex() + ' USING utf8mb4)' if str(value) else "''"

        def insert(table, values):
            sql('INSERT INTO ' + table + '(' + ','.join(values) + ') VALUES('
                + ','.join(literal(value) for value in values.values()) + ')')

        def check(name, passed, fatal=True):
            cases.append({'case': name, 'passed': bool(passed)})
            print(('PASS ' if passed else 'FAIL ') + name, flush=True)
            if not passed and fatal:
                raise AssertionError(name)

        def rows():
            result = {table: hashlib.sha256(sql('SELECT * FROM ' + table + ' ORDER BY id').encode()).hexdigest()
                      for table in TABLES}
            for department in ('fixture_class_a', 'fixture_class_b'):
                key = 'departLog:addiWorkAssign:' + department
                result[key] = hashlib.sha256('\n'.join(sorted(api.cache('SMEMBERS', key).splitlines())).encode()).hexdigest()
            return result

        def disk():
            return {str(path.relative_to(api.runtime / 'uploads')): hashlib.sha256(path.read_bytes()).hexdigest()
                    for path in (api.runtime / 'uploads').rglob('*') if path.is_file()}

        def success(response):
            status, body, _ = response
            return status == 200 and body and body.get('success') is True

        def bytes_read(actor):
            headers = {'X-Access-Token': api.tokens[actor]} if actor else {}
            request = Request('http://127.0.0.1:' + str(api.ports['backend']) + '/api/sys/common/static/' + key,
                              headers=headers)
            try:
                response = urlopen(request, timeout=10)
            except HTTPError as failure:
                response = failure
            with response:
                return response.status, response.read()

        prefix = 'file_encoded_' + uuid4().hex[:10]
        file_id, task_id = prefix + '_file', prefix + '_task'
        key = prefix + '/private.txt'
        folder = api.runtime / 'uploads' / prefix
        path = api.runtime / 'uploads' / key
        content = b'synthetic encoded reference attachment\n'
        static = '/api/sys/common/static/'
        percent = static + '%66' + key[1:]
        entity = "<img src='" + static + '&#102;' + key[1:] + "'>"
        # Keep literal JSON Unicode and slash escapes in the stored rich field.
        escaped_json = '{"media":[{"src":"' + static.replace('/', '\\/') + '\\u0066' + key[1:] + '"}]}'
        variations = (
            ('percent URL', {'workUrl': percent}),
            ('HTML entity', {'workDesc': entity}),
            ('HTML entity and URL encoding', {'workDesc': "<img src='" + static + '&#x25;66' + key[1:] + "'>"}),
            ('nested JSON escapes', {'workDesc': escaped_json}),
            ('independent JSON fields', {'workUrl': '["https://example.invalid/external"]', 'workDesc': escaped_json}),
        )
        original_rows, original_disk = rows(), disk()
        if folder.exists():
            raise RuntimeError('Refusing to overwrite existing encoded-reference probe folder')

        def reset():
            sql('DELETE FROM teaching_additional_work WHERE id=' + literal(task_id))
            sql('DELETE FROM sys_file WHERE id=' + literal(file_id))
            path.write_bytes(content)
            insert('sys_file', {'id': file_id, 'file_name': 'private.txt', 'file_path': key, 'file_location': 1,
                                'create_by': 'fixture_teacher_a', 'create_time': '2026-10-11 00:00:00', 'del_flag': 0})
            insert('teaching_additional_work', {'id': task_id, 'work_name': prefix, 'work_dept': 'fixture_class_a',
                                               'status': 1, 'code_type': 0, 'create_by': 'fixture_teacher_a',
                                               'create_time': '2026-10-11 00:00:00'})

        try:
            for actor in ('teacher_a', 'student_a', 'student_b'):
                api.login(actor)
            folder.mkdir()
            for label, reference_fields in variations:
                reset()
                check(label + ' fixture contains no raw file key or ID', all(key not in value and file_id not in value
                                                                          for value in reference_fields.values()))
                payload = dict(id=task_id, workName=prefix, workDept='fixture_class_a', status=1, codeType=0,
                               workCover='', workDocumentUrl='', workUrl='', workDesc='')
                payload.update(reference_fields)
                check(label + ' teacher saves owned reference through HTTP',
                      success(api.request('PUT', '/teaching/teachingAdditionalWork/edit', 'teacher_a', payload)))
                task_before = sql('SELECT * FROM teaching_additional_work WHERE id=' + literal(task_id))
                check(label + ' unauthorized student cannot read bytes', bytes_read('student_b')[0] == 403)
                check(label + ' anonymous reader cannot read bytes', bytes_read(None)[0] == 401)
                if not args.expect_legacy or '%' in ''.join(reference_fields.values()):
                    check(label + ' assigned student reads exact bytes', bytes_read('student_a') == (200, content))
                else:
                    check(label + ' baseline candidate prefilter denies assigned student', bytes_read('student_a')[0] == 403)
                response = api.request('DELETE', '/system/sysFile/delete?id=' + file_id, 'teacher_a')
                if args.expect_legacy:
                    check(label + ' baseline wrongly accepts in-use file deletion', success(response))
                    check(label + ' baseline erases referenced bytes and metadata', not path.exists()
                          and sql('SELECT COUNT(*) FROM sys_file WHERE id=' + literal(file_id)) == '0')
                else:
                    status, body, _ = response
                    check(label + ' deletion refuses a decoded live reference', status == 200 and body
                          and body.get('success') is False and body.get('code') == 500
                          and body.get('message') == '文件仍被使用，请先移除引用')
                    check(label + ' refusal preserves exact bytes and live metadata', path.read_bytes() == content
                          and sql('SELECT del_flag FROM sys_file WHERE id=' + literal(file_id)) == '0')
                    check(label + ' assigned student still reads exact bytes after refusal', bytes_read('student_a') == (200, content))
                    check(label + ' other student remains denied after refusal', bytes_read('student_b')[0] == 403)
                check(label + ' deletion does not alter task reference', task_before == sql(
                    'SELECT * FROM teaching_additional_work WHERE id=' + literal(task_id)))

            if not args.expect_legacy:
                reset()
                # An encoded external URL must not be mistaken for this local key.
                payload = dict(id=task_id, workName=prefix, workDept='fixture_class_a', status=1, codeType=0,
                               workDesc="<img src='https://example.invalid/static/%66" + key[1:] + "'>")
                check('external encoded image remains a permitted external reference', success(api.request(
                    'PUT', '/teaching/teachingAdditionalWork/edit', 'teacher_a', payload)))
                check('external encoded image does not publish the local key', bytes_read('student_a')[0] == 403)
                check('unreferenced local file still deletes successfully', success(api.request(
                    'DELETE', '/system/sysFile/delete?id=' + file_id, 'teacher_a')))
                check('ordinary cleanup removes its bytes and metadata', not path.exists()
                      and sql('SELECT COUNT(*) FROM sys_file WHERE id=' + literal(file_id)) == '0')
        except Exception as failure:
            error = type(failure).__name__ + ': ' + str(failure)
        finally:
            sql('DELETE FROM teaching_additional_work WHERE id=' + literal(task_id))
            sql('DELETE FROM sys_file WHERE id=' + literal(file_id))
            if folder.exists():
                shutil.rmtree(folder)
        check('all original business rows and assignment counters restored', original_rows == rows(), fatal=False)
        check('all original upload bytes restored', original_disk == disk(), fatal=False)
        result = {'cases': cases, 'passed': sum(case['passed'] for case in cases), 'failed': sum(not case['passed'] for case in cases),
                  'total': len(cases), 'jar_sha256': api.jar_sha256, 'expected_legacy': args.expect_legacy, 'exception': error,
                  'created_at': datetime.now(timezone.utc).isoformat(),
                  'scope': 'Owned synthetic teacher HTTP edit, assigned/cross-class/anonymous byte reads, encoded-reference deletion; no remote storage.'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    return error is None and result['failed'] == 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('runtime', 'jar', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--expect-legacy', action='store_true')
    raise SystemExit(0 if verify(parser.parse_args()) else 1)
