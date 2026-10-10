#!/usr/bin/env python3
"""Test actual multipart uploads inside the synthetic runtime and its owned probes."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import secrets
import subprocess
import tempfile
import zipfile
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen
from local_http import FixtureApi
from local_runtime import mysql_command

PREFIX = 'upload-boundary-probe'


def verify(args):
    cases = []
    with FixtureApi(args.runtime.resolve(), args.jar) as api:
        uploads = api.runtime / 'uploads'
        outside = api.runtime / (PREFIX + '-outside')
        sandbox = uploads / PREFIX
        if outside.exists() or sandbox.exists():
            raise RuntimeError('Probe directory already exists')
        existing_work = subprocess.check_output(mysql_command(api.runtime) + ['teachingopen_dev', '-e', "SELECT COUNT(*) FROM teaching_work WHERE work_name='" + PREFIX + "'"], text=True).strip()
        if existing_work != '0':
            raise RuntimeError('Probe work already exists')
        outside.mkdir()
        sandbox.mkdir()
        (outside / 'sentinel.txt').write_bytes(b'outside sentinel')
        (sandbox / 'blocked').write_bytes(b'not a directory')
        (sandbox / 'external-link').symlink_to(outside, target_is_directory=True)
        (sandbox / 'internal').mkdir()
        (sandbox / 'internal-link').symlink_to(sandbox / 'internal', target_is_directory=True)
        (sandbox / 'readonly').mkdir()
        (sandbox / 'readonly').chmod(0o500)
        owned = []
        work_ids = []
        file_ids = []

        def sql(query):
            return subprocess.check_output(mysql_command(api.runtime) + ['teachingopen_dev', '-e', query], text=True).strip()

        def tables():
            return {t: hashlib.sha256(sql('SELECT * FROM ' + t + ' ORDER BY id').encode()).hexdigest()
                    for t in ('sys_file', 'teaching_work')}

        def files(root):
            return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in root.rglob('*') if p.is_file() and not p.is_symlink()}

        original_files = files(uploads)
        original_tables = tables()

        def check(name, passed):
            cases.append({'case': name, 'passed': bool(passed)})
            print(('PASS ' if passed else 'FAIL ') + name, flush=True)

        def upload(fields=None, actor='student_a', content=b'synthetic upload bytes', filename='example.sb3', include_file=True, token=None):
            boundary = 'fixture-' + secrets.token_hex(12)
            body = bytearray()
            for key, value in (fields or {}).items():
                body.extend(('--' + boundary + '\r\nContent-Disposition: form-data; name="' + key + '"\r\n\r\n' + value + '\r\n').encode())
            if include_file:
                body.extend(('--' + boundary + '\r\nContent-Disposition: form-data; name="file"; filename="' + filename + '"\r\nContent-Type: application/octet-stream\r\n\r\n').encode())
                body.extend(content)
                body.extend(b'\r\n')
            body.extend(('--' + boundary + '--\r\n').encode())
            headers = {'Content-Type': 'multipart/form-data; boundary=' + boundary}
            if actor is not None:
                headers['X-Access-Token'] = api.tokens[actor]
            elif token is not None:
                headers['X-Access-Token'] = token
            req = Request('http://127.0.0.1:' + str(api.ports['backend']) + '/api/sys/common/upload', bytes(body), headers, method='POST')
            try:
                response = urlopen(req, timeout=15)
            except HTTPError as error:
                response = error
            with response:
                payload = json.loads(response.read())
                if payload.get('success') and payload.get('message') != 'local':
                    path = (uploads / payload['message']).resolve()
                    # Refuse cleanup outside the two explicitly owned test roots.
                    if not (path.is_relative_to(uploads.resolve()) or path.is_relative_to(outside.resolve())):
                        raise RuntimeError('Unexpected test upload destination')
                    owned.append(path)
                    if not args.expect_legacy:
                        relative = str(path.relative_to(uploads))
                        file_ids.extend(sql("SELECT id FROM sys_file WHERE file_path='" + relative.replace("'", "''") + "'").splitlines())
                return response.status, payload

        def rejected(name, fields, **kwargs):
            before, outside_before = files(uploads), files(outside)
            status, body = upload(fields, **kwargs)
            check(name, body.get('success') is False and not str(api.runtime) in json.dumps(body)
                  and files(uploads) == before and files(outside) == outside_before)

        try:
            for actor in ('student_a', 'teacher_a', 'admin'):
                api.login(actor)
            if args.expect_legacy:
                status, body = upload({'biz': '../' + outside.name})
                check('legacy parent directory escapes configured upload root', body.get('success') and owned[-1].parent == outside and owned[-1].read_bytes() == b'synthetic upload bytes')
                status, body = upload({'biz': PREFIX + '/external-link'})
                check('legacy symlink writes outside upload root', body.get('success') and owned[-1].parent == outside)
                status, body = upload({'bizPath': PREFIX + '/python'})
                check('legacy editor directory parameter ignored', body.get('success') and '/' not in body['message'])
            else:
                for label, fields in [
                    ('parent directory', {'biz': '../' + outside.name}),
                    ('nested traversal', {'biz': PREFIX + '/../../' + outside.name}),
                    ('editor alias traversal', {'bizPath': '../' + outside.name}),
                    ('absolute directory', {'biz': str(outside)}),
                    ('backslash traversal', {'biz': '..\\' + outside.name}),
                    ('drive path', {'biz': 'C:/uploads'}),
                    ('dot segment', {'biz': PREFIX + '/./child'}),
                    ('NUL directory', {'biz': PREFIX + '/\x00child'}),
                    ('outside symlink', {'biz': PREFIX + '/external-link'}),
                    ('inside symlink', {'biz': PREFIX + '/internal-link'}),
                    ('existing file directory', {'biz': PREFIX + '/blocked/child'}),
                    ('unwritable directory', {'biz': PREFIX + '/readonly'}),
                    ('conflicting aliases', {'biz': PREFIX + '/a', 'bizPath': PREFIX + '/b'})]:
                    rejected(label + ' rejected without byte changes', fields)
                rejected('missing multipart file returns safe failure', {'biz': PREFIX}, include_file=False)
                before = files(uploads)
                status, body, _ = api.request('POST', '/sys/common/upload', 'student_a', {})
                check('non-multipart upload returns safe error without writes', status == 200 and body.get('success') is False
                      and body.get('message') == '请选择上传文件' and files(uploads) == before)
                for actor, token, label in [(None, None, 'anonymous'), (None, 'invalid-upload-token', 'invalid token')]:
                    before = files(uploads)
                    status, body = upload({'biz': PREFIX}, actor=actor, token=token)
                    check(label + ' upload denied before writing', status == 401 and body.get('success') is False and files(uploads) == before)
                for actor in ('student_a', 'teacher_a', 'admin'):
                    for key in ('biz', 'bizPath'):
                        directory = PREFIX + '/' + actor + '/' + key
                        status, body = upload({key: directory}, actor)
                        check(actor + ' ' + key + ' upload preserves returned relative path and bytes', status == 200 and body.get('success') is True
                              and body['message'].startswith(directory + '/') and owned[-1].read_bytes() == b'synthetic upload bytes')
                for fields, content, filename, label in [
                    ({}, b'root bytes', 'root.txt', 'default root'),
                    ({'biz': PREFIX + '/same', 'bizPath': PREFIX + '/same'}, b'matching', 'same.sb3', 'matching aliases'),
                    ({'bizPath': PREFIX + '/python'}, b'', 'empty.py', 'empty Python file'),
                    ({'bizPath': PREFIX + '/scratchjr'}, b'synthetic sjr', 'project.sjr', 'ScratchJr extension'),
                    ({'bizPath': PREFIX + '/中文资料'}, '中文内容'.encode(), '课程.txt', 'Unicode directory and file'),
                    ({'biz': PREFIX}, b'no extension', 'project', 'extensionless file'),
                    ({'biz': PREFIX}, b'archive', 'project.tar.gz', 'compound extension'),
                    ({'biz': PREFIX}, b'filename traversal', '../attempt.txt', 'client path basename'),
                    ({'biz': PREFIX}, b'x' * (2 * 1024 * 1024), 'large.sb3', 'two MiB file')]:
                    status, body = upload(fields, content=content, filename=filename)
                    check(label + ' succeeds with exact bytes inside root', status == 200 and body.get('success') is True
                          and owned[-1].is_relative_to(uploads.resolve()) and owned[-1].read_bytes() == content
                          and '..' not in Path(body['message']).parts)
                first = upload({'biz': PREFIX}, content=b'first version', filename='same.py')[1]['message']
                second = upload({'biz': PREFIX}, content=b'second version', filename='same.py')[1]['message']
                check('same client filename cannot overwrite earlier bytes', first != second and (uploads / first).read_bytes() == b'first version' and (uploads / second).read_bytes() == b'second version')
                before = files(uploads)
                status, body = upload({'jeditor': 'true'}, include_file=False)
                check('legacy local base64 editor marker retained without disk write', status == 200 and body.get('success') is True and body.get('message') == 'local' and files(uploads) == before)
                content = b'print("synthetic upload pipeline")\n'
                status, body = upload({'bizPath': PREFIX + '/python'}, content=content, filename='pipeline.py')
                key = body['message']
                status, body, _ = api.request('POST', '/system/sysFile/add', 'student_a', {'fileName': 'pipeline.py', 'filePath': key, 'fileLocation': 1, 'fileType': 2})
                check('uploaded path can be registered by existing editor request', status == 200 and body.get('success') is True)
                file_ids.append(body['result']['id'])
                status, body, _ = api.request('POST', '/teaching/teachingWork/submit', 'student_a', {'workName': PREFIX, 'workType': '4', 'workStatus': '0', 'workFile': file_ids[-1]})
                check('uploaded file can be saved as an actual student draft', status == 200 and body.get('success') is True)
                ident = sql("SELECT id FROM teaching_work WHERE work_name='" + PREFIX + "'")
                if not ident or '\n' in ident: raise RuntimeError('Expected exactly one pipeline work')
                work_ids.append(ident)
                status, body, _ = api.request('GET', '/teaching/teachingWork/studentWorkInfo?workId=' + ident, 'student_a')
                check('owner reopens draft with nested uploaded file URL', status == 200 and body.get('success') is True and body['result'].get('workFileKey') == key)
                request = Request('http://127.0.0.1:' + str(api.ports['backend']) + '/api/sys/common/static/' + quote(key), headers={'X-Access-Token': api.tokens['student_a']})
                with urlopen(request, timeout=15) as response:
                    check('actual HTTP download returns uploaded draft bytes', response.status == 200 and response.read() == content)
                request.add_header('Range', 'bytes=0-4')
                with urlopen(request, timeout=15) as response:
                    check('nested upload retains byte-range reads', response.status == 206 and response.read() == content[:5])
                status, body, _ = api.request('DELETE', '/teaching/teachingWork/delete?id=' + ident, 'teacher_a')
                check('normal work deletion reclaims pipeline file metadata and bytes', status == 200 and body.get('success') is True
                      and not (uploads / key).exists() and sql("SELECT COUNT(*) FROM sys_file WHERE id='" + file_ids[-1] + "'") == '0')
                if args.java_home is None: raise RuntimeError('--java-home is required for packaged streaming fault checks')
                jar = args.jar or Path(__file__).resolve().parents[1] / 'jeecg-boot-module-system/target/teaching-open-2.8.0.jar'
                with tempfile.TemporaryDirectory(prefix='teaching-upload-fault-') as folder:
                    temp = Path(folder)
                    with zipfile.ZipFile(jar) as archive:
                        for name in archive.namelist():
                            if name.startswith(('BOOT-INF/lib/jeecg-boot-base-common-', 'BOOT-INF/lib/spring-web-', 'BOOT-INF/lib/spring-core-')) and name.endswith('.jar'):
                                (temp / Path(name).name).write_bytes(archive.read(name))
                    classpath = str(temp) + '/*'
                    java = args.java_home.resolve() / 'bin/java'
                    subprocess.run([str(java.with_name('javac')), '-cp', classpath, '-d', str(temp), str(Path(__file__).with_name('VerifyLocalUploadFailure.java'))], check=True, capture_output=True)
                    output = subprocess.check_output([str(java), '-cp', str(temp) + ':' + classpath, 'VerifyLocalUploadFailure', str(temp / 'fault-files')], text=True)
                    for fault in (0, 1, 2):
                        check('packaged streaming fault ' + str(fault) + ' cleans partial bytes', 'PASS streaming fault ' + str(fault) + ':' in output)
            # New candidates register ownership at upload time; remove only rows
            # belonging to this run before checking the original snapshot.
            for ident in file_ids:
                sql("DELETE FROM sys_file WHERE id='" + ident + "'")
            check('upload does not silently change existing file or work records', tables() == original_tables)
            jar_hash = api.jar_sha256
        finally:
            for ident in work_ids:
                sql("DELETE FROM teaching_work WHERE id='" + ident + "'")
            for ident in file_ids:
                sql("DELETE FROM sys_file WHERE id='" + ident + "'")
            for path in set(owned):
                path.unlink(missing_ok=True)
            (sandbox / 'external-link').unlink()
            (sandbox / 'internal-link').unlink()
            (sandbox / 'blocked').unlink()
            (sandbox / 'readonly').chmod(0o700)
            for path in sorted(sandbox.rglob('*'), key=lambda p: len(p.parts), reverse=True):
                if not path.is_dir():
                    raise RuntimeError('Unexpected remaining file in owned probe')
                path.rmdir()
            sandbox.rmdir()
            (outside / 'sentinel.txt').unlink()
            outside.rmdir()
        baseline_files = {p: h for p, h in original_files.items() if not p.startswith(PREFIX + '/')}
        check('original upload bytes restored', files(uploads) == baseline_files)
        check('owned external probe and links removed', not outside.exists() and not sandbox.exists())
    report = {'observed_utc': datetime.now(timezone.utc).isoformat(), 'jar_sha256': jar_hash, 'expected_legacy': args.expect_legacy,
              'passed': sum(c['passed'] for c in cases), 'total': len(cases), 'cases': cases,
              'scope': 'actual local multipart uploads and filesystem bytes; does not prove file ownership, downloads, cloud upload or browser editor workflows'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(str(report['passed']) + '/' + str(report['total']) + ' checks passed')
    return report['passed'] == report['total']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', required=True, type=Path)
    parser.add_argument('--jar', type=Path)
    parser.add_argument('--java-home', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--expect-legacy', action='store_true')
    raise SystemExit(0 if verify(parser.parse_args()) else 1)
