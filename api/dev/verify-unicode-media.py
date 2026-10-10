#!/usr/bin/env python3
"""Desired Unicode media behavior through real HTTP in one owned local runtime.

The assertions are identical for the baseline and the candidate. No service is
started or stopped, and credentials, CAPTCHA values and response bodies are not
written to evidence. The full original fixture user rows stay only in memory.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import http.client
import json
import os
from pathlib import Path
import secrets
import shutil
import stat
import struct
import subprocess
from urllib.parse import quote
from uuid import uuid4
import zlib

from local_http import FixtureApi
from local_recovery import database_inventory, private_write
from local_runtime import load_ports, mysql_command


EXPECTED_PORTS = {'mysql': 13368, 'redis': 16441, 'backend': 18169, 'frontend': 18170}
STATIC = '/api/sys/common/static/'
ACTORS = ('admin', 'teacher_a', 'teacher_b', 'student_a', 'student_b')


def literal(value):
    return 'CONVERT(0x' + str(value).encode('utf-8').hex() + ' USING utf8mb4)'


def png(red, green, blue):
    """Produce actual lossless PNG bytes; no media-generation dependency."""
    def chunk(kind, data):
        return struct.pack('!I', len(data)) + kind + data + struct.pack('!I', zlib.crc32(kind + data) & 0xffffffff)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('!2I5B', 2, 2, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress((b'\0' + bytes((red, green, blue)) * 2) * 2)) + chunk(b'IEND', b''))


def attachment_inventory(root):
    """Include every directory, regular byte stream and link without following it."""
    result = {}
    for directory, dirs, files in os.walk(root, followlinks=False):
        for name in dirs + files:
            item = Path(directory) / name
            mode = item.lstat().st_mode
            record = {'mode': stat.S_IMODE(mode)}
            if stat.S_ISLNK(mode):
                record.update(kind='symlink', target=os.readlink(item))
            elif stat.S_ISDIR(mode):
                record.update(kind='directory')
            elif stat.S_ISREG(mode):
                record.update(kind='file', bytes=item.stat().st_size, sha256=hashlib.sha256(item.read_bytes()).hexdigest())
            else:
                raise RuntimeError('Unexpected special file in owned attachment tree')
            result[item.relative_to(root).as_posix()] = record
    return dict(sorted(result.items()))


def verify(args):
    runtime = args.runtime.resolve()
    if (runtime.name != 'unicode-media-1003' or runtime.parent.name != '.devspace'
            or runtime.is_symlink() or load_ports(runtime) != EXPECTED_PORTS):
        raise ValueError('Only the unicode-media-1003 local runtime is authorized')
    if args.output.exists():
        raise ValueError('Evidence already exists; use a fresh output name')
    lock = runtime / 'unicode-media-probe.lock'
    lock_fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(lock_fd)
    cases, observations = [], []
    prefix = 'fixture_ump_' + uuid4().hex[:10]
    uploads = runtime / 'uploads'
    sandbox = uploads / prefix
    outside = runtime / (prefix + '_outside.txt')
    baseline, restored, original_files, final_files = None, None, None, None
    fatal = None

    def check(name, passed, **details):
        cases.append({'case': name, 'passed': bool(passed), **details})
        print(('PASS ' if passed else 'FAIL ') + name, flush=True)

    try:
        with FixtureApi(runtime, args.jar) as api:
            def sql(statement):
                result = subprocess.run(mysql_command(runtime) + ['teachingopen_dev', '-e', statement],
                                        capture_output=True, text=True, timeout=25)
                if result.returncode:
                    raise RuntimeError('Owned Unicode fixture SQL operation failed')
                return result.stdout.rstrip('\n')

            def insert(table, suffix, **fields):
                fields = dict(id=prefix + suffix, **fields)
                sql('INSERT INTO `' + table + '` (' + ','.join('`' + k + '`' for k in fields)
                    + ') VALUES (' + ','.join('NULL' if v is None else literal(v) for v in fields.values()) + ')')
                return fields['id']

            def update(table, suffix, **fields):
                sql('UPDATE `' + table + '` SET ' + ','.join('`' + k + '`=' + ('NULL' if v is None else literal(v))
                    for k, v in fields.items()) + ' WHERE id=' + literal(prefix + suffix))

            def call(method, raw_path, actor=None, headers=None, data=None, port=None):
                h = dict(headers or {})
                if actor is not None:
                    h['X-Access-Token'] = api.tokens[actor]
                connection = http.client.HTTPConnection('127.0.0.1', port or EXPECTED_PORTS['backend'], timeout=15)
                try:
                    # http.client preserves the ASCII request target, including
                    # percent escapes and dot segments; no URL normalization.
                    connection.request(method, raw_path, body=data, headers=h)
                    reply = connection.getresponse()
                    body = reply.read(1024 * 1024 + 1)
                    if len(body) > 1024 * 1024:
                        raise RuntimeError('Unexpectedly large synthetic response')
                    return reply.status, body, {k.lower(): v for k, v in reply.getheaders()}
                finally:
                    connection.close()

            def media(key, actor=None, method='GET', headers=None, raw_path=None):
                return call(method, raw_path or STATIC + quote(key, safe='/'), actor, headers)

            def details(reply):
                status, body, headers = reply
                keep = ('content-type', 'content-disposition', 'content-range', 'content-length',
                        'cache-control', 'accept-ranges', 'x-content-type-options')
                return {'http_status': status, 'body_bytes': len(body), 'body_sha256': hashlib.sha256(body).hexdigest(),
                        'headers': {k: headers[k] for k in keep if k in headers}}

            def allow(name, key, payload, actor=None, method='GET', headers=None, mime='image/png'):
                reply = media(key, actor, method, headers)
                status, body, h = reply
                disposition = ('attachment' if mime == 'application/octet-stream' else 'inline')
                expected_disposition = disposition + "; filename*=UTF-8''" + quote(Path(key).name, safe='')
                passed = (status == 200 and body == (b'' if method == 'HEAD' else payload)
                          and h.get('content-length') == str(len(payload)) and 'content-range' not in h
                          and h.get('content-type') == mime and h.get('content-disposition') == expected_disposition
                          and h.get('cache-control') == 'no-store' and h.get('x-content-type-options') == 'nosniff')
                check(name, passed, expected_status=200, expected_body_sha256=hashlib.sha256(payload).hexdigest(), **details(reply))
                return reply

            def ranged(name, key, payload, actor=None, headers=None):
                h = dict(headers or {}, Range='bytes=2-8')
                reply = media(key, actor, headers=h)
                status, body, rh = reply
                check(name, status == 206 and body == payload[2:9] and rh.get('content-range') == 'bytes 2-8/' + str(len(payload))
                      and rh.get('content-length') == '7' and rh.get('cache-control') == 'no-store'
                      and rh.get('content-disposition') == "inline; filename*=UTF-8''" + quote(Path(key).name, safe=''),
                      expected_status=206, **details(reply))

            sentinels = []

            def deny(name, key, expected, actor=None, method='GET', headers=None, raw_path=None):
                reply = media(key, actor, method, headers, raw_path)
                status, body, h = reply
                permitted_codes = (expected,) if isinstance(expected, int) else tuple(expected)
                check(name, status in permitted_codes and not any(p in body for p in sentinels)
                      and 'content-range' not in h, expected_status=list(permitted_codes), **details(reply))

            baseline = database_inventory(runtime)
            original_files = attachment_inventory(uploads)
            columns = [line.split('\t')[0] for line in sql('SHOW COLUMNS FROM sys_user').splitlines()]
            user_expression = ','.join("IFNULL(HEX(CAST(`" + c + "` AS BINARY)),'~')" for c in columns)
            users = sql("SELECT 'ROW'," + user_expression + ' FROM sys_user ORDER BY id').splitlines()
            if len(users) != 5 or sandbox.exists() or outside.exists():
                raise RuntimeError('Expected untouched five-account fixture and unused namespace')
            cookies = {}
            app_values = dict(line.split('=', 1) for line in (runtime / 'config/application-localtest.properties').read_text().splitlines()
                              if line and not line.startswith('#') and '=' in line)
            cookie_name = app_values.get('jeecg.media.cookie-name', 'teaching_media')
            try:
                for actor in ACTORS:
                    api.login(actor)
                    cookies[actor] = next((c.split(';')[0] for c in api.last_response_headers.get_all('Set-Cookie', [])
                                          if c.startswith(cookie_name + '=')), '')
                    check('synthetic login issues media cookie ' + actor, bool(cookies[actor]))

                sandbox.mkdir()
                public_key = prefix + '/课程资料/课程封面.png'
                private_key = prefix + '/私人作业/作业预览.png'
                unit_key = prefix + '/单元资料/中文视频.png'
                rich_key = prefix + '/单元资料/富文本图片.png'
                red, green, blue, yellow = png(250, 30, 20), png(20, 220, 30), png(10, 20, 250), png(240, 240, 20)
                outside_payload = b'SYNTHETIC-UNICODE-OUTSIDE-SENTINEL'
                sentinels.extend((red, green, blue, yellow, outside_payload))
                def fixture_file(key, payload):
                    path = uploads / key
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(payload)
                for key, payload in ((public_key, red), (private_key, green), (unit_key, blue), (rich_key, yellow)):
                    fixture_file(key, payload)
                outside.write_bytes(outside_payload)

                public_id = insert('teaching_course', 'pub', course_name='合成中文首页课程', course_cover=public_key, show_home=1, is_shared=0)
                private_id = insert('sys_file', 'private', create_by='fixture_student_a', file_path=private_key,
                                    file_name='作业预览.png', file_location=1, file_type=2, del_flag=0)
                insert('teaching_work', 'work', user_id='fixture_student_a', depart_id='fixture_class_a', work_name='合成中文私有作业',
                       work_file=private_id, work_type=1, work_status=0, create_by='fixture_student_a', create_time='2026-10-03 00:00:00')
                insert('teaching_course_unit', 'unit', unit_name='合成中文单元', course_id='fixture_course_a',
                       course_video=unit_key, show_course_video=1,
                       media_content='<img src="' + STATIC + quote(rich_key, safe='/') + '">')

                for method in ('GET', 'HEAD'):
                    allow('public Chinese course cover ' + method, public_key, red, method=method)
                ranged('public Chinese course cover Range', public_key, red)
                for method, h, code, body in (('GET', {}, 200, red), ('HEAD', {}, 200, b''),
                                              ('GET', {'Range': 'bytes=2-8'}, 206, red[2:9])):
                    reply = call(method, STATIC + quote(public_key, safe='/'), headers=h, port=EXPECTED_PORTS['frontend'])
                    check('same-origin proxy Chinese public cover ' + method + (' Range' if h else ''),
                          reply[0] == code and reply[1] == body and reply[2].get('content-disposition')
                          == "inline; filename*=UTF-8''" + quote(Path(public_key).name, safe=''), expected_status=code, **details(reply))
                for actor in ('student_a', 'teacher_a', 'admin'):
                    for method in ('GET', 'HEAD'):
                        allow('private Chinese work ' + actor + ' ' + method, private_key, green, actor, method)
                    ranged('private Chinese work ' + actor + ' Range', private_key, green, actor)
                for actor, code in ((None, 401), ('student_b', 403), ('teacher_b', 403)):
                    for method in ('GET', 'HEAD'):
                        deny('private Chinese work denied ' + str(actor) + ' ' + method, private_key, code, actor, method)
                    deny('private Chinese work Range denied ' + str(actor), private_key, code, actor, headers={'Range': 'bytes=2-8'})
                for key, payload, label in ((unit_key, blue, 'unit video'), (rich_key, yellow, 'unit rich image')):
                    for actor in ('student_a', 'teacher_a', 'admin'):
                        allow('Chinese ' + label + ' permitted ' + actor, key, payload, actor)
                        ranged('Chinese ' + label + ' Range ' + actor, key, payload, actor)
                    for actor, code in ((None, 401), ('student_b', 403), ('teacher_b', 403)):
                        deny('Chinese ' + label + ' denied ' + str(actor), key, code, actor)
                        deny('Chinese ' + label + ' HEAD denied ' + str(actor), key, code, actor, method='HEAD')
                update('teaching_course_unit', 'unit', show_course_video=0)
                deny('hidden Chinese unit video denied enrolled student', unit_key, 403, 'student_a')
                allow('hidden Chinese unit video retained for class teacher', unit_key, blue, 'teacher_a')
                update('teaching_course_unit', 'unit', del_flag=1)
                deny('deleted Chinese unit image denied enrolled student', rich_key, 403, 'student_a')
                update('teaching_course_unit', 'unit', del_flag=0, show_course_video=1)

                # Real valid uploads contain Unicode in both supported directory
                # parameters. A multi-dot original extension also produces a
                # Unicode basename in the server-generated storage key.
                def upload(field, actor='student_a'):
                    directory = prefix + ('/课程上传' if field == 'biz' else '/编辑器上传')
                    boundary = 'fixture-ump-' + secrets.token_hex(10)
                    name = '课程封面.png' if field == 'biz' else '课程.中文.png'
                    payload = red if field == 'biz' else blue
                    body = ('--' + boundary + '\r\nContent-Disposition: form-data; name="' + field + '"\r\n\r\n'
                            + directory + '\r\n--' + boundary + '\r\nContent-Disposition: form-data; name="file"; filename="'
                            + name + '"\r\nContent-Type: image/png\r\n\r\n').encode() + payload + ('\r\n--' + boundary + '--\r\n').encode()
                    reply = call('POST', '/api/sys/common/upload', actor,
                                 {'Content-Type': 'multipart/form-data; boundary=' + boundary}, body)
                    try:
                        result = json.loads(reply[1])
                    except ValueError:
                        result = {}
                    if actor is None:
                        check('anonymous actual Unicode multipart upload denied', reply[0] == 401 and result.get('success') is False,
                              expected_status=401, business_success=result.get('success'), **details(reply))
                        return
                    key = result.get('message', '') if result.get('success') else ''
                    safe = isinstance(key, str) and key.startswith(directory + '/') and '..' not in key.split('/')
                    check('actual Unicode ' + field + ' multipart succeeds', reply[0] == 200 and result.get('success') is True and safe,
                          expected_status=200, business_success=result.get('success'), **details(reply))
                    if not safe:
                        observations.append({'case': 'upload ' + field, 'value': 'No safe successful object key; dependent read checks omitted'})
                        return
                    disk = uploads / key
                    rows = sql('SELECT id,create_by,file_location,del_flag,HEX(file_path),HEX(file_name) FROM sys_file WHERE BINARY file_path=BINARY ' + literal(key)).splitlines()
                    row = rows[0].split('\t') if len(rows) == 1 else []
                    check('actual Unicode ' + field + ' upload bytes and ownership recorded', disk.is_file() and disk.read_bytes() == payload
                          and len(row) == 6 and row[1:4] == ['fixture_student_a', '1', '0'] and row[4].lower() == key.encode().hex()
                          and row[5].lower() == name.encode().hex(), matching_metadata_rows=len(rows))
                    if len(row) != 6:
                        return
                    insert('teaching_work', 'up_' + field, user_id='fixture_student_a', depart_id='fixture_class_a',
                           work_name='合成中文上传作业', work_file=row[0], work_type=1, work_status=0,
                           create_by='fixture_student_a', create_time='2026-10-03 00:00:00')
                    allow('actual Unicode ' + field + ' uploaded object GET', key, payload, 'student_a')
                    allow('actual Unicode ' + field + ' uploaded object HEAD', key, payload, 'student_a', 'HEAD')
                    ranged('actual Unicode ' + field + ' uploaded object Range', key, payload, 'student_a')
                    allow('actual Unicode ' + field + ' work readable by class teacher', key, payload, 'teacher_a')
                    deny('actual Unicode ' + field + ' uploaded object cross-class denied', key, 403, 'student_b')
                    deny('actual Unicode ' + field + ' uploaded object anonymous denied', key, 401)
                upload('biz')
                upload('bizPath')
                files_before_rejection, db_before_rejection = attachment_inventory(uploads), database_inventory(runtime)
                upload('biz', actor=None)
                db_after_rejection = database_inventory(runtime)
                check('anonymous Unicode upload writes no business rows or bytes', files_before_rejection == attachment_inventory(uploads)
                      and all(db_before_rejection[t] == db_after_rejection.get(t) for t in db_before_rejection if t != 'sys_log'))

                # Exercise raw storage keys, encoded same-origin URI references,
                # special but legal filenames, and distinct neighboring bytes.
                names = ('中文根.png', 'space name.png', 'plus+name.png', '50%name.png', '课件.中文.png', '封面A.png', '封面Ａ.png')
                for index, name in enumerate(names):
                    key = prefix + '/' + name
                    payload = red if index % 2 == 0 else blue
                    fixture_file(key, payload)
                    insert('sys_config', 'name' + str(index), config_key=prefix + str(index), config_enabled=1,
                           config_value='<img src="' + STATIC + quote(key, safe='/+') + '">')
                    allow('encoded local reference preserves exact bytes ' + name, key, payload)
                control_key = prefix + '/ascii/private.png'
                fixture_file(control_key, yellow)
                insert('sys_file', 'control', file_path=control_key, file_name='private.png', file_location=1, del_flag=0, create_by='fixture_student_a')
                allow('ASCII private control remains readable by owner', control_key, yellow, 'student_a')
                deny('ASCII private control remains denied cross class', control_key, 403, 'student_b')
                deny('case-insensitive DB lookup cannot alias private storage key', control_key.upper(), 403, 'student_a')

                # Grant URLs must match exactly, including the local origin.
                update('teaching_course', 'pub', course_cover=STATIC + quote(public_key, safe='/'))
                allow('encoded same-origin course cover reference remains public', public_key, red)
                update('teaching_course', 'pub', course_cover='https://other.invalid' + STATIC + quote(public_key, safe='/'))
                deny('external-origin Chinese reference grants no anonymous access', public_key, 401)
                update('teaching_course', 'pub', course_cover='x' + public_key)
                deny('substring Chinese reference grants no anonymous access', public_key, 401)
                update('teaching_course', 'pub', course_cover=public_key, del_flag=1)
                deny('deleted homepage Chinese cover no longer public', public_key, 401)
                update('teaching_course', 'pub', del_flag=0)

                allow('cookie-only Chinese private image returns actual PNG', private_key, green,
                      headers={'Cookie': cookies['student_a']})
                allow('cookie-only Chinese private HEAD', private_key, green, method='HEAD', headers={'Cookie': cookies['student_a']})
                ranged('cookie-only Chinese private Range', private_key, green, headers={'Cookie': cookies['student_a']})
                reply = call('GET', STATIC + quote(private_key, safe='/'), headers={'Cookie': cookies['student_a']},
                             port=EXPECTED_PORTS['frontend'])
                check('same-origin proxy cookie-only Chinese private PNG bytes', reply[0] == 200 and reply[1] == green,
                      expected_status=200, **details(reply))
                deny('foreign token takes precedence over owner media cookie', private_key, 403, 'student_b', headers={'Cookie': cookies['student_a']})
                deny('invalid token cannot fall back to owner media cookie', private_key, 401,
                     headers={'Cookie': cookies['student_a'], 'X-Access-Token': 'synthetic-ump-invalid'})
                deny('supplied invalid token still rejects public Chinese cover', public_key, 401,
                     headers={'X-Access-Token': 'synthetic-ump-invalid'})
                sql('UPDATE sys_user SET status=2 WHERE username=' + literal('fixture_student_a'))
                for method in ('GET', 'HEAD'):
                    deny('frozen owner Chinese media denied ' + method, private_key, 401, 'student_a', method)
                    deny('frozen owner ASCII media denied ' + method, control_key, 401, 'student_a', method)
                deny('frozen owner cookie Chinese media denied', private_key, 401, headers={'Cookie': cookies['student_a']})
                sql('UPDATE sys_user SET status=1 WHERE username=' + literal('fixture_student_a'))
                allow('restored owner Chinese media readable', private_key, green, 'student_a')

                # Links are forbidden even if the administrator has metadata
                # access. Check final-component and intermediate-component links.
                for name, target in (('外部链接.png', outside), ('内部链接.png', uploads / public_key)):
                    (sandbox / name).symlink_to(target)
                    deny('Unicode symlink refuses bytes ' + name, prefix + '/' + name, 404, 'admin')
                (sandbox / '目录链接').symlink_to(uploads / prefix / '课程资料', target_is_directory=True)
                deny('Unicode intermediate symlink refuses bytes', prefix + '/目录链接/课程封面.png', 404, 'admin')

                encoded = quote(private_key, safe='/')
                encoded_dir = quote(prefix + '/私人作业/', safe='/')
                encoded_name = quote('作业预览.png', safe='')
                invalid_paths = {
                    'literal semicolon': STATIC + encoded + ';parameter=1',
                    'encoded semicolon': STATIC + encoded + '%3bparameter=1',
                    'encoded backslash': STATIC + encoded_dir + '%5c' + encoded_name,
                    'literal backslash': STATIC + encoded_dir + '\\' + encoded_name,
                    'dot segment': STATIC + encoded_dir + './' + encoded_name,
                    'parent segment': STATIC + encoded_dir + '../' + quote('私人作业/作业预览.png', safe='/'),
                    'encoded dot segment': STATIC + encoded_dir + '%2e/' + encoded_name,
                    'encoded parent segment': STATIC + encoded_dir + '%2e%2e/' + quote('私人作业/作业预览.png', safe='/'),
                    'double encoded parent': STATIC + encoded_dir + '%252e%252e/' + encoded_name,
                    'encoded slash': STATIC + encoded.replace('/', '%2f'),
                    'double encoded slash': STATIC + encoded.replace('/', '%252f'),
                    'double encoded Unicode basename': STATIC + encoded_dir + encoded_name.replace('%', '%25'),
                    'empty path segment': STATIC + encoded_dir + '/' + encoded_name,
                    'encoded NUL': STATIC + encoded_dir + '%00' + encoded_name,
                    'encoded LF': STATIC + encoded_dir + '%0a' + encoded_name,
                    'encoded DEL': STATIC + encoded_dir + '%7f' + encoded_name,
                    'Unicode C1 control': STATIC + encoded_dir + '%C2%85' + encoded_name,
                    'illegal UTF8 continuation': STATIC + encoded_dir + '%80' + encoded_name,
                    'illegal UTF8 overlong slash': STATIC + encoded_dir + '%c0%af' + encoded_name,
                    'illegal UTF8 surrogate': STATIC + encoded_dir + '%ed%a0%80' + encoded_name,
                    'illegal UTF8 out of range': STATIC + encoded_dir + '%f4%90%80%80' + encoded_name,
                    'illegal UTF8 truncated': STATIC + encoded_dir + '%e4%b8' + encoded_name,
                    'invalid percent escape': STATIC + encoded_dir + '%GG' + encoded_name,
                }
                for label, path in invalid_paths.items():
                    for method in ('GET', 'HEAD'):
                        deny('malformed path refuses bytes ' + label + ' ' + method, private_key, (400, 401, 403, 404), 'admin', method, raw_path=path)
                    deny('malformed path refuses Range ' + label, private_key, (400, 401, 403, 404), 'admin',
                         headers={'Range': 'bytes=2-8'}, raw_path=path)
                # Unicode lookalikes are legal characters; these unknown keys
                # must never normalize into or read the real ASCII-delimited key.
                for label, value in (('fullwidth slash', private_key.replace('/', '／')),
                                     ('division slash', private_key.replace('/', '∕')),
                                     ('fullwidth dot', private_key.replace('.png', '．png')),
                                     ('fullwidth semicolon', private_key + '；parameter=1')):
                    deny('Unicode lookalike does not alias real file ' + label, value, (400, 401, 403, 404), 'admin')

                stale_token, stale_cookie = api.tokens['student_a'], cookies['student_a']
                logout_status, logout_result, _ = api.request('GET', '/sys/logout', 'student_a')
                check('owner actual logout succeeds', logout_status == 200 and logout_result and logout_result.get('success') is True)
                for key, label in ((private_key, 'Chinese'), (control_key, 'ASCII')):
                    for method in ('GET', 'HEAD'):
                        deny('logged-out token denied ' + label + ' ' + method, key, 401, method=method,
                             headers={'X-Access-Token': stale_token})
                    deny('logged-out cookie denied ' + label, key, 401, headers={'Cookie': stale_cookie, 'Range': 'bytes=2-8'})
            except Exception as error:
                # Only type is retained: urllib/SQL/HTTP errors can include
                # credential-bearing commands, response bodies or local paths.
                fatal = type(error).__name__
                check('probe completed without an execution error', False, error_type=fatal)
            finally:
                api.close()
                for table in ('teaching_work', 'teaching_course_unit', 'teaching_course', 'sys_config'):
                    sql('DELETE FROM `' + table + '` WHERE LEFT(id,' + str(len(prefix)) + ')=' + literal(prefix))
                sql('DELETE FROM sys_file WHERE LEFT(id,' + str(len(prefix)) + ')=' + literal(prefix)
                    + ' OR LEFT(file_path,' + str(len(prefix) + 1) + ')=' + literal(prefix + '/'))
                for row in users:
                    values = row.split('\t')[1:]
                    assignments = []
                    for column, value in zip(columns, values):
                        expression = 'NULL' if value == '~' else ("''" if value == '' else 'CONVERT(0x' + value + ' USING utf8mb4)')
                        if column != 'id':
                            assignments.append('`' + column + '`=' + expression)
                    sql('UPDATE sys_user SET ' + ','.join(assignments) + ' WHERE id=CONVERT(0x'
                        + values[columns.index('id')] + ' USING utf8mb4)')
                if sandbox.is_symlink():
                    raise RuntimeError('Owned sandbox unexpectedly became a symlink')
                if sandbox.exists():
                    shutil.rmtree(sandbox)
                outside.unlink(missing_ok=True)
            restored = database_inventory(runtime)
            final_files = attachment_inventory(uploads)
            changed_tables = [t for t in baseline if t != 'sys_log' and baseline[t] != restored.get(t)]
            check('all complete business rows and table schemas restored except ordinary sys_log',
                  baseline.keys() == restored.keys() and not changed_tables, changed_tables=changed_tables, table_count=len(baseline))
            changed_files = [p for p in set(original_files) | set(final_files) if original_files.get(p) != final_files.get(p)]
            check('all original attachment bytes directories modes and links restored', not changed_files,
                  changed_paths=sorted(changed_files), original_entries=len(original_files))
            jar_sha256 = api.jar_sha256
    finally:
        lock.unlink(missing_ok=True)
    report = {'observed_utc': datetime.now(timezone.utc).isoformat(), 'label': args.label,
              'jar_sha256': jar_sha256, 'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'scope': 'Actual loopback HTTP and database with five task-owned synthetic CLI accounts; legitimate multipart Unicode biz/bizPath uploads; full-row/schema and attachment restoration. No browser, production, playable video, capacity or manual acceptance claim.',
              'expected_behavior_identical_before_after': True, 'passed': sum(c['passed'] for c in cases), 'total': len(cases),
              'cases': cases, 'observations': observations, 'error_type': fatal,
              'database_before': baseline, 'database_after': restored,
              'attachments_before_sha256': hashlib.sha256(json.dumps(original_files, sort_keys=True).encode()).hexdigest(),
              'attachments_after_sha256': hashlib.sha256(json.dumps(final_files, sort_keys=True).encode()).hexdigest()}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    private_write(args.output, json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(str(report['passed']) + '/' + str(report['total']) + ' checks passed', flush=True)
    return report['passed'] == report['total']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', required=True, type=Path)
    parser.add_argument('--jar', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--label', choices=('baseline', 'candidate'), required=True)
    raise SystemExit(0 if verify(parser.parse_args()) else 1)
