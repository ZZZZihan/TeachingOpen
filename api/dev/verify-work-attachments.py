#!/usr/bin/env python3
"""Verify sent-work attachment lifetime against an isolated running backend."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from local_http import FixtureApi
from local_runtime import mysql_command

PREFIX = 'fixture_aprobe_'
NAME = 'attachment-probe-'
TRIGGER = 'fixture_attachment_delete_failure'
BASE = '/teaching/teachingWork/'
TABLES = ('teaching_work', 'teaching_work_correct', 'teaching_work_comment', 'sys_file')


def verify(args):
    cases = []
    with FixtureApi(args.runtime.resolve(), args.jar) as api:
        uploads = api.runtime / 'uploads'
        owned_paths = []

        def sql(query):
            return subprocess.check_output(mysql_command(api.runtime) + ['teachingopen_dev', '-e', query], text=True).strip()

        def snapshot():
            return {table: hashlib.sha256(sql('SELECT * FROM ' + table + ' ORDER BY id').encode()).hexdigest() for table in TABLES}

        def files():
            return {str(p.relative_to(uploads)): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in uploads.rglob('*') if p.is_file()}

        def check(name, passed):
            cases.append({'case': name, 'passed': bool(passed)})
            print(('PASS ' if passed else 'FAIL ') + name, flush=True)

        def call(method, path, actor='teacher_a', data=None):
            return api.request(method, BASE + path, actor, data)[:2]

        def allowed(name, method, path, actor='teacher_a', data=None):
            status, body = call(method, path, actor, data)
            check(name, status == 200 and body and body.get('success') is True)
            return body or {}

        def file(suffix, directory=False, missing=False, location=1):
            key = NAME + suffix + '.txt'
            path = uploads / key
            owned_paths.append(path)
            if directory:
                path.mkdir()
                (path / 'keep.txt').write_bytes(b'cannot reclaim a directory')
            elif not missing:
                path.write_bytes(('synthetic attachment ' + suffix).encode())
            ident = PREFIX + 'file_' + suffix
            sql("INSERT INTO sys_file (id,file_name,file_path,file_location) VALUES ('" + ident + "','" + key + "','" + key + "'," + str(location) + ")")
            return ident, path

        def work(suffix, attachment='', cover='', owner='fixture_student_a', department='fixture_class_a'):
            ident = PREFIX + suffix
            sql("INSERT INTO teaching_work (id,user_id,depart_id,work_name,work_type,work_status,work_file,work_cover,create_by,create_time) VALUES ('" + ident + "','" + owner + "','" + department + "','" + NAME + suffix + "','1',0,'" + attachment + "','" + cover + "','fixture_student_a','2026-10-03 00:00:00')")
            sql("INSERT INTO teaching_work_correct (id,work_id,score,comment) VALUES ('" + ident + "','" + ident + "',3,'synthetic feedback')")
            sql("INSERT INTO teaching_work_comment (id,work_id,user_id,comment) VALUES ('" + ident + "','" + ident + "','" + owner + "','synthetic comment')")
            return ident

        def row_exists(table, ident):
            return sql("SELECT COUNT(*) FROM " + table + " WHERE id='" + ident + "'") == '1'

        def intact(ident, path):
            return row_exists('sys_file', ident) and path.is_file()

        def reclaimed(ident, path):
            return not row_exists('sys_file', ident) and not path.exists()

        def sent(source, suffix):
            allowed(suffix + ' real send', 'POST', 'sendWork', data={'sendWorkId': source, 'userIdList': ['fixture_teacher_a']})
            clone = sql("SELECT id FROM teaching_work WHERE work_name='" + NAME + suffix + "' AND user_id='fixture_teacher_a'")
            if not clone or '\n' in clone:
                raise RuntimeError('Expected one sent copy')
            return clone

        def readable(ident, path):
            # Resolve the surviving work's file ID through real metadata HTTP,
            # then fetch exact bytes via the actual local static route.
            status, body, _ = api.request('GET', '/system/sysFile/queryById?id=' + ident, 'teacher_a')
            if status != 200 or not body or not body.get('success'):
                return False
            key = (body.get('result') or {}).get('filePath')
            if key != path.name:
                return False
            request = Request('http://127.0.0.1:' + str(api.ports['backend']) + '/api/sys/common/static/' + key,
                              headers={'X-Access-Token': api.tokens['teacher_a']})
            try:
                with urlopen(request, timeout=15) as response:
                    return response.status == 200 and response.read() == path.read_bytes()
            except HTTPError:
                return False

        original, original_files = snapshot(), files()
        if any(sql("SELECT COUNT(*) FROM " + table + " WHERE id LIKE '" + PREFIX + "%'") != '0' for table in TABLES):
            raise RuntimeError('Existing attachment probe rows')
        if sql("SELECT COUNT(*) FROM teaching_work WHERE work_name LIKE '" + NAME + "%'") != '0' or list(uploads.glob(NAME + '*')):
            raise RuntimeError('Existing attachment probe work or files')
        if sql("SELECT COUNT(*) FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA=DATABASE() AND TRIGGER_NAME='" + TRIGGER + "'") != '0':
            raise RuntimeError('Existing probe trigger')
        trigger_created = False
        try:
            for actor in ('teacher_a', 'teacher_b', 'student_a'):
                api.login(actor)
            attachment, path = file('source')
            cover, cover_path = file('cover')
            source = work('source', attachment, cover)
            clone = sent(source, 'source')
            clone_row = allowed('recipient reads sent copy', 'GET', 'queryById?id=' + clone).get('result', {})
            check('real send shares both source file IDs', clone_row.get('workFile') == attachment and clone_row.get('workCover') == cover)
            check('file and cover readable before deletion', readable(attachment, path) and readable(cover, cover_path))
            allowed('teacher deletes source', 'DELETE', 'delete?id=' + source)
            check('source and child rows deleted while recipient remains', not any(row_exists(t, source) for t in TABLES[:3]) and row_exists('teaching_work', clone))
            if args.expect_legacy:
                check('legacy source deletion loses recipient file and cover', reclaimed(attachment, path) and reclaimed(cover, cover_path))
            else:
                check('recipient file and cover retain metadata and exact HTTP bytes', readable(attachment, path) and readable(cover, cover_path))
                allowed('delete final recipient copy', 'DELETE', 'delete?id=' + clone)
                check('last reference reclaims file and cover', reclaimed(attachment, path) and reclaimed(cover, cover_path))
                allowed('repeat deletion is harmless', 'DELETE', 'delete?id=' + clone)

                attachment, path = file('reverse')
                source = work('reverse', attachment, attachment)
                clone = sent(source, 'reverse')
                allowed('delete recipient before source', 'DELETE', 'delete?id=' + clone)
                check('source survives reverse deletion and same-ID cover', readable(attachment, path))
                allowed('delete remaining source with same-ID cover', 'DELETE', 'delete?id=' + source)
                check('same-ID file and cover reclaimed once', reclaimed(attachment, path))

                attachment, path = file('batch')
                a = work('batch_a', attachment)
                b = work('batch_b', '', attachment)
                c = work('batch_c', attachment)
                allowed('delete subset batch with duplicate ID', 'DELETE', 'deleteBatch?ids=' + a + ',' + a + ',' + b)
                check('cross-field reference outside batch retains attachment', readable(attachment, path))
                allowed('delete final batch reference', 'DELETE', 'deleteBatch?ids=' + c)
                check('final batch reclaims metadata and bytes', reclaimed(attachment, path))

                attachment, path = file('all_batch')
                a = work('all_batch_a', attachment)
                b = work('all_batch_b', attachment)
                allowed('all shared copies deleted in one batch', 'DELETE', 'deleteBatch?ids=' + a + ',' + b)
                check('all-copy batch reclaims shared file', reclaimed(attachment, path))

                attachment, path = file('denied')
                a = work('denied_a', attachment)
                b = work('denied_b', attachment, owner='fixture_student_b', department='fixture_class_b')
                before, before_files = snapshot(), files()
                for actor, route in [('student_a', 'delete?id=' + a), ('teacher_b', 'delete?id=' + a),
                                     ('teacher_a', 'deleteBatch?ids=' + a + ',' + b)]:
                    status, body = call('DELETE', route, actor)
                    check(actor + ' unauthorized deletion rejected', status == 200 and body and body.get('success') is False and body.get('code') == 510)
                check('denied single and mixed batch preserve all rows and bytes', snapshot() == before and files() == before_files)

            # Force the second row of a batch to fail in MySQL, after the first
            # delete and child-row deletes have executed inside the transaction.
            attachment, path = file('rollback_a')
            other_attachment, other_path = file('rollback_b')
            a = work('rollback_a', attachment)
            b = work('rollback_b', other_attachment)
            before, before_files = snapshot(), files()
            sql("DELIMITER //\nCREATE TRIGGER " + TRIGGER + " BEFORE DELETE ON teaching_work FOR EACH ROW BEGIN IF OLD.id='" + b + "' THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='synthetic attachment rollback'; END IF; END//\nDELIMITER ;")
            trigger_created = True
            status, body = call('DELETE', 'deleteBatch?ids=' + a + ',' + b)
            check('injected batch database failure returns an error', body and body.get('success') is False)
            if args.expect_legacy:
                check('legacy rollback restores work but loses attachments', row_exists('teaching_work', a) and row_exists('teaching_work', b) and not path.exists() and not other_path.exists())
            else:
                check('failed batch restores works feedback comments metadata and bytes', snapshot() == before and files() == before_files)
            sql('DROP TRIGGER ' + TRIGGER)
            trigger_created = False

            if not args.expect_legacy:
                allowed('retry batch after removing database failure', 'DELETE', 'deleteBatch?ids=' + a + ',' + b)
                check('successful retry reclaims both attachments', reclaimed(attachment, path) and reclaimed(other_attachment, other_path))

                attachment, path = file('failure', directory=True)
                a = work('failure', attachment)
                allowed('work deletion commits despite attachment I/O failure', 'DELETE', 'delete?id=' + a)
                check('failed cleanup preserves metadata and directory contents', row_exists('sys_file', attachment) and (path / 'keep.txt').read_bytes() == b'cannot reclaim a directory' and not row_exists('teaching_work', a))
                attachment, path = file('missing', missing=True)
                a = work('missing', attachment)
                allowed('delete work whose file is already missing', 'DELETE', 'delete?id=' + a)
                check('already missing object metadata is reclaimed', reclaimed(attachment, path))

                attachment, path = file('alias')
                alias = PREFIX + 'file_alias_second'
                sql("INSERT INTO sys_file (id,file_name,file_path,file_location) SELECT '" + alias + "',file_name,file_path,file_location FROM sys_file WHERE id='" + attachment + "'")
                a = work('alias_a', attachment)
                b = work('alias_b', alias)
                allowed('delete work with an aliased physical file', 'DELETE', 'delete?id=' + a)
                check('aliased recipient retains metadata and readable bytes', row_exists('sys_file', attachment) and readable(alias, path))

                attachment, path = file('unknown', location=0)
                a = work('unknown', attachment)
                allowed('work with unknown file storage can be deleted', 'DELETE', 'delete?id=' + a)
                check('unknown storage remains available for diagnosis', intact(attachment, path))
                a = work('empty')
                allowed('empty attachments are harmless', 'DELETE', 'delete?id=' + a)

            jar_hash = api.jar_sha256
        finally:
            if trigger_created:
                sql('DROP TRIGGER ' + TRIGGER)
            for table in TABLES[1:3]:
                sql("DELETE FROM " + table + " WHERE work_id IN (SELECT id FROM teaching_work WHERE work_name LIKE '" + NAME + "%') OR id LIKE '" + PREFIX + "%'")
            sql("DELETE FROM teaching_work WHERE work_name LIKE '" + NAME + "%'; DELETE FROM sys_file WHERE id LIKE '" + PREFIX + "%'")
            for path in owned_paths:
                if path.is_dir():
                    (path / 'keep.txt').unlink()
                    path.rmdir()
                else:
                    path.unlink(missing_ok=True)
        check('original work feedback comment and file rows restored', snapshot() == original)
        check('original file bytes restored', files() == original_files)
        check('temporary failure trigger removed', sql("SELECT COUNT(*) FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA=DATABASE() AND TRIGGER_NAME='" + TRIGGER + "'") == '0')
    report = {'observed_utc': datetime.now(timezone.utc).isoformat(), 'jar_sha256': jar_hash,
              'expected_legacy': args.expect_legacy, 'passed': sum(c['passed'] for c in cases), 'total': len(cases), 'cases': cases,
              'scope': 'actual synthetic HTTP/login/send/delete, MySQL rollback injection and local attachment bytes; no browser editor, Qiniu, concurrent writer or global file API acceptance'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(str(report['passed']) + '/' + str(report['total']) + ' checks passed')
    return report['passed'] == report['total']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', required=True, type=Path)
    parser.add_argument('--jar', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--expect-legacy', action='store_true')
    raise SystemExit(0 if verify(parser.parse_args()) else 1)
