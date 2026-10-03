#!/usr/bin/env python3
"""Desired percent-encoded reference behavior in one owned local runtime.

Use the identical expectations for baseline and candidate. This probe performs
real loopback HTTP, owns only a unique fixture namespace, preserves full user
rows in memory, and compares every database row/schema and attachment afterward.
It never starts/stops a service or authenticates a browser.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import http.client
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from urllib.parse import quote
from uuid import uuid4

from local_http import FixtureApi
from local_recovery import database_inventory, private_write
from local_runtime import load_ports, mysql_command

spec = importlib.util.spec_from_file_location('unicode_helpers', Path(__file__).with_name('verify-unicode-media.py'))
helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helpers)

EXPECTED_PORTS = {'mysql': 13369, 'redis': 16442, 'backend': 18171, 'frontend': 18172}
STATIC = '/api/sys/common/static/'
ACTORS = ('admin', 'teacher_a', 'teacher_b', 'student_a', 'student_b')
TABLES = ('sys_config', 'teaching_news', 'teaching_additional_work', 'teaching_course_unit',
          'teaching_work', 'teaching_course', 'sys_file')


def literal(value):
    # MySQL has no empty 0x binary literal; keep all nonempty UTF-8 values hex-safe.
    return "''" if str(value) == '' else helpers.literal(value)


def lower_escapes(value):
    return re.sub(r'%[0-9A-Fa-f]{2}', lambda match: match.group().lower(), value)


def verify(args):
    runtime = args.runtime.absolute()
    if (runtime != runtime.resolve() or runtime.name != 'encoded-media-1003'
            or runtime.parent.name != '.devspace' or load_ports(runtime) != EXPECTED_PORTS):
        raise ValueError('Only the non-symlink encoded-media-1003 synthetic runtime is authorized')
    if args.output.exists():
        raise ValueError('Evidence exists; use a fresh output name')
    lock = runtime / 'encoded-media-probe.lock'
    os.close(os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600))
    cases, observations, cleanup_errors = [], [], []
    prefix = 'fixture_emr_' + uuid4().hex[:10]
    uploads, sandbox = runtime / 'uploads', runtime / 'uploads' / prefix
    before, after, files_before, files_after = None, None, None, None
    fatal, jar_sha256 = None, None

    def check(name, passed, **fields):
        cases.append({'case': name, 'passed': bool(passed), **fields})
        print(('PASS ' if passed else 'FAIL ') + name, flush=True)

    try:
        with FixtureApi(runtime, args.jar) as api:
            jar_sha256 = api.jar_sha256
            config = dict(line.split('=', 1) for line in (runtime / 'config/application-localtest.properties').read_text().splitlines()
                          if line and not line.startswith('#') and '=' in line)
            reference_base = config['jeecg.path.staticDomain'].rstrip('/') + '/'
            cookie_name = config.get('jeecg.media.cookie-name', 'teaching_media')

            def sql(statement):
                result = subprocess.run(mysql_command(runtime) + ['--default-character-set=utf8mb4', 'teachingopen_dev', '-e', statement],
                                        capture_output=True, text=True, timeout=25)
                if result.returncode:
                    raise RuntimeError('Owned encoded-reference fixture SQL operation failed')
                return result.stdout.rstrip('\n')

            def insert(table, suffix, **fields):
                fields = dict(id=prefix + suffix, **fields)
                sql('INSERT INTO `' + table + '` (' + ','.join('`' + key + '`' for key in fields)
                    + ') VALUES (' + ','.join('NULL' if value is None else literal(value) for value in fields.values()) + ')')
                return fields['id']

            def update(table, suffix, **fields):
                sql('UPDATE `' + table + '` SET ' + ','.join('`' + key + '`=' + ('NULL' if value is None else literal(value))
                    for key, value in fields.items()) + ' WHERE id=' + literal(prefix + suffix))

            def call(key, actor=None, method='GET', headers=None):
                request_headers = dict(headers or {})
                if actor is not None:
                    request_headers['X-Access-Token'] = api.tokens[actor]
                connection = http.client.HTTPConnection('127.0.0.1', EXPECTED_PORTS['backend'], timeout=15)
                try:
                    connection.request(method, STATIC + quote(key, safe='/'), headers=request_headers)
                    reply = connection.getresponse()
                    body = reply.read(1024 * 1024 + 1)
                    if len(body) > 1024 * 1024:
                        raise RuntimeError('Unexpectedly large synthetic response')
                    return reply.status, body, {key.lower(): value for key, value in reply.getheaders()}
                finally:
                    connection.close()

            def details(reply):
                status, body, headers = reply
                keep = ('content-type', 'content-disposition', 'content-range', 'content-length',
                        'cache-control', 'x-content-type-options')
                return {'http_status': status, 'body_bytes': len(body), 'body_sha256': hashlib.sha256(body).hexdigest(),
                        'headers': {key: value for key, value in headers.items() if key in keep}}

            sentinels = []

            def allow(name, key, payload, actor=None, method='GET', headers=None):
                reply = call(key, actor, method, headers)
                status, body, response_headers = reply
                ranged = method == 'GET' and bool(headers and headers.get('Range'))
                desired_status = 206 if ranged else 200
                desired_body = payload[2:9] if ranged else (b'' if method == 'HEAD' else payload)
                passed = (status == desired_status and body == desired_body
                          and response_headers.get('content-length') == str(7 if ranged else len(payload))
                          and response_headers.get('content-type') == 'image/png'
                          and response_headers.get('content-disposition') == "inline; filename*=UTF-8''" + quote(Path(key).name, safe='')
                          and response_headers.get('cache-control') == 'no-store'
                          and response_headers.get('x-content-type-options') == 'nosniff'
                          and (response_headers.get('content-range') == 'bytes 2-8/' + str(len(payload)) if ranged
                               else 'content-range' not in response_headers))
                check(name, passed, expected_status=desired_status, expected_body_sha256=hashlib.sha256(desired_body).hexdigest(), **details(reply))
                return reply

            def deny(name, key, actor=None, expected=None, method='GET', headers=None):
                desired = expected if expected is not None else (401 if actor is None and not headers else 403)
                reply = call(key, actor, method, headers)
                check(name, reply[0] == desired and not any(payload in reply[1] for payload in sentinels)
                      and 'content-range' not in reply[2], expected_status=desired, **details(reply))

            def fixture(name):
                key = prefix + '/' + name
                path = uploads / key
                path.parent.mkdir(parents=True, exist_ok=True)
                if path.exists():
                    raise RuntimeError('Fixture filename aliases an already-created byte stream')
                index = len(sentinels) + 1
                payload = helpers.png((index * 29) % 255, (index * 53) % 255, (index * 79) % 255)
                path.write_bytes(payload)
                sentinels.append(payload)
                return key, payload

            def url(key):
                return reference_base + quote(key, safe='/')

            def html(reference):
                return '<img src="' + reference + '">'

            before = database_inventory(runtime)
            files_before = helpers.attachment_inventory(uploads)
            columns = [line.split('\t')[0] for line in sql('SHOW COLUMNS FROM sys_user').splitlines()]
            expression = ','.join("IFNULL(HEX(CAST(`" + column + "` AS BINARY)),'~')" for column in columns)
            original_users = sql("SELECT 'ROW'," + expression + ' FROM sys_user ORDER BY id').splitlines()
            if len(original_users) != 5 or sandbox.exists():
                raise RuntimeError('Expected untouched synthetic users and namespace')
            cookies = {}
            try:
                for actor in ACTORS:
                    api.login(actor)
                    cookies[actor] = next((cookie.split(';')[0] for cookie in api.last_response_headers.get_all('Set-Cookie', [])
                                          if cookie.startswith(cookie_name + '=')), '')
                    check('actual fixture login issues configured media cookie ' + actor, bool(cookies[actor]))
                sandbox.mkdir()

                # The original defect remains a desired 200 check in both runs.
                plus, plus_bytes = fixture('original+cover.png')
                insert('sys_config', 'original', config_key=prefix + 'original', config_enabled=1, config_value=html(url(plus)))
                reply = allow('original legal percent2B HTML reference', plus, plus_bytes)
                observations.append({'case': 'original legal percent2B HTML reference', 'desired_status': 200,
                                     'returned_expected_bytes': reply[1] == plus_bytes, **details(reply)})
                update('sys_config', 'original', config_value=html(reference_base + quote(plus, safe='/+')))
                reply = allow('original literal plus HTML comparison', plus, plus_bytes)
                observations.append({'case': 'original literal plus HTML comparison', 'desired_status': 200,
                                     'returned_expected_bytes': reply[1] == plus_bytes, **details(reply)})
                update('sys_config', 'original', config_enabled=0)

                cover, cover_bytes = fixture('course/封面+space name.png')
                insert('teaching_course', 'course', course_name='合成百分号封面', course_cover='', show_home=1, is_shared=0)
                representations = (
                    ('raw storage key', cover),
                    ('configured same-origin percent2B uppercase', url(cover)),
                    ('configured same-origin percent2b lowercase', lower_escapes(url(cover))),
                    ('literal plus with encoded Chinese and space', reference_base + quote(cover, safe='/+')),
                    ('optional unreserved first character encoded', reference_base + '%66' + quote(cover[1:], safe='/')),
                    ('mixed raw and encoded characters', reference_base + '%66' + quote(cover[1:], safe='/+').replace('space', '%73pace')),
                    ('HTML percent-encoded href', '<a href="' + url(cover) + '">合成</a>'),
                    ('JSON percent-encoded string', json.dumps({'cover': url(cover)}, ensure_ascii=False)),
                )
                for label, reference in representations:
                    update('teaching_course', 'course', course_cover=reference)
                    allow('public course ' + label, cover, cover_bytes)
                update('teaching_course', 'course', course_cover=url(cover))
                allow('encoded public cover HEAD', cover, cover_bytes, method='HEAD')
                allow('encoded public cover Range', cover, cover_bytes, headers={'Range': 'bytes=2-8'})
                update('teaching_course', 'course', show_home=0)
                deny('withdrawing homepage grant denies anonymous encoded cover', cover)
                update('teaching_course', 'course', show_home=1, del_flag=1)
                deny('deleted course cannot grant encoded cover', cover)
                update('teaching_course', 'course', show_home=0, del_flag=0, course_cover='')

                # Private unit and additional-work candidates must retain current class scope.
                unit, unit_bytes = fixture('unit/视频+名.png')
                rich, rich_bytes = fixture('unit/富文本+名.png')
                plan, plan_bytes = fixture('unit/教案+名.png')
                insert('teaching_course_unit', 'unit', unit_name='合成百分号私有单元', course_id='fixture_course_a',
                       course_video=json.dumps([{'url': lower_escapes(url(unit))}]), show_course_video=1,
                       media_content=html(url(rich)), course_plan=url(plan), show_course_plan=0)
                for actor in (None, 'student_a', 'teacher_a', 'student_b', 'teacher_b', 'admin'):
                    if actor in ('student_a', 'teacher_a', 'admin'):
                        allow('encoded unit JSON permitted ' + actor, unit, unit_bytes, actor)
                        allow('encoded unit HTML permitted ' + actor, rich, rich_bytes, actor)
                    else:
                        deny('encoded unit JSON denied ' + str(actor), unit, actor)
                        deny('encoded unit HTML denied ' + str(actor), rich, actor)
                allow('encoded private unit cookie-only GET', unit, unit_bytes, headers={'Cookie': cookies['student_a']})
                allow('encoded private unit cookie-only HEAD', unit, unit_bytes, method='HEAD', headers={'Cookie': cookies['student_a']})
                allow('encoded private unit cookie-only Range', unit, unit_bytes, headers={'Cookie': cookies['student_a'], 'Range': 'bytes=2-8'})
                deny('cross-class cookie cannot authorize encoded unit', unit, expected=403, headers={'Cookie': cookies['student_b']})
                update('teaching_course_unit', 'unit', show_course_video=0)
                deny('hidden encoded unit video denied student', unit, 'student_a')
                allow('hidden encoded unit video retained for teacher', unit, unit_bytes, 'teacher_a')
                deny('hidden encoded plan denied student', plan, 'student_a')
                allow('hidden encoded plan retained for teacher', plan, plan_bytes, 'teacher_a')
                update('teaching_course_unit', 'unit', del_flag=1)
                deny('deleted unit encoded HTML denied student', rich, 'student_a')
                deny('deleted unit encoded HTML denied teacher', rich, 'teacher_a')
                update('teaching_course_unit', 'unit', del_flag=0, show_course_video=1)

                starter, starter_bytes = fixture('additional/起始+名.png')
                document, document_bytes = fixture('additional/文档+名.png')
                insert('teaching_additional_work', 'additional', work_name='合成百分号附加作业', work_dept='fixture_class_a', status=1,
                       work_url=lower_escapes(url(starter)), work_document_url=json.dumps({'url': url(document)}))
                for actor in (None, 'student_a', 'teacher_a', 'student_b', 'teacher_b', 'admin'):
                    if actor in ('student_a', 'teacher_a', 'admin'):
                        allow('encoded additional starter permitted ' + actor, starter, starter_bytes, actor)
                    else:
                        deny('encoded additional starter denied ' + str(actor), starter, actor)
                allow('encoded additional document JSON class student', document, document_bytes, 'student_a')
                update('teaching_additional_work', 'additional', status=0)
                deny('closed additional encoded starter denied student', starter, 'student_a')
                allow('closed additional encoded starter retained for teacher', starter, starter_bytes, 'teacher_a')
                update('teaching_additional_work', 'additional', status=1, work_dept='fixture_class_b')
                deny('reassigned additional starter denied old class student', starter, 'student_a')
                deny('reassigned additional starter denied old class teacher', starter, 'teacher_a')
                update('teaching_additional_work', 'additional', status=0, work_url='', work_document_url='')

                config_key, config_bytes = fixture('config/配置+名.png')
                insert('sys_config', 'config', config_key=prefix + 'config', config_enabled=1, config_value=html(lower_escapes(url(config_key))))
                allow('enabled sysconfig lowercase percent HTML anonymous', config_key, config_bytes)
                update('sys_config', 'config', config_value=json.dumps({'image': url(config_key)}))
                allow('enabled sysconfig percent JSON anonymous', config_key, config_bytes)
                update('sys_config', 'config', config_enabled=0)
                deny('disabled sysconfig percent JSON anonymous', config_key)
                deny('disabled sysconfig percent JSON student', config_key, 'student_a')

                news, news_bytes = fixture('news/资讯+名.png')
                insert('teaching_news', 'news', news_title='合成百分号资讯', news_status=1, news_content=json.dumps([{'src': lower_escapes(url(news))}]))
                allow('published news encoded JSON anonymous', news, news_bytes)
                update('teaching_news', 'news', news_content=html(url(news)))
                allow('published news encoded HTML anonymous', news, news_bytes)
                update('teaching_news', 'news', news_status=0)
                deny('draft news encoded HTML anonymous', news)
                deny('draft news encoded HTML student', news, 'student_a')

                # One reference must grant exactly one distinct byte stream.
                pair_plus, pair_plus_bytes = fixture('identity/pair+name.png')
                pair_space, pair_space_bytes = fixture('identity/pair name.png')
                percent, percent_bytes = fixture('identity/percent%2Bname.png')
                decoded_plus, decoded_plus_bytes = fixture('identity/percent+name.png')
                insert('sys_config', 'identity', config_key=prefix + 'identity', config_enabled=1, config_value=url(pair_plus))
                allow('percent2B grants plus filename', pair_plus, pair_plus_bytes)
                deny('percent2B does not grant neighboring space filename', pair_space)
                update('sys_config', 'identity', config_value=url(pair_space))
                allow('percent20 grants space filename', pair_space, pair_space_bytes)
                deny('percent20 does not grant neighboring plus filename', pair_plus)
                update('sys_config', 'identity', config_value=url(percent))
                allow('percent252B decodes once to literal percent2B filename', percent, percent_bytes)
                deny('percent252B cannot grant plus through double decoding', decoded_plus)
                update('sys_config', 'identity', config_value=url(decoded_plus))
                allow('percent2B grants plus comparison file', decoded_plus, decoded_plus_bytes)
                deny('percent2B cannot grant literal percent2B comparison file', percent)
                update('sys_config', 'identity', config_value=percent)
                allow('raw literal percent storage key remains exact', percent, percent_bytes)
                update('sys_config', 'identity', config_value='')

                target, target_bytes = fixture('boundary/exact+name.png')
                longer, longer_bytes = fixture('boundary/exact+name.png.more.png')
                # APFS may alias different case to the same file. Test the case
                # spelling as a reference/request key without overwriting bytes.
                upper = prefix + '/boundary/EXACT+name.png'
                neighbor, neighbor_bytes = fixture('boundary/other+name.png')
                insert('sys_config', 'boundary', config_key=prefix + 'boundary', config_enabled=1, config_value='')
                for label, invalid in (
                    ('foreign origin same static path', 'https://other.invalid' + STATIC + quote(target, safe='/')),
                    ('substring raw key', 'x' + target),
                    ('substring encoded URL path', reference_base + 'x' + quote(target, safe='/')),
                    ('similar longer key', url(longer)),
                    ('different case key', url(upper)),
                    ('different exact key', url(neighbor)),
                    ('invalid percent syntax', url(target).replace('%2B', '%GG')),
                ):
                    update('sys_config', 'boundary', config_value=html(invalid))
                    deny('exact reference rejects ' + label + ' anonymous', target)
                    deny('exact reference rejects ' + label + ' authenticated', target, 'student_a')
                update('sys_config', 'boundary', config_value=url(target))
                allow('boundary valid encoded exact key', target, target_bytes)
                for key, label in ((longer, 'longer filename'), (upper, 'case-different filename'), (neighbor, 'neighbor filename')):
                    deny('valid encoded target does not publish ' + label, key)
                update('sys_config', 'boundary', config_value='')

                replacement, replacement_bytes = fixture('utf8/�name.png')
                slash_replacements, slash_bytes = fixture('utf8/��name.png')
                insert('sys_config', 'utf8', config_key=prefix + 'utf8', config_enabled=1, config_value=url(replacement))
                allow('valid percentEF BF BD grants exact replacement-character filename', replacement, replacement_bytes)
                for label, escape, key in (
                    ('illegal single byte', '%FF', replacement),
                    ('truncated sequence', '%E4%B8', replacement),
                    ('surrogate sequence', '%ED%A0%80', replacement),
                    ('overlong slash', '%C0%AF', slash_replacements),
                ):
                    encoded = reference_base + quote(prefix + '/utf8/', safe='/') + escape + 'name.png'
                    update('sys_config', 'utf8', config_value=html(encoded))
                    deny('malformed UTF8 reference cannot alias actual replacement file ' + label, key)
                    deny('malformed UTF8 reference cannot alias actual replacement file authenticated ' + label, key, 'student_a')
                update('sys_config', 'utf8', config_value='')

                # Owner and class permissions on registered raw keys are unchanged.
                owned, owned_bytes = fixture('owned/作者+作业.png')
                file_id = insert('sys_file', 'file', create_by='fixture_student_a', file_path=owned, file_name=Path(owned).name,
                                 file_location=1, file_type=2, del_flag=0)
                insert('teaching_work', 'work', user_id='fixture_student_a', depart_id='fixture_class_a', work_name='合成编码引用私有作品',
                       work_file=file_id, work_type=1, work_status=0, create_by='fixture_student_a', create_time='2026-10-03 00:00:00')
                for actor in (None, 'student_a', 'teacher_a', 'student_b', 'teacher_b', 'admin'):
                    if actor in ('student_a', 'teacher_a', 'admin'):
                        allow('raw registered key remains permitted ' + actor, owned, owned_bytes, actor)
                    else:
                        deny('raw registered key remains denied ' + str(actor), owned, actor)
                update('teaching_work', 'work', work_status=3)
                allow('published raw work key remains public', owned, owned_bytes)
                update('teaching_work', 'work', work_status=0)
                deny('withdrawn raw work key immediately denies anonymous Range', owned, headers={'Range': 'bytes=2-8'}, expected=401)
                sql('UPDATE sys_user SET status=2 WHERE id=' + literal('fixture_student_a'))
                deny('disabled account token cannot read encoded private unit', unit, 'student_a', expected=401)
                deny('disabled account cookie cannot read encoded private unit', unit, expected=401, headers={'Cookie': cookies['student_a']})
                sql('UPDATE sys_user SET status=1 WHERE id=' + literal('fixture_student_a'))
                allow('restored account token can read encoded private unit', unit, unit_bytes, 'student_a')
                old_token, old_cookie = api.tokens['student_a'], cookies['student_a']
                logout_status, logout, _ = api.request('GET', '/sys/logout', 'student_a')
                check('actual synthetic logout succeeds', logout_status == 200 and logout and logout.get('success') is True)
                deny('revoked token cannot read encoded private unit', unit, expected=401, headers={'X-Access-Token': old_token})
                deny('revoked cookie cannot read encoded private unit', unit, expected=401, headers={'Cookie': old_cookie, 'Range': 'bytes=2-8'})
            except Exception as error:
                fatal = type(error).__name__
                check('probe completes without execution error', False, error_type=fatal)
            finally:
                try:
                    api.close()
                except Exception as error:
                    cleanup_errors.append({'operation': 'fixture logout', 'error_type': type(error).__name__})
                for table in TABLES:
                    try:
                        sql('DELETE FROM `' + table + '` WHERE LEFT(id,' + str(len(prefix)) + ')=' + literal(prefix))
                    except Exception as error:
                        cleanup_errors.append({'operation': 'namespace cleanup ' + table, 'error_type': type(error).__name__})
                for row in original_users:
                    values = row.split('\t')[1:]
                    assignments = []
                    for column, value in zip(columns, values):
                        if column == 'id':
                            continue
                        value_sql = 'NULL' if value == '~' else ("''" if value == '' else 'CONVERT(0x' + value + ' USING utf8mb4)')
                        assignments.append('`' + column + '`=' + value_sql)
                    try:
                        sql('UPDATE sys_user SET ' + ','.join(assignments) + ' WHERE id=CONVERT(0x'
                            + values[columns.index('id')] + ' USING utf8mb4)')
                    except Exception as error:
                        cleanup_errors.append({'operation': 'full fixture user restore', 'error_type': type(error).__name__})
                if sandbox.is_symlink():
                    cleanup_errors.append({'operation': 'attachment cleanup', 'error_type': 'UnexpectedSymlink'})
                elif sandbox.exists():
                    shutil.rmtree(sandbox)
            after = database_inventory(runtime)
            files_after = helpers.attachment_inventory(uploads)
            changed = [table for table in before if table != 'sys_log' and before[table] != after.get(table)]
            check('every complete business row and table schema restored except sys_log', before.keys() == after.keys() and not changed,
                  changed_tables=changed, table_count=len(before))
            changed_files = sorted(path for path in set(files_before) | set(files_after) if files_before.get(path) != files_after.get(path))
            check('every attachment byte directory mode and link restored', not changed_files,
                  changed_paths=changed_files, original_entries=len(files_before))
            check('cleanup operations completed without error', not cleanup_errors, errors=cleanup_errors)
    finally:
        lock.unlink(missing_ok=True)
    report = {'observed_utc': datetime.now(timezone.utc).isoformat(), 'label': args.label,
              'jar_sha256': jar_sha256, 'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'scope': 'Actual loopback HTTP and isolated synthetic database; percent URL candidates, exact byte identity, current permissions and complete restoration. No browser, production, playable-video, performance or human-acceptance claim.',
              'reference_origin_from_runtime_config': reference_base,
              'expected_behavior_identical_before_after': True, 'passed': sum(case['passed'] for case in cases), 'total': len(cases),
              'cases': cases, 'observations': observations, 'error_type': fatal, 'cleanup_errors': cleanup_errors,
              'database_before': before, 'database_after': after,
              'attachments_before_sha256': hashlib.sha256(json.dumps(files_before, sort_keys=True).encode()).hexdigest(),
              'attachments_after_sha256': hashlib.sha256(json.dumps(files_after, sort_keys=True).encode()).hexdigest(),
              'coverage_boundary': 'Raw keys and configured-origin URI paths, quoted HTML src/href, ordinary JSON URL strings. Arbitrary HTML entities, JSON unicode escapes, frontend proxy and SQL-query performance are not asserted.'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    private_write(args.output, json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(str(report['passed']) + '/' + str(report['total']) + ' desired checks passed', flush=True)
    return report['passed'] == report['total']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--jar', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--label', choices=('baseline', 'candidate'), required=True)
    raise SystemExit(0 if verify(parser.parse_args()) else 1)
