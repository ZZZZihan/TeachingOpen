#!/usr/bin/env python3
"""Bounded anonymous GET checks on an owned private production-content copy.

No login, Redis access, writes, remote requests, student files, or raw response
logging. Output is a private aggregate report; errors are deliberately redacted.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import subprocess
from urllib.parse import quote, urlencode, unquote, urlsplit

from local_recovery import local_path, private_write, sha256
from local_runtime import assert_app_config, load_ports
from production_fixture import FORMAT, KIND, SCHEMA_PROFILE, ordinary_asset, read_private
from snapshot_backend import config_argument, process_identity, validate_jar


BUSINESS_TABLES = ('teaching_course', 'teaching_course_unit', 'teaching_course_dept',
                   'teaching_additional_work', 'teaching_student', 'teaching_work',
                   'teaching_work_correct')
HOME = '/teaching/teachingCourse/getHomeCourse'
# This existing endpoint filters show_home only. del_flag is compared with SQL
# as stored, including NULL; this verifier does not invent a deletion policy.
ELIGIBLE = 'show_home=1'
HEX64 = re.compile('[0-9a-f]{64}')
IDENTIFIER = re.compile('[A-Za-z][A-Za-z0-9_]*')


class SafeFailure(Exception):
    """Only fixed codes from this source may be written to the report."""


def sql(runtime, query):
    # SELECT-only input is not put into process arguments. A server-enforced
    # read-only transaction is used even though every statement is fixed here.
    if not query.startswith('SELECT ') or ';' in query:
        raise SafeFailure('query_not_read_only')
    client = runtime / 'tools/mysql-8.4.6-macos15-arm64/bin/mysql'
    config = runtime / 'config/snapshot-app-client.cnf'
    read_private(config)
    result = subprocess.run([str(client), '--defaults-extra-file=' + str(config),
                             '--batch', '--raw', '--skip-column-names', 'teachingopen_dev'],
                            input='START TRANSACTION READ ONLY;\n' + query + ';\nROLLBACK;\n',
                            text=True, capture_output=True, timeout=30)
    if result.returncode:
        # MySQL stderr can contain SQL fragments and retained content. Discard it.
        raise SafeFailure('read_only_sql_failed')
    return result.stdout.strip()


def guard(runtime, requested_jar=None):
    runtime = local_path(runtime)
    ports = load_ports(runtime)
    manifest = json.loads(read_private(runtime / 'snapshot-manifest.json'))
    if (manifest.get('format') != FORMAT or manifest.get('kind') != KIND
            or manifest.get('complete') is not True or manifest.get('runtime') != str(runtime)
            or manifest.get('datadir') != str(runtime / 'mysql-data')
            or manifest.get('ports') != ports or manifest.get('assets_verified') is not True
            or manifest.get('student_attachments') != 'withheld; not copied'
            or manifest.get('redis_sessions_restored') is not False):
        raise SafeFailure('snapshot_manifest_mismatch')
    for key in ('source_sha256', 'source_manifest_sha256', 'schema_policy_sha256'):
        if not isinstance(manifest.get(key), str) or not HEX64.fullmatch(manifest[key]):
            raise SafeFailure('source_binding_missing')
    if manifest['schema_policy_sha256'] != sha256(SCHEMA_PROFILE):
        raise SafeFailure('schema_policy_changed')
    for key in ('config/application-localtest.properties', 'config/snapshot-app-client.cnf',
                'assets-result.json'):
        read_private(runtime / key)
        if sha256(runtime / key) != manifest.get('private_files', {}).get(key):
            raise SafeFailure('bound_configuration_changed')
    assert_app_config(runtime)
    process = json.loads(read_private(runtime / 'backend-process.json'))
    jar = validate_jar(requested_jar or process['jar_path'], process['jar_sha256'])
    identity = process_identity(process['pid'])
    if (type(process.get('pid')) is not int or process['pid'] <= 1
            or process.get('profile') != 'dev,localtest'
            or process.get('config_argument') != config_argument(runtime)
            or process.get('snapshot_manifest_sha256') != sha256(runtime / 'snapshot-manifest.json')
            or str(jar) != process.get('jar_path') or identity != process.get('identity')
            or not identity or str(jar) not in identity
            or '--spring.profiles.active=dev,localtest' not in identity
            or config_argument(runtime) not in identity):
        raise SafeFailure('backend_identity_mismatch')
    listener = subprocess.run(['lsof', '-nP', '-a', '-p', str(process['pid']),
                               '-iTCP:' + str(ports['backend']), '-sTCP:LISTEN', '-Fn'],
                              capture_output=True, text=True, timeout=10)
    names = [line[1:] for line in listener.stdout.splitlines() if line.startswith('n')]
    if listener.returncode or names != ['127.0.0.1:' + str(ports['backend'])]:
        raise SafeFailure('backend_listener_not_owned_loopback')
    owner = sql(runtime, "SELECT CONCAT(@@datadir,'|',@@port)")
    if owner != str(runtime / 'mysql-data') + '/|' + str(ports['mysql']):
        raise SafeFailure('mysql_owner_mismatch')
    account = sql(runtime, "SELECT COUNT(*),COALESCE(SUM(username REGEXP '^snapshot_user_[0-9]{3}$' "
                  "AND id=username AND realname=username AND school='' AND avatar IS NULL "
                  "AND birthday IS NULL AND sex IS NULL AND email IS NULL AND phone IS NULL "
                  "AND third_id IS NULL AND third_type IS NULL AND work_no IS NULL AND post IS NULL "
                  "AND telephone IS NULL),0) FROM sys_user")
    if manifest.get('sanitization', {}).get('users') != 7 or account != '7\t7':
        raise SafeFailure('anonymous_account_shape_changed')
    return runtime, ports, manifest, process


def business_snapshot(runtime):
    # Hash on the SQL server: no retained text or file paths enter the report.
    snapshots = {}
    for table in BUSINESS_TABLES:
        columns = sql(runtime, "SELECT column_name FROM information_schema.columns "
                      "WHERE table_schema='teachingopen_dev' AND table_name='" + table
                      + "' ORDER BY ordinal_position").splitlines()
        if not columns or not all(IDENTIFIER.fullmatch(column) for column in columns):
            raise SafeFailure('business_schema_unexpected')
        parts = ["IF(`" + col + "` IS NULL,'N',CONCAT('V',HEX(`" + col + "`)))" for col in columns]
        rows = sql(runtime, "SELECT SHA2(CONCAT_WS('|'," + ','.join(parts) + "),256) FROM `" + table + '`').splitlines()
        if any(not HEX64.fullmatch(value) for value in rows):
            raise SafeFailure('business_digest_invalid')
        snapshots[table] = {'rows': len(rows), 'sha256': hashlib.sha256('\n'.join(sorted(rows)).encode()).hexdigest()}
    return snapshots


def request(port, path, params):
    if not path.startswith('/teaching/') or '?' in path or '://' in path:
        raise SafeFailure('request_route_not_allowed')
    connection = http.client.HTTPConnection('127.0.0.1', port, timeout=20)
    try:
        # No cookies, login credentials, token headers or redirect following.
        connection.request('GET', '/api' + path + '?' + urlencode(params), headers={'Accept': 'application/json'})
        response = connection.getresponse()
        content = response.read(8 * 1024 * 1024 + 1)
        if len(content) > 8 * 1024 * 1024:
            raise SafeFailure('response_exceeds_bound')
        try:
            payload = json.loads(content)
        except (ValueError, UnicodeError):
            payload = None
        return response.status, payload, response.getheader('Content-Type', '')
    finally:
        connection.close()


def page_result(status, body):
    if (status != 200 or not isinstance(body, dict) or body.get('success') is not True
            or not isinstance(body.get('result'), dict)):
        raise SafeFailure('home_response_not_successful')
    result = body['result']
    if (not isinstance(result.get('records'), list) or type(result.get('total')) is not int
            or result['total'] < 0 or any(not isinstance(row, dict) or not isinstance(row.get('id'), str)
                                       for row in result['records'])):
        raise SafeFailure('home_response_shape_invalid')
    return result


def course_rows(runtime, condition=ELIGIBLE):
    query = "SELECT JSON_OBJECT('id',id,'name',course_name,'type',course_type,'category',course_category," \
            "'cover',course_cover,'showHome',show_home,'delFlag',del_flag) FROM teaching_course WHERE " + condition + ' ORDER BY id'
    return [json.loads(line) for line in sql(runtime, query).splitlines()]


def cover_http_bytes(port, relative, expected_bytes):
    # relative has already passed ordinary_asset and course-manifest checks.
    # Direct HTTPConnection never follows redirects or uses browser cookies.
    ceiling = 16 * 1024 * 1024
    if type(expected_bytes) is not int or not 0 < expected_bytes <= ceiling:
        raise SafeFailure('cover_exceeds_http_byte_bound')
    connection = http.client.HTTPConnection('127.0.0.1', port, timeout=20)
    try:
        connection.request('GET', '/api/sys/common/static/' + quote(relative, safe='/'),
                           headers={'Accept': 'application/octet-stream'})
        response = connection.getresponse()
        # Read at most the manifest size plus one byte, and never print payloads
        # or Location headers. An HTTP redirect is a failure, not a next request.
        content = response.read(expected_bytes + 1)
        if response.status != 200 or len(content) != expected_bytes:
            raise SafeFailure('anonymous_cover_http_bytes_unexpected')
        return hashlib.sha256(content).hexdigest()
    finally:
        connection.close()


def local_covers(runtime, rows, port):
    assets = json.loads(read_private(runtime / 'assets-result.json'))
    verified, skipped = {}, 0
    for row in rows:
        raw = row.get('courseCover')
        if not raw:
            skipped += 1
            continue
        if not isinstance(raw, str) or ',' in raw:
            raise SafeFailure('cover_reference_shape_invalid')
        value = urlsplit(raw)
        path = unquote(value.path)
        marker = next((m for m in ('/sys/common/static/', '/upFiles/') if m in path), None)
        if marker:
            path = path.split(marker, 1)[1]
        elif value.scheme or value.netloc:
            skipped += 1
            continue  # Never contact an external resource.
        record = assets.get('files', {}).get(path)
        if not record:
            raise SafeFailure('cover_not_in_course_asset_manifest')
        if path in verified:
            continue
        asset = ordinary_asset(runtime / 'uploads', path)
        digest = sha256(asset)
        if asset.stat().st_size != record['bytes'] or digest != record['sha256']:
            raise SafeFailure('cover_bytes_differ_from_manifest')
        if cover_http_bytes(port, path, record['bytes']) != digest:
            raise SafeFailure('anonymous_cover_http_sha256_mismatch')
        verified[path] = digest
    return {'verified_unique_local_covers': len(verified), 'empty_or_external_references': skipped,
            'anonymous_http_covers_verified': len(verified), 'http_cover_byte_ceiling': 16 * 1024 * 1024,
            'content_set_sha256': hashlib.sha256('\n'.join(sorted(verified.values())).encode()).hexdigest()}


def verify(args):
    runtime = local_path(args.runtime)
    output = args.output.absolute()
    if output.parent != runtime or output.exists() or output.is_symlink():
        raise SafeFailure('output_requires_fresh_private_runtime_file')
    cases, metrics, before, after = [], {}, None, None
    report = {'observed_utc': datetime.now(timezone.utc).isoformat(), 'executed': False,
              'scope': 'Anonymous real loopback GET and read-only SQL on a private production-content copy; '
                       'no login, Redis access, student files, writes, browser acceptance or production delivery.',
              'cases': cases, 'metrics': metrics, 'http_requests_completed': 0,
              'limitations': ['Existing getHomeCourse filters show_home=1; del_flag equality is checked without adding a NULL/0 filter guarantee.',
                              'If no visible nonzero del_flag rows exist, deletion-state exclusion is not demonstrated.',
                              'Only copied course-cover assets are read; student files and external resources are not requested.']}
    def check(name, passed, **aggregate):
        cases.append({'case': name, 'passed': bool(passed), **aggregate})
    def call(route, params):
        result = request(ports['backend'], route, params)
        report['http_requests_completed'] += 1
        return result
    try:
        runtime, ports, manifest, process = guard(runtime, args.jar)
        report.update({'executed': True, 'owned_process_verified': True, 'backend_port': ports['backend'],
                       'jar_sha256': process['jar_sha256'], 'manifest_sha256': sha256(runtime / 'snapshot-manifest.json')})
        before = business_snapshot(runtime)
        expected = course_rows(runtime)
        counts = sql(runtime, 'SELECT COUNT(*),COALESCE(SUM(show_home=1),0),'
                     'COALESCE(SUM(show_home=1 AND del_flag=0),0),COALESCE(SUM(show_home=1 AND del_flag<>0),0),'
                     'COALESCE(SUM(show_home=1 AND del_flag IS NULL),0) FROM teaching_course').split('\t')
        metrics['course_visibility_counts'] = dict(zip(('all_courses', 'show_home', 'home_zero_delete_flag', 'home_nonzero_delete_flag', 'home_null_delete_flag'), map(int, counts)))
        bound = manifest['database']['teaching_course']['rows']
        if type(bound) is not int or not 1 <= bound <= 100 or len(expected) > bound:
            raise SafeFailure('course_snapshot_exceeds_bound')
        status, body, _ = call(HOME, {'pageNo': 1, 'pageSize': bound})
        page = page_result(status, body)
        records = page['records']
        expected_ids = {row['id'] for row in expected}
        actual_ids = {row['id'] for row in records}
        check('anonymous homepage matches existing SQL show_home contract',
              page['total'] == len(expected) and len(records) == len(expected) and actual_ids == expected_ids,
              http_status=status, sql_total=len(expected), api_total=page['total'])
        expected_by_id = {row['id']: row for row in expected}
        check('returned homepage showHome and delFlag equal stored SQL flags including NULL',
              all(row['id'] in expected_by_id and row.get('showHome') is True
                  and row.get('delFlag') == expected_by_id[row['id']]['delFlag'] for row in records), records=len(records))
        paged_ids = []
        paging_ok = True
        for number in range(1, max(1, (len(expected) + 1) // 2) + 1):
            status, body, _ = call(HOME, {'pageNo': number, 'pageSize': 2})
            small = page_result(status, body)
            paged_ids.extend(row['id'] for row in small['records'])
            paging_ok &= (small['total'] == len(expected) and small.get('current') == number
                          and small.get('size') == 2 and len(small['records']) <= 2)
        check('homepage page numbers and size preserve complete eligible set',
              paging_ok and len(paged_ids) == len(set(paged_ids)) == len(expected) and set(paged_ids) == expected_ids)
        status, body, _ = call(HOME, {'pageNo': bound + 1, 'pageSize': 2})
        far = page_result(status, body)
        check('beyond-last homepage page returns empty records with same total', not far['records'] and far['total'] == len(expected))
        if not expected:
            raise SafeFailure('visible_course_required_for_filter_checks')
        name = expected[0]['name']
        if not isinstance(name, str) or not name:
            raise SafeFailure('course_name_filter_unavailable')
        value = "CONVERT(UNHEX('" + name.encode().hex() + "') USING utf8mb4)"
        filtered = course_rows(runtime, ELIGIBLE + " AND course_name LIKE CONCAT('%'," + value + ",'%')")
        status, body, _ = call(HOME, {'courseName': name, 'pageNo': 1, 'pageSize': bound})
        found = page_result(status, body)
        check('homepage course-name filter matches SQL LIKE', found['total'] == len(filtered) and len(found['records']) == len(filtered)
              and {row['id'] for row in found['records']} == {row['id'] for row in filtered}, matches=found['total'])
        for api_field, sql_field, row_field in [('courseType', 'course_type', 'type'), ('courseCategory', 'course_category', 'category')]:
            selected = next((int(row[row_field]) for row in expected
                             if row[row_field] is not None and re.fullmatch('-?[0-9]+', str(row[row_field]))), None)
            has_reference = selected is not None
            # Nullable/legacy columns may have no typed visible example. A
            # fixed integer still checks parameter acceptance and SQL-equivalent
            # empty filtering; do not claim a positive match in that situation.
            if selected is None:
                selected = 1
            filtered = course_rows(runtime, ELIGIBLE + ' AND ' + sql_field + '=' + str(selected))
            status, body, _ = call(HOME, {api_field: selected, 'pageNo': 1, 'pageSize': bound})
            found = page_result(status, body)
            check('homepage ' + api_field + ' filter matches SQL', found['total'] == len(filtered) and len(found['records']) == len(filtered)
                  and {row['id'] for row in found['records']} == {row['id'] for row in filtered}, matches=found['total'],
                  reference_from_visible_course=has_reference)
        missing_name = 'snapshot_readonly_absent_' + report['manifest_sha256']
        status, body, _ = call(HOME, {'courseName': missing_name, 'pageSize': 2})
        empty = page_result(status, body)
        check('unmatched homepage name returns empty successful page', empty['total'] == 0 and empty['records'] == [])
        for label, route in [('course', '/teaching/teachingCourse/list'), ('unit', '/teaching/teachingCourseUnit/list')]:
            status, payload, kind = call(route, {'pageNo': 1, 'pageSize': 2})
            check('anonymous ' + label + ' management remains denied', status == 401 and kind.startswith('application/json')
                  and isinstance(payload, dict) and payload.get('success') is False and payload.get('code') == 401
                  and not payload.get('result'), http_status=status)
        metrics['home_cover_assets'] = local_covers(runtime, records, ports['backend'])
        check('anonymous homepage cover HTTP bytes match local copies and course asset manifest',
              metrics['home_cover_assets']['verified_unique_local_covers'] > 0, **metrics['home_cover_assets'])
        # Only identity/config checks and SELECTs are repeated. No baseline full
        # fixture verifier, Redis sessions or operational audit tables are read.
        guard(runtime, args.jar)
    except Exception as error:
        report['failure_code'] = str(error) if isinstance(error, SafeFailure) else 'redacted_' + type(error).__name__
    finally:
        if before is not None:
            try:
                after = business_snapshot(runtime)
                changed = [table for table in BUSINESS_TABLES if before[table] != after[table]]
                report['business_before'] = before
                report['business_after'] = after
                report['changed_business_tables'] = changed
                check('anonymous checks leave selected business rows unchanged', not changed)
            except Exception:
                report['business_after_unavailable'] = True
        report['passed'] = sum(case['passed'] for case in cases)
        report['total'] = len(cases)
        report['successful'] = bool(report['executed'] and cases and report['passed'] == report['total'] and not report.get('failure_code'))
        private_write(output, json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'executed': report['executed'], 'passed': report['passed'], 'total': report['total'],
                      'successful': report['successful'], 'failure_code': report.get('failure_code'),
                      'changed_business_tables': report.get('changed_business_tables')}))
    return 0 if report['successful'] else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True, help='Fresh aggregate JSON directly inside the private runtime')
    parser.add_argument('--jar', type=Path, help='Exact owned JAR; omitted means use bound backend-process metadata')
    try:
        raise SystemExit(verify(parser.parse_args()))
    except SafeFailure as error:
        print(json.dumps({'executed': False, 'successful': False, 'failure_code': str(error)}))
        raise SystemExit(1)
    except Exception as error:
        print(json.dumps({'executed': False, 'successful': False, 'failure_code': 'redacted_' + type(error).__name__}))
        raise SystemExit(1)
