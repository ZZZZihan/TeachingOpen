#!/usr/bin/env python3
"""Retired Minio demo routes and retained local uploads on an owned fixture.

Refuse a JAR containing the retired cloud controller before sending any demo
request. Require local uploads and disabled loopback Minio configuration. All
HTTP requests use loopback directly and cannot follow redirects. A legacy JAR
is never exercised against its hardcoded external storage provider.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
from urllib.error import HTTPError
from urllib.parse import quote, urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener
from uuid import uuid4
from zipfile import ZipFile

from local_http import FixtureApi
from local_recovery import database_inventory, file_inventory, private_write, sql
from media_index_fixture import media_index_snapshot


DEMO_CLASS = 'BOOT-INF/classes/org/jeecg/modules/demo/test/controller/MinioController.class'
ACTORS = (None, 'student_a', 'teacher_a', 'admin')


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def multipart(directory, content):
    boundary = 'fixture-minio-demo-boundary'
    body = ('--' + boundary + '\r\nContent-Disposition: form-data; name="biz"\r\n\r\n'
            + directory + '\r\n--' + boundary
            + '\r\nContent-Disposition: form-data; name="file"; filename="probe.txt"\r\n'
            + 'Content-Type: text/plain\r\n\r\n').encode()
    return body + content + ('\r\n--' + boundary + '--\r\n').encode(), 'multipart/form-data; boundary=' + boundary


def aliases(operation):
    canonical = '/test/minio/' + operation
    return (canonical, canonical + '/', canonical + ';fixture=1', canonical + '.js',
            canonical + '.json', '/%74est/minio/' + operation,
            '/test/%6dinio/' + operation, '/test%2Fminio/' + operation)


def verify(args):
    if args.output.exists() or args.output.is_symlink():
        raise RuntimeError('Preserve existing Minio demo evidence; choose a new output')
    jar = args.jar.resolve()
    cases, responses, error, cleanup_error = [], [], None, None

    def check(name, passed, fatal=True):
        cases.append({'case': name, 'passed': bool(passed)})
        print(('PASS ' if passed else 'FAIL ') + name, flush=True)
        if fatal and not passed:
            raise AssertionError(name)

    # This artifact gate deliberately precedes FixtureApi login and every HTTP
    # request. A regression fails without running the old external-cloud code.
    with ZipFile(jar) as archive:
        entries = set(archive.namelist())
    check('candidate contains no executable Minio demo controller', DEMO_CLASS not in entries)
    for name in ('config/MinioConfig', 'modules/system/controller/SysUploadController'):
        check('candidate retains configured storage component ' + name,
              'BOOT-INF/classes/org/jeecg/' + name + '.class' in entries)

    with FixtureApi(args.runtime.resolve(), jar) as api:
        # The CI adapter binds application.properties; the local runtime guard
        # binds config/application-localtest.properties. Both keep real secrets
        # private, and only these harmless safety assertions enter the report.
        config = api.runtime / 'application.properties'
        if not config.exists():
            config = api.runtime / 'config/application-localtest.properties'
        values = dict(line.split('=', 1) for line in config.read_text().splitlines()
                      if line and not line.startswith('#') and '=' in line)
        check('fixture upload mode is local', values.get('jeecg.uploadType') == 'local')
        check('fixture Minio endpoint and credentials are disabled loopback values',
              urlsplit(values.get('jeecg.minio.minio_url', '')).hostname in ('127.0.0.1', 'localhost', '::1')
              and values.get('jeecg.minio.minio_name') == 'disabled'
              and values.get('jeecg.minio.minio_pass') == 'disabled')

        origin = 'http://127.0.0.1:' + str(api.ports['backend']) + '/api'
        opener = build_opener(ProxyHandler({}), NoRedirect())
        uploads = api.runtime / 'uploads'
        directory = 'fixture-minio-demo-' + uuid4().hex
        folder = uploads / directory
        if folder.exists() or folder.is_symlink():
            raise RuntimeError('Owned local-upload control directory already exists')

        def request(method, path, actor, body=None, content_type=None, extra_headers=None):
            headers = dict(extra_headers or {})
            if actor:
                headers['X-Access-Token'] = api.tokens[actor]
            if content_type:
                headers['Content-Type'] = content_type
            try:
                response = opener.open(Request(origin + path, body, headers, method=method), timeout=15)
            except HTTPError as failure:
                response = failure
            with response:
                raw = response.read()
                try:
                    payload = json.loads(raw)
                except (ValueError, UnicodeDecodeError):
                    payload = None
                return response.status, payload, raw, response.headers

        def index():
            return media_index_snapshot(lambda statement: sql(api.runtime, statement))

        def snapshot():
            return {'database': database_inventory(api.runtime), 'uploads': file_inventory(uploads), 'media_index': index()}

        for actor in ACTORS[1:]:
            api.login(actor)
        original = snapshot()
        demo_body, demo_type = multipart(directory, b'retired demo must not upload these bytes\n')
        try:
            for actor in ACTORS:
                for operation, method in (('upload', 'POST'), ('download', 'GET'), ('url', 'GET')):
                    for path in aliases(operation):
                        status, payload, raw, headers = request(method, path, actor,
                                                              demo_body if operation == 'upload' else None,
                                                              demo_type if operation == 'upload' else None)
                        label = str(actor or 'anonymous') + ' ' + method + ' ' + path
                        responses.append({'actor': actor or 'anonymous', 'method': method, 'path': path,
                                          'status': status, 'body_sha256': hashlib.sha256(raw).hexdigest()})
                        # Canonical authenticated requests must reach the actual
                        # missing-route result. Alias rejection can happen first
                        # in Shiro/Tomcat; it must never execute a cloud method.
                        expected = (404,) if actor and path == '/test/minio/' + operation else (400, 401, 403, 404)
                        check(label + ' cannot enter a demo handler', status in expected
                              and not (isinstance(payload, dict) and payload.get('success') is True)
                              and 'Content-Disposition' not in headers and 'Location' not in headers)
                after = snapshot()
                check(str(actor or 'anonymous') + ' retired routes preserve every database table',
                      after['database'] == original['database'])
                check(str(actor or 'anonymous') + ' retired routes preserve all upload bytes',
                      after['uploads'] == original['uploads'])
                check(str(actor or 'anonymous') + ' retired routes preserve media index and state',
                      after['media_index'] == original['media_index'])

            # Independent success controls exercise the configured local storage
            # path for each authenticated role, with ownership and exact bytes.
            for actor in ACTORS[1:]:
                content = ('retained local upload by fixture ' + actor + '\n').encode()
                body, content_type = multipart(directory + '/' + actor, content)
                status, payload, _, _ = request('POST', '/sys/common/upload', actor, body, content_type)
                check(actor + ' legitimate local upload succeeds', status == 200 and isinstance(payload, dict)
                      and payload.get('success') is True and isinstance(payload.get('message'), str))
                key = payload['message']
                relative = PurePosixPath(key)
                check(actor + ' local upload remains in its owned control directory',
                      not relative.is_absolute() and '..' not in relative.parts
                      and key.startswith(directory + '/' + actor + '/')
                      and (uploads / key).is_file() and (uploads / key).read_bytes() == content)
                literal = "CONVERT(0x" + key.encode().hex() + ' USING utf8mb4)'
                count = sql(api.runtime, 'SELECT COUNT(*) FROM teachingopen_dev.sys_file WHERE file_path='
                            + literal + " AND file_location=1 AND del_flag=0 AND create_by='fixture_" + actor + "'")
                check(actor + ' local upload has one persisted ownership record', count == '1')
                path = '/sys/common/static/' + quote(key, safe='/')
                status, _, raw, _ = request('GET', path, actor)
                check(actor + ' can read its exact local-upload bytes', status == 200 and raw == content)
                status, _, raw, headers = request('GET', path, actor, extra_headers={'Range': 'bytes=0-4'})
                check(actor + ' local upload retains range reads', status == 206 and raw == content[:5]
                      and headers.get('Content-Range') == 'bytes 0-4/' + str(len(content)))
                status, _, raw, _ = request('GET', path, None)
                check(actor + ' unpublished upload remains private', status in (401, 403, 404) and raw != content)
        except Exception as failure:
            error = type(failure).__name__ + ': ' + str(failure)
        finally:
            try:
                # A fresh UUID namespace belongs exclusively to this probe.
                # No existing file, unrelated row, or derived index is repaired.
                sql(api.runtime, "DELETE FROM teachingopen_dev.sys_file WHERE file_path LIKE '" + directory + "/%'")
                if folder.is_symlink():
                    raise RuntimeError('Unexpected link in owned control directory; cleanup refused')
                if folder.exists():
                    shutil.rmtree(folder)
            except Exception as failure:
                cleanup_error = type(failure).__name__ + ': ' + str(failure)
            try:
                restored = snapshot()
                business = lambda state: {name: value for name, value in state['database'].items() if name != 'sys_log'}
                check('all original non-audit business tables restored after local controls',
                      business(restored) == business(original), fatal=False)
                check('all original upload bytes restored after local controls',
                      restored['uploads'] == original['uploads'], fatal=False)
                check('original media index and state restored without rebuilding',
                      restored['media_index'] == original['media_index'], fatal=False)
            except Exception as failure:
                cleanup_error = cleanup_error or type(failure).__name__ + ': ' + str(failure)

        result = {'created_at': datetime.now(timezone.utc).isoformat(), 'jar_sha256': api.jar_sha256,
                  'cases': cases, 'responses': responses, 'passed': sum(case['passed'] for case in cases),
                  'failed': sum(not case['passed'] for case in cases), 'total': len(cases),
                  'exception': error, 'cleanup_exception': cleanup_error,
                  'scope': 'Exact candidate JAR absence gate, real synthetic loopback HTTP/login, retired routes and aliases for anonymous/student/teacher/admin, database/uploads/media-index preservation, local upload/ownership/private byte and range controls. No production or external Minio provider validation; normal login/logout audit records retained.'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    private_write(args.output, json.dumps(result, indent=2) + '\n')
    print(str(result['passed']) + '/' + str(result['total']) + ' checks passed', flush=True)
    return error is None and cleanup_error is None and result['failed'] == 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('runtime', 'jar', 'output'):
        parser.add_argument('--' + name, required=True, type=Path)
    raise SystemExit(0 if verify(parser.parse_args()) else 1)
