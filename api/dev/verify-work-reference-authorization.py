#!/usr/bin/env python3
"""H-04: references must not manufacture private-file access in an owned fixture."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

from local_http import FixtureApi
from local_runtime import mysql_command
from media_index_fixture import media_index_snapshot, rebuild_media_index_after_sql

PREFIX = 'fixture_rprobe_'
NAME = 'reference-probe-'
DIRECTORY = 'reference-probe-files'
WORK = '/teaching/teachingWork/'
ADDITIONAL = '/teaching/teachingAdditionalWork/'
TABLES = ('teaching_work', 'teaching_work_correct', 'teaching_work_comment', 'sys_data_log',
          'sys_file', 'teaching_additional_work', 'teaching_depart_day_log', 'sys_depart')


def verify(args):
    cases = []
    error = None
    with FixtureApi(args.runtime.resolve(), args.jar) as api:
        has_media_index = not getattr(args, 'expect_legacy', False)
        def sql(query):
            result = subprocess.check_output(mysql_command(api.runtime) + ['teachingopen_dev', '-e', query], text=True).strip()
            if has_media_index:
                rebuild_media_index_after_sql(api, query)
            return result

        def literal(value):
            return 'NULL' if value is None else "CONVERT(0x" + str(value).encode().hex() + " USING utf8mb4)" if str(value) else "''"

        def insert(table, **values):
            sql('INSERT INTO ' + table + ' (' + ','.join(values) + ') VALUES (' + ','.join(literal(v) for v in values.values()) + ')')

        def check(name, passed, fatal=True):
            cases.append({'case': name, 'passed': bool(passed)})
            print(('PASS ' if passed else 'FAIL ') + name, flush=True)
            if not passed and fatal:
                raise AssertionError(name)

        def rows():
            return {table: hashlib.sha256(sql('SELECT * FROM ' + table + ' ORDER BY id').encode()).hexdigest() for table in TABLES}

        def files():
            return {str(p.relative_to(api.runtime / 'uploads')): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in (api.runtime / 'uploads').rglob('*') if p.is_file()}

        def snapshot():
            return {'rows': rows(), 'files': files(), 'assignment_cache': api.cache('SMEMBERS', cache_key),
                    'media_references': media_index_snapshot(sql) if has_media_index else None}

        def allowed(name, method, path, body=None, actor='teacher_a'):
            status, response, _ = api.request(method, path, actor, body)
            check(name, status == 200 and response and response.get('success') is True)
            return response.get('result')

        def denied(name, method, path, body=None, actor='teacher_a', code=510):
            before = snapshot()
            status, response, _ = api.request(method, path, actor, body)
            check(name, status == (200 if actor else 401) and response and response.get('success') is False
                  and response.get('code') == (code if actor else 401) and not response.get('result'))
            check(name + ' preserves work feedback files statistics and media references', before == snapshot())

        def bytes_read(key, actor='teacher_a'):
            headers = {'X-Access-Token': api.tokens[actor]} if actor else {}
            request = Request(origin + '/api/sys/common/static/' + quote(key, safe='/'), headers=headers)
            try:
                response = urlopen(request, timeout=15)
            except HTTPError as failure:
                response = failure
            with response:
                return response.status, response.read()

        def remains_private(label, ident, key, actor='teacher_a'):
            status, response, _ = api.request('GET', '/system/sysFile/queryById?id=' + ident, actor)
            check(label + ' metadata remains forbidden', status == 200 and response and response.get('success') is False
                  and response.get('code') == 510 and not response.get('result'))
            status, content = bytes_read(key, actor)
            check(label + ' actual private bytes remain forbidden', status == 403 and content != (api.runtime / 'uploads' / key).read_bytes())

        def raw_upload():
            boundary = 'reference-ownership-upload'
            content = b'uploaded by fixture teacher a\n'
            body = ('--' + boundary + '\r\nContent-Disposition: form-data; name="biz"\r\n\r\n' + DIRECTORY
                    + '\r\n--' + boundary + '\r\nContent-Disposition: form-data; name="file"; filename="owned.py"\r\n'
                    + 'Content-Type: text/plain\r\n\r\n').encode() + content + ('\r\n--' + boundary + '--\r\n').encode()
            request = Request(origin + '/api/sys/common/upload', body,
                              {'Content-Type': 'multipart/form-data; boundary=' + boundary, 'X-Access-Token': api.tokens['teacher_a']}, method='POST')
            with urlopen(request, timeout=15) as response:
                result = json.loads(response.read())
                check('actual teacher upload registers a file', response.status == 200 and result.get('success') is True)
            key = result['message']
            check('teacher upload belongs to probe directory', key.startswith(DIRECTORY + '/') and '..' not in key.split('/'))
            ident = sql('SELECT id FROM sys_file WHERE file_path=' + literal(key) + " AND create_by='fixture_teacher_a' AND del_flag=0")
            check('teacher upload has one canonical owned file ID and exact bytes', bool(ident) and '\n' not in ident
                  and (api.runtime / 'uploads' / key).read_bytes() == content)
            return ident, key

        origin = 'http://127.0.0.1:' + str(api.ports['backend'])
        static = '/api/sys/common/static/'
        folder = api.runtime / 'uploads' / DIRECTORY
        cache_key = 'departLog:addiWorkAssign:' + PREFIX + 'class'
        if folder.exists() or any(sql("SELECT COUNT(*) FROM " + table + " WHERE id LIKE '" + PREFIX + "%'") != '0' for table in TABLES):
            raise RuntimeError('Existing reference-authorization probe data; refusing overwrite')
        if sql("SELECT COUNT(*) FROM teaching_work WHERE work_name LIKE '" + NAME + "%'") != '0':
            raise RuntimeError('Existing reference-authorization probe names')
        if api.cache('EXISTS', cache_key) != '0':
            raise RuntimeError('Existing reference-authorization probe cache')
        original_rows, original_files = rows(), files()
        original_media_index = media_index_snapshot(sql) if has_media_index else None
        try:
            for actor in ('teacher_a', 'teacher_b', 'student_a', 'student_b', 'admin'):
                api.login(actor)
            folder.mkdir()
            for suffix, uploader in (('original', 'student_a'), ('private', 'student_b'), ('source', 'teacher_b')):
                key = DIRECTORY + '/' + suffix + '.txt'
                (api.runtime / 'uploads' / key).write_bytes(('synthetic private bytes ' + suffix).encode())
                insert('sys_file', id=PREFIX + suffix, file_name=suffix + '.txt', file_path=key, file_location=1, create_by='fixture_' + uploader)
            # Source belongs to a managed student but its retained file was uploaded
            # by another teacher: a valid sent-copy reference, not a new binding.
            for suffix, attachment in (('work', 'original'), ('source_work', 'source')):
                insert('teaching_work', id=PREFIX + suffix, user_id='fixture_student_a', depart_id='fixture_class_a',
                       work_name=NAME + suffix, work_file=PREFIX + attachment, work_cover=PREFIX + attachment,
                       work_type='2', work_status=1, work_scene='create', del_flag=0, create_by='fixture_student_a',
                       create_time='2026-10-11 00:00:00')
            insert('teaching_work_correct', id=PREFIX + 'feedback', work_id=PREFIX + 'work', score=3, comment='original feedback')
            insert('teaching_work_comment', id=PREFIX + 'comment', work_id=PREFIX + 'work', user_id='fixture_student_a', comment='original discussion')
            insert('sys_depart', id=PREFIX + 'class', parent_id='fixture_class_a', depart_name='reference probe class',
                   org_code='A99A01A98', org_type='3', org_category='3', del_flag='0', status='1')
            insert('teaching_additional_work', id=PREFIX + 'assignment', work_name=NAME + 'assignment', work_dept=PREFIX + 'class',
                   status=0, code_type=0, create_by='fixture_teacher_a', work_desc='Original assignment description')
            private_id, private_key = PREFIX + 'private', DIRECTORY + '/private.txt'
            remains_private('initial teacher access', private_id, private_key)
            forged = {'id': PREFIX + 'work', 'workFile': private_id, 'workStatus': '3', 'workName': NAME + 'hijacked',
                      'teachingWorkCorrectList': [], 'teachingWorkCommentList': []}
            task = {'id': PREFIX + 'assignment', 'workName': NAME + 'assignment', 'workDept': PREFIX + 'class', 'status': 0, 'codeType': 0}

            if args.expect_legacy:
                allowed('baseline teacher can attach a previously private file', 'PUT', WORK + 'edit', forged)
                allowed('baseline forged reference permits file metadata', 'GET', '/system/sysFile/queryById?id=' + private_id)
                status, content = bytes_read(private_key)
                check('baseline forged reference permits exact private bytes', status == 200 and content == (folder / 'private.txt').read_bytes())
                sql("UPDATE teaching_work SET work_file='" + PREFIX + "original',work_status=1 WHERE id='" + PREFIX + "work'")
                remains_private('after baseline reference removed', private_id, private_key)
                allowed('baseline assignment URL can manufacture read access', 'PUT', ADDITIONAL + 'edit', dict(task, workCover=static + private_key))
                status, content = bytes_read(private_key)
                check('baseline assignment reference permits exact private bytes', status == 200 and content == (folder / 'private.txt').read_bytes())
            else:
                for field in ('workFile', 'workCover'):
                    body = dict(forged)
                    body.pop('workFile')
                    body[field] = private_id
                    denied('teacher cannot replace ' + field + ' with private file', 'PUT', WORK + 'edit', body)
                    remains_private('after denied ' + field, private_id, private_key)
                for value in (private_id, private_id.upper(), PREFIX + 'missing'):
                    denied('teacher add rejects unauthorized or noncanonical file ' + value, 'POST', WORK + 'add',
                           {'id': PREFIX + 'new_denied', 'userId': 'fixture_student_a', 'departId': 'fixture_class_a',
                            'workName': NAME + 'new_denied', 'workType': '2', 'workFile': value, 'workStatus': '3'})
                denied('teacher import role cannot bypass reference checks', 'POST', WORK + 'importExcel', {})
                denied('student cannot use teacher management edit', 'PUT', WORK + 'edit', forged, actor='student_a')
                denied('cross-class teacher cannot use management edit', 'PUT', WORK + 'edit', forged, actor='teacher_b')

                # The byte resolver recognizes raw keys, exact local URLs, once
                # encoded URLs, HTML entities and nested JSON. All share the guard.
                encoded = static + DIRECTORY + '/%70rivate%2Etxt'
                references = [('workCover', private_key), ('workDocumentUrl', static + private_key),
                              ('workUrl', encoded), ('workDesc', '<img src="' + static + DIRECTORY + '/&#x70;rivate.txt">'),
                              ('workDesc', json.dumps({'nested': [{'src': encoded}]}))]
                for index, (field, value) in enumerate(references):
                    denied('assignment edit rejects local reference form ' + str(index), 'PUT', ADDITIONAL + 'edit', dict(task, **{field: value}))
                    denied('assignment add rejects local reference form ' + str(index), 'POST', ADDITIONAL + 'add', dict(task, **{field: value}))
                    remains_private('after denied assignment reference ' + str(index), private_id, private_key)

                upload_id, upload_key = raw_upload()
                allowed('teacher can replace file and cover with own upload', 'PUT', WORK + 'edit',
                        {'id': PREFIX + 'work', 'workFile': upload_id, 'workCover': upload_id, 'workStatus': '1'})
                check('owned upload reference persists', sql("SELECT CONCAT(work_file,':',work_cover) FROM teaching_work WHERE id='" + PREFIX + "work'") == upload_id + ':' + upload_id)
                allowed('normal teacher grading preserves owned attachment', 'PUT', WORK + 'edit',
                        {'id': PREFIX + 'work', 'workStatus': '2', 'teachingWorkCorrectList': [{'score': 5, 'comment': 'legitimate grading'}]})
                check('normal grade keeps new file and discussion', sql("SELECT score FROM teaching_work_correct WHERE work_id='" + PREFIX + "work'") == '5'
                      and sql("SELECT comment FROM teaching_work_comment WHERE work_id='" + PREFIX + "work'") == 'original discussion')
                allowed('student reads teacher uploaded replacement metadata', 'GET', '/system/sysFile/queryById?id=' + upload_id, actor='student_a')
                status, content = bytes_read(upload_key, 'student_a')
                check('student reads exact replacement bytes', status == 200 and content == (api.runtime / 'uploads' / upload_key).read_bytes())
                allowed('teacher add accepts own registered upload', 'POST', WORK + 'add',
                        {'id': PREFIX + 'new', 'userId': 'fixture_student_a', 'departId': 'fixture_class_a', 'workName': NAME + 'new',
                         'workFile': upload_id, 'workType': '2', 'workStatus': '0'})

                allowed('legitimate send clones an accessible source with foreign uploaded attachments', 'POST', WORK + 'sendWork',
                        {'sendWorkId': PREFIX + 'source_work', 'userIdList': ['fixture_student_a']})
                clone_id = sql("SELECT id FROM teaching_work WHERE work_name='" + NAME + "source_work' AND id<>'" + PREFIX + "source_work'")
                check('send produced a distinct draft and preserved both source references', bool(clone_id) and '\n' not in clone_id
                      and sql('SELECT CONCAT(work_file,\':\',work_cover,\':\',work_status) FROM teaching_work WHERE id=' + literal(clone_id))
                      == PREFIX + 'source:' + PREFIX + 'source:0')
                # A received draft may retain its shared attachment while editable.
                # Once graded, the same student save must preserve that reviewed copy.
                retained_draft = {'id': clone_id, 'workName': NAME + 'clone_retained', 'workFile': PREFIX + 'source',
                                  'workCover': PREFIX + 'source', 'workType': '2', 'workStatus': '0'}
                allowed('student may save a sent draft with retained foreign attachment', 'POST', WORK + 'submit',
                        retained_draft, actor='student_a')
                allowed('teacher can retain a clone attachment while grading', 'PUT', WORK + 'edit',
                        {'id': clone_id, 'workFile': PREFIX + 'source', 'workCover': PREFIX + 'source', 'workStatus': '2',
                         'teachingWorkCorrectList': [{'score': 4, 'comment': 'retained clone'}]})
                denied('student cannot save the graded sent copy even with its retained foreign attachment',
                       'POST', WORK + 'submit', retained_draft, actor='student_a', code=409)
                allowed('clone recipient still reads metadata', 'GET', '/system/sysFile/queryById?id=' + PREFIX + 'source', actor='student_a')
                status, content = bytes_read(DIRECTORY + '/source.txt', 'student_a')
                check('clone recipient still reads exact shared bytes', status == 200 and content == (folder / 'source.txt').read_bytes())

                allowed('assignment accepts uploaded local media and external links', 'PUT', ADDITIONAL + 'edit',
                        dict(task, workCover=static + upload_key, workDocumentUrl='https://cdn.example.test/document.pdf',
                             workDesc='<p>Lesson text</p><img src="https://cdn.example.test/image.png">'))
                allowed('assignment can retain its authorized local reference', 'PUT', ADDITIONAL + 'edit',
                        dict(task, workCover=static + upload_key, workDesc='Updated lesson text'))
                remains_private('all permitted flows preserve unrelated private file', private_id, private_key)
        except Exception as failure:
            error = type(failure).__name__ + ': ' + str(failure)
        finally:
            owned = "SELECT id FROM teaching_work WHERE id LIKE '" + PREFIX + "%' OR work_name LIKE '" + NAME + "%'"
            sql('DELETE FROM teaching_work_correct WHERE work_id IN (' + owned + ')')
            sql('DELETE FROM teaching_work_comment WHERE work_id IN (' + owned + ')')
            sql('DELETE FROM sys_data_log WHERE data_id IN (' + owned + ')')
            sql("DELETE FROM teaching_work WHERE id LIKE '" + PREFIX + "%' OR work_name LIKE '" + NAME + "%'")
            sql("DELETE FROM teaching_additional_work WHERE id LIKE '" + PREFIX + "%' OR work_name LIKE '" + NAME + "%'")
            sql("DELETE FROM teaching_depart_day_log WHERE depart_id='" + PREFIX + "class'")
            sql("DELETE FROM sys_depart WHERE id='" + PREFIX + "class'")
            sql("DELETE FROM sys_file WHERE id LIKE '" + PREFIX + "%' OR file_path LIKE '" + DIRECTORY + "/%'")
            api.cache('DEL', cache_key)
            if folder.exists():
                shutil.rmtree(folder)
        check('all original business rows restored', rows() == original_rows, fatal=False)
        if has_media_index:
            check('original media reference index and state restored', media_index_snapshot(sql) == original_media_index, fatal=False)
        check('all original file bytes restored', files() == original_files, fatal=False)
        result = {'cases': cases, 'passed': sum(case['passed'] for case in cases), 'failed': sum(not case['passed'] for case in cases),
                  'total': len(cases), 'jar_sha256': api.jar_sha256, 'expected_legacy': args.expect_legacy, 'exception': error,
                  'created_at': datetime.now(timezone.utc).isoformat(),
                  'scope': 'Synthetic HTTP/login, owned MySQL state, upload/send/grade/save, private metadata and exact local bytes; no production or Qiniu execution.'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    return error is None and result['failed'] == 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('runtime', 'jar', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--expect-legacy', action='store_true')
    raise SystemExit(0 if verify(parser.parse_args()) else 1)
