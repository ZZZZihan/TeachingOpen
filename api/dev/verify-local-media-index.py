#!/usr/bin/env python3
"""M-06: transactional local-media candidates on an already running owned fixture.

Does not start an application, change global MySQL instrumentation, or connect to
production. Real HTTP bytes and EXPLAIN are checked; latency/capacity are not
inferred from these functional probes. SQL fixtures and cleanup use one random
namespace. --expect-legacy is a read-only packaged-code/schema comparison.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import html
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
from threading import Barrier
from time import perf_counter
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen
from uuid import uuid4
from zipfile import ZipFile

from local_http import FixtureApi
from local_runtime import mysql_command


SOURCE_TABLES = ('teaching_course', 'teaching_course_unit', 'teaching_additional_work',
                 'sys_config', 'teaching_news', 'sys_data_log')
BUSINESS_TABLES = SOURCE_TABLES + ('sys_file', 'teaching_work', 'teaching_course_dept')
INDEX = 'sys_local_file_reference'
STATE = 'sys_local_file_reference_state'
NEWS = '/teaching/teachingNews/'
REBUILD = '/sys/localMediaReferences/rebuild'
JAVA = 'api/jeecg-boot-module-system/src/main/java/org/jeecg/modules/system/service/'


def literal(value):
    if value is None:
        return 'NULL'
    return 'CONVERT(0x' + str(value).encode('utf-8').hex() + ' USING utf8mb4)' if str(value) else "''"


def digest(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def valid_storage_key(value):
    """Storage-key contract, applied to the independently constructed fixture references."""
    return bool(value) and len(value) <= 1024 and not value.startswith('/') \
        and '\\' not in value and ':' not in value and not any(ord(c) < 32 or ord(c) == 127 for c in value) \
        and all(part not in ('', '.', '..') for part in value.split('/'))


def one_table(plan):
    """Find EXPLAIN's single-table node without relying on pretty JSON layout."""
    if isinstance(plan, dict):
        if 'table' in plan:
            return plan['table']
        for value in plan.values():
            found = one_table(value)
            if found is not None:
                return found
    elif isinstance(plan, list):
        for value in plan:
            found = one_table(value)
            if found is not None:
                return found
    return None


def download_statement_counts(output):
    """Classify only the known download SELECT shapes from existing digest counters."""
    found = {}
    for line in output.splitlines():
        identity, text_hex, count, examined, sent = line.split('\t')
        text = bytes.fromhex(text_hex).decode('utf-8')
        normalized = re.sub(r'\s+', ' ', text.replace('`', '')).strip().upper()
        candidate = normalized == ('SELECT SOURCE_TYPE , SOURCE_ID , REFERENCE_VALUE FROM '
            'SYS_LOCAL_FILE_REFERENCE WHERE REFERENCE_KIND = ? AND REFERENCE_HASH = ?')
        # The tombstone-aware downloader reads deleted registrations too. Both
        # versions must retain the exact path/location filters; do not count OR,
        # partial filters, unions or arbitrary sys_file queries as bounded reads.
        registration = re.fullmatch(
            r'SELECT (?:\*|[A-Z_][A-Z0-9_]*(?: , [A-Z_][A-Z0-9_]*)*) FROM SYS_FILE '
            r'WHERE FILE_PATH = \? AND FILE_LOCATION = \?(?: AND DEL_FLAG = \?)?', normalized) is not None
        source = any(normalized.startswith('SELECT * FROM ' + table.upper() + ' WHERE ID IN (')
                     for table in SOURCE_TABLES)
        if candidate or registration or source:
            found[identity] = {'digest_text': text, 'category': 'candidate' if candidate else 'registration' if registration else 'source',
                              'count': int(count), 'rows_examined': int(examined), 'rows_sent': int(sent)}
    return found


def verify(args):
    if args.output.exists():
        raise RuntimeError('Existing probe evidence must be preserved')
    max_scale = getattr(args, 'max_unrelated_rows', 1000)
    if max_scale not in (1000, 10000):
        raise ValueError('Use exactly 1000 or 10000 unrelated fixture rows')
    root = Path(__file__).resolve().parents[2]
    jar = (args.jar or root / 'api/jeecg-boot-module-system/target/teaching-open-2.8.0.jar').resolve()
    nonce = uuid4().hex[:10]
    prefix = 'lmi_' + nonce + '_'
    directory = 'media-index-' + nonce
    trigger = prefix + 'insert_failure'
    cases, plans, observations, measurements = [], [], {}, []
    error = None
    snapshots = {}
    trigger_created = False
    cleanup_ready = False
    original = None

    def check(name, passed, fatal=True, **details):
        cases.append(dict(case=name, passed=bool(passed), **details))
        print(('PASS ' if passed else 'FAIL ') + name, flush=True)
        if not passed and fatal:
            raise AssertionError(name)

    with FixtureApi(args.runtime.resolve(), jar) as api:
        folder = api.runtime / 'uploads' / directory
        origin = 'http://127.0.0.1:' + str(api.ports['backend'])

        def sql(statement, timeout=90):
            result = subprocess.run(mysql_command(api.runtime) + ['--default-character-set=utf8mb4',
                '--batch', '--skip-column-names', '--raw', 'teachingopen_dev'],
                input=statement, capture_output=True, text=True, timeout=timeout)
            if result.returncode:
                # These statements contain only synthetic IDs/media, not credentials.
                raise RuntimeError('Synthetic media-index SQL failed: ' + result.stderr[:2500])
            return result.stdout.rstrip('\n')

        def owned(column='id'):
            return 'LEFT(BINARY `' + column + '`,' + str(len(prefix)) + ')=' + literal(prefix)

        def insert(table, **values):
            sql('INSERT INTO `' + table + '` (' + ','.join('`' + k + '`' for k in values)
                + ') VALUES (' + ','.join(literal(v) for v in values.values()) + ')')

        columns = {}

        def table_hash(table, where='1=1'):
            if table not in columns:
                columns[table] = sql('SELECT COLUMN_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() '
                    'AND TABLE_NAME=' + literal(table) + ' ORDER BY ORDINAL_POSITION').splitlines()
            names = columns[table]
            if not names or any(not re.fullmatch('[A-Za-z_][A-Za-z0-9_]*', name) for name in names):
                raise RuntimeError('Unexpected media fixture table columns')
            query = 'SELECT CONCAT_WS(\'|\',' + ','.join("IFNULL(HEX(`" + name + "`),'NULL')" for name in names)
            query += ') FROM `' + table + '` WHERE ' + where + ' ORDER BY ' + ','.join('`' + name + '`' for name in names)
            return hashlib.sha256(sql(query).encode()).hexdigest()

        def file_hashes():
            return {str(path.relative_to(api.runtime / 'uploads')): hashlib.sha256(path.read_bytes()).hexdigest()
                    for path in (api.runtime / 'uploads').rglob('*') if path.is_file()}

        def snapshot():
            return {'business': {table: table_hash(table) for table in BUSINESS_TABLES},
                    'index': table_hash(INDEX), 'state': table_hash(STATE), 'files': file_hashes()}

        def bytes_read(key, actor=None):
            headers = {'X-Access-Token': api.tokens[actor]} if actor else {}
            request = Request(origin + '/api/sys/common/static/' + quote(key, safe='/'), headers=headers)
            try:
                response = urlopen(request, timeout=20)
            except HTTPError as failure:
                response = failure
            with response:
                return response.status, response.read()

        def media(label, key, actor=None, permitted=True):
            expected = (api.runtime / 'uploads' / key).read_bytes()
            status, content = bytes_read(key, actor)
            check(label, status == 200 and content == expected if permitted
                  else status == (403 if actor else 401) and content != expected,
                  actor=actor, http_status=status, expected_bytes_sha256=hashlib.sha256(expected).hexdigest())

        def allowed(label, method, path, body=None):
            status, response, _ = api.request(method, path, 'admin', body)
            check(label, status == 200 and isinstance(response, dict) and response.get('success') is True)
            return response

        def rebuild(label):
            # Larger explicit backfills can legitimately exceed FixtureApi's 15s request timeout.
            request = Request(origin + '/api' + REBUILD, method='POST',
                              headers={'X-Access-Token': api.tokens['admin']})
            try:
                response = urlopen(request, timeout=180)
            except HTTPError as failure:
                response = failure
            with response:
                status, raw = response.status, response.read()
            try:
                payload = json.loads(raw)
            except ValueError:
                payload = None
            check(label, status == 200 and isinstance(payload, dict) and payload.get('success') is True
                  and type(payload.get('result')) is int and payload['result'] >= 0)
            return payload['result']

        def references(source_id, value, kind='key', source='teaching_news'):
            return int(sql('SELECT COUNT(*) FROM ' + INDEX + ' WHERE source_type=' + literal(source)
                + ' AND source_id=' + literal(source_id) + ' AND reference_kind=' + literal(kind)
                + ' AND reference_hash=' + literal(digest(value)) + ' AND BINARY reference_value=' + literal(value)))

        def content(source_id):
            value = sql('SELECT HEX(news_content) FROM teaching_news WHERE id=' + literal(source_id))
            return bytes.fromhex(value).decode('utf-8')

        def body(url, tag='media'):
            return '<p>' + tag + '</p><img src="' + html.escape(url, quote=True) + '">'

        def encoded(key):
            # Encode once, including ordinary ASCII characters; do not double decode.
            return domain.rstrip('/') + '/' + '/'.join(''.join('%%%02X' % b for b in part.encode())
                for part in key.split('/'))

        def known_file(name):
            path = folder / (name + '.txt')
            path.write_bytes(('synthetic local-media bytes: ' + name + '\n').encode())
            return directory + '/' + path.name

        def statement_counts():
            query = ('SELECT DIGEST,HEX(DIGEST_TEXT),COUNT_STAR,SUM_ROWS_EXAMINED,SUM_ROWS_SENT '
                'FROM performance_schema.events_statements_summary_by_digest WHERE SCHEMA_NAME=DATABASE() '
                "AND DIGEST_TEXT LIKE 'SELECT %'")
            return download_statement_counts(sql(query))

        def measure_reads(scale, label, key, permitted):
            # Warm-up is outside the 20 measured requests and statement-counter delta.
            status, payload = bytes_read(key)
            expected = (api.runtime / 'uploads' / key).read_bytes()
            check(str(scale) + ' bodies: ' + label + ' warm-up retains correct HTTP access',
                  status == (200 if permitted else 401) and (payload == expected) == permitted)
            available = observations['performance_schema']['available']
            before = statement_counts() if available else {}
            elapsed, responses_ok = [], True
            for _ in range(20):
                started = perf_counter()
                status, payload = bytes_read(key)
                elapsed.append((perf_counter() - started) * 1000)
                responses_ok &= status == (200 if permitted else 401) and (payload == expected) == permitted
            after = statement_counts() if available else {}
            check(str(scale) + ' bodies: ' + label + ' measured responses retain exact access', responses_ok)
            measurement = {'unrelated_bodies': scale, 'lookup': label, 'request_count': len(elapsed),
                'http_ms': elapsed, 'p95_ms': sorted(elapsed)[math.ceil(0.95 * len(elapsed)) - 1],
                'timing_scope': 'Local synthetic loopback, sequential requests, one warm-up; no load/throughput capacity claim'}
            measurements.append(measurement)
            if available:
                delta = []
                for identity in sorted(set(before) | set(after)):
                    end = after.get(identity, before[identity]) if identity in before else after[identity]
                    start = before.get(identity, dict(count=0, rows_examined=0, rows_sent=0))
                    item = {name: end[name] - start[name] for name in ('count', 'rows_examined', 'rows_sent')}
                    item.update(digest=identity, digest_text=end['digest_text'], category=end['category'])
                    if any(item[name] for name in ('count', 'rows_examined', 'rows_sent')):
                        delta.append(item)
                totals = {name: sum(item[name] for item in delta) for name in ('count', 'rows_examined', 'rows_sent')}
                candidates = [item for item in delta if item['category'] == 'candidate']
                measurement['download_select_digest_deltas'] = delta
                measurement['download_select_totals'] = totals
                check(str(scale) + ' bodies: ' + label + ' has one indexed candidate query per request',
                    len(candidates) == 1 and candidates[0]['count'] == 20
                    and candidates[0]['rows_examined'] == (20 if permitted else 0)
                    and candidates[0]['rows_sent'] == (20 if permitted else 0), candidate_digest_deltas=candidates)
                check(str(scale) + ' bodies: ' + label + ' download SQL and examined rows stay bounded',
                    totals['count'] == (60 if permitted else 40)
                    and totals['rows_examined'] == (40 if permitted else 0)
                    and totals['rows_sent'] == (40 if permitted else 0), download_select_totals=totals)
            else:
                measurement['statement_counts'] = 'Unavailable without changing runtime instrumentation; EXPLAIN evidence retained'

        try:
            with ZipFile(jar) as archive:
                download_class = archive.read('BOOT-INF/classes/org/jeecg/modules/system/service/LocalDownloadAccessService.class')
                indexed_class_exists = 'BOOT-INF/classes/org/jeecg/modules/system/service/LocalMediaReferenceIndex.class' in archive.namelist()
                index_class = archive.read('BOOT-INF/classes/org/jeecg/modules/system/service/LocalMediaReferenceIndex.class') if indexed_class_exists else b''
            observations['packaged_download_class_sha256'] = hashlib.sha256(download_class).hexdigest()
            observations['packaged_index_class_sha256'] = hashlib.sha256(index_class).hexdigest() if indexed_class_exists else None
            if args.expect_legacy:
                check('legacy packaged downloader contains the old LOCATE scan', b'LOCATE(' in download_class)
                check('legacy packaged candidate has no local-media reference index class', not indexed_class_exists)
                observations['legacy_scope'] = 'Read-only packaged-code comparison; no behavioral or throughput claim'
            else:
                check('running candidate packages the local-media index implementation', indexed_class_exists)
                check('packaged downloader contains no old LOCATE query', b'LOCATE(' not in download_class)
                check('packaged index candidates use equality on reference hash', b'reference_hash=?' in index_class)
                for name in ('LocalDownloadAccessService.java', 'LocalMediaReferenceIndex.java'):
                    path = root / JAVA / name
                    source = path.read_text()
                    observations.setdefault('source_sha256', {})[str(path.relative_to(root))] = digest(source)
                    hot = source if name.startswith('LocalDownload') else source[source.index('public Map<LocalMediaSource'):source.index('public static String hash')]
                    check(name + ' hot path has no LOCATE or CONCAT body scan', not re.search(r'(?i)\b(?:LOCATE|CONCAT(?:_WS)?)\s*\(', hot))
                check('new reference and state tables exist', sql('SELECT COUNT(*) FROM information_schema.TABLES '
                    'WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME IN (' + literal(INDEX) + ',' + literal(STATE) + ')') == '2')
                check('startup index is initialized at version one', sql('SELECT version FROM ' + STATE + ' WHERE id=1') == '1')
                domain = sql('SELECT static_domain FROM ' + STATE + ' WHERE id=1')
                check('startup state stores a nonempty static domain', bool(domain) and domain != 'NULL')
                for table in BUSINESS_TABLES:
                    check('fixture namespace absent in ' + table, sql('SELECT COUNT(*) FROM `' + table + '` WHERE ' + owned()) == '0')
                check('fixture namespace absent from reference index', sql('SELECT COUNT(*) FROM ' + INDEX + ' WHERE ' + owned('source_id')) == '0')
                check('random probe trigger does not exist', sql('SELECT COUNT(*) FROM information_schema.TRIGGERS '
                    'WHERE TRIGGER_SCHEMA=DATABASE() AND TRIGGER_NAME=' + literal(trigger)) == '0')
                check('random probe directory does not exist', not folder.exists())
                original = snapshot()
                snapshots['before'] = original
                cleanup_ready = True
                for actor in ('admin', 'student_a', 'student_b', 'teacher_a', 'teacher_b'):
                    api.login(actor)
                performance_enabled = sql('SELECT @@performance_schema') == '1'
                digest_enabled = sql("SELECT ENABLED FROM performance_schema.setup_consumers WHERE NAME='statements_digest'") == 'YES' if performance_enabled else False
                observations['performance_schema'] = {'available': performance_enabled and digest_enabled,
                    'performance_schema_enabled': performance_enabled, 'statements_digest_enabled': digest_enabled,
                    'scope': 'Read-only existing statement digest counters; no reset, consumer change, global log or instrumentation change'}
                folder.mkdir()
                keys = {name: known_file(name) for name in ('live', 'replacement', 'unknown', 'legacy',
                    'course', 'unit', 'assignment', 'config', 'draft', 'history', 'race-a', 'race-b', 'fault')}
                for actor in (None, 'student_a', 'teacher_a'):
                    before = snapshot()
                    status, response, _ = api.request('POST', REBUILD, actor)
                    check(str(actor) + ' cannot rebuild', status == (401 if actor is None else 200)
                          and isinstance(response, dict) and response.get('success') is False
                          and response.get('code') == (401 if actor is None else 510))
                    check(str(actor) + ' denied rebuild preserves business index state and files', snapshot() == before)

                live_id = prefix + 'live'
                live_url = domain.rstrip('/') + '/' + keys['live']
                allowed('ordinary news add succeeds', 'POST', NEWS + 'add',
                    {'id': live_id, 'newsTitle': prefix + 'live', 'newsStatus': 1, 'newsContent': body(live_url)})
                check('ordinary add indexes the canonical local key', references(live_id, keys['live']) == 1)
                media('ordinary added media returns exact public HTTP bytes', keys['live'])
                saved_content, saved_refs = content(live_id), table_hash(INDEX, 'source_id=' + literal(live_id))
                allowed('title-only partial news edit succeeds', 'PUT', NEWS + 'edit', {'id': live_id, 'newsTitle': prefix + 'renamed'})
                check('partial edit retains authoritative body and its index', content(live_id) == saved_content
                      and table_hash(INDEX, 'source_id=' + literal(live_id)) == saved_refs)
                replace_url = encoded(keys['replacement'])
                allowed('media replacement edit succeeds', 'PUT', NEWS + 'edit', {'id': live_id, 'newsContent': body(replace_url)})
                check('replacement removes old key and indexes once-decoded new key', references(live_id, keys['live']) == 0
                      and references(live_id, keys['replacement']) == 1)
                media('removed media is denied while original bytes still exist', keys['live'], permitted=False)
                media('encoded replacement returns exact public HTTP bytes', keys['replacement'])
                # Direct fixture changes deliberately keep an old candidate: the index must not authorize it.
                sql('UPDATE teaching_news SET news_status=0 WHERE id=' + literal(live_id))
                check('withdrawn media still has an index candidate', references(live_id, keys['replacement']) == 1)
                media('indexed draft is not public', keys['replacement'], permitted=False)
                media('indexed draft remains forbidden to a student', keys['replacement'], 'student_a', False)
                sql('UPDATE teaching_news SET news_status=1,news_content=' + literal('<p>reference removed</p>') + ' WHERE id=' + literal(live_id))
                check('stale candidate exists after deliberate out-of-band fixture edit', references(live_id, keys['replacement']) == 1)
                media('stale index hit cannot authorize bytes absent from current body', keys['replacement'], permitted=False)
                allowed('ordinary delete succeeds', 'DELETE', NEWS + 'delete?id=' + live_id)
                check('ordinary deletion removes source and all its reference rows', sql('SELECT COUNT(*) FROM teaching_news WHERE id=' + literal(live_id)) == '0'
                      and sql('SELECT COUNT(*) FROM ' + INDEX + ' WHERE source_id=' + literal(live_id)) == '0')

                # Import-like historical rows have no file registration; explicit rebuild indexes them.
                insert('teaching_news', id=prefix + 'legacy', news_title=prefix + 'legacy', news_status=1,
                       news_content='<img src="' + encoded(keys['legacy']) + '">')
                insert('teaching_course', id=prefix + 'course', course_name=prefix + 'course', del_flag=0,
                       show_home=1, course_cover=keys['course'], course_desc='<p>Unrelated legacy prose</p>')
                insert('teaching_course', id=prefix + 'private_course', course_name=prefix + 'private', del_flag=0,
                       show_home=0, is_shared=0)
                insert('teaching_course_unit', id=prefix + 'unit', unit_name=prefix + 'unit', del_flag=0,
                       course_id=prefix + 'private_course', media_content=json.dumps({'nested': [{'src': encoded(keys['unit'])}]}))
                insert('teaching_additional_work', id=prefix + 'assignment', work_name=prefix + 'assignment',
                       work_dept='fixture_class_a', status=1, work_desc=json.dumps({'nested': [{'src': encoded(keys['assignment'])}]}))
                insert('sys_config', id=prefix + 'config', config_key=prefix + 'media', config_enabled=1,
                       config_value='<img src="' + domain.rstrip('/') + '/' + keys['config'].replace('.', '&#46;') + '">')
                insert('teaching_news', id=prefix + 'draft', news_title=prefix + 'draft', news_status=0,
                       news_content='<img src="' + encoded(keys['draft']) + '">')
                insert('sys_file', id=prefix + 'history_file', file_name='history.txt', file_path=keys['history'],
                       file_location=1, del_flag=0, create_by='fixture_student_b')
                insert('teaching_work', id=prefix + 'work', work_name=prefix + 'history', user_id='fixture_student_a',
                       depart_id='fixture_class_a', work_type='2', work_file='', work_status=0, del_flag=0,
                       create_by='fixture_student_a', create_time='2026-10-11 00:00:00')
                insert('sys_data_log', id=prefix + 'history', data_table='teaching_work', data_id=prefix + 'work',
                       data_content=json.dumps({'workFile': prefix + 'history_file'}), data_version=0)
                check('legacy media keys have no sys_file record', sql('SELECT COUNT(*) FROM sys_file WHERE '
                    'file_path IN (' + ','.join(literal(keys[name]) for name in ('legacy', 'course', 'unit', 'assignment', 'config')) + ')') == '0')
                media('direct historical import is unavailable before explicit rebuild', keys['legacy'], permitted=False)
                rebuild('admin explicitly rebuilds imported media references')
                for source in SOURCE_TABLES:
                    check('rebuild indexes fixture source ' + source, int(sql('SELECT COUNT(*) FROM ' + INDEX
                        + ' WHERE source_type=' + literal(source) + ' AND ' + owned('source_id'))) > 0)
                media('legacy imported encoded HTML returns exact bytes after rebuild', keys['legacy'])
                media('legacy bare storage key returns exact bytes after rebuild', keys['course'])
                media('HTML entity reference returns exact bytes after rebuild', keys['config'])
                media('nested JSON assignment reference obeys member access', keys['assignment'], 'student_a')
                media('nested JSON assignment reference rejects another class', keys['assignment'], 'student_b', False)
                media('indexed unit does not confer course permission', keys['unit'], 'student_a', False)
                media('indexed draft remains private after rebuild', keys['draft'], permitted=False)
                check('history reference is indexed as file identity', references(prefix + 'history', prefix + 'history_file', 'file', 'sys_data_log') == 1)
                media('indexed work history authorizes its owner', keys['history'], 'student_a')
                media('indexed work history rejects cross-class teacher', keys['history'], 'teacher_b', False)
                media('unknown existing bytes remain forbidden anonymously', keys['unknown'], permitted=False)
                media('unknown existing bytes remain forbidden to a student', keys['unknown'], 'student_a', False)
                # An exact hash/key candidate with an unrelated current body still grants nothing.
                insert(INDEX, source_type='teaching_news', source_id=prefix + 'legacy', field_name='news_content',
                       reference_kind='key', reference_hash=digest(keys['unknown']), reference_value=keys['unknown'])
                media('forged exact index candidate cannot replace authoritative body', keys['unknown'], permitted=False)
                sql('DELETE FROM ' + INDEX + ' WHERE source_type=\'teaching_news\' AND source_id=' + literal(prefix + 'legacy')
                    + ' AND reference_hash=' + literal(digest(keys['unknown'])))

                fault_id, edit_id = prefix + 'fault_new', prefix + 'fault_edit'
                fault_payload = {'id': fault_id, 'newsTitle': prefix + 'fault', 'newsStatus': 1,
                                 'newsContent': body(encoded(keys['fault']), 'fault')}
                allowed('fault-edit positive fixture add succeeds', 'POST', NEWS + 'add',
                    {'id': edit_id, 'newsTitle': prefix + 'faultedit', 'newsStatus': 1, 'newsContent': body(encoded(keys['live']))})
                sql('DELIMITER //\nCREATE TRIGGER `' + trigger + '` BEFORE INSERT ON ' + INDEX + ' FOR EACH ROW BEGIN '
                    'IF NEW.source_type=\'teaching_news\' AND NEW.source_id IN (' + literal(fault_id) + ',' + literal(edit_id) + ') '
                    "THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='synthetic local media index insertion failure'; END IF; END//\nDELIMITER ;\n")
                trigger_created = True
                before = snapshot()
                try:
                    insert(INDEX, source_type='teaching_news', source_id=fault_id, field_name='news_content',
                           reference_kind='key', reference_hash=digest(keys['fault']), reference_value=keys['fault'])
                except RuntimeError as failure:
                    check('owned insertion-fault trigger really fires', 'synthetic local media index insertion failure' in str(failure))
                else:
                    check('owned insertion-fault trigger really fires', False)
                check('direct trigger proof leaves all persisted state unchanged', snapshot() == before)
                edit_payload = {'id': edit_id, 'newsContent': body(encoded(keys['fault']), 'failed edit')}
                for label, method, payload in (('add', 'POST', fault_payload), ('edit', 'PUT', edit_payload)):
                    before = snapshot()
                    status, response, _ = api.request(method, NEWS + label, 'admin', payload)
                    check('index insertion fault rejects ordinary news ' + label, status in (200, 500)
                          and isinstance(response, dict) and response.get('success') is False)
                    check('index insertion fault rolls back body index state and bytes for ' + label, snapshot() == before)
                sql('DROP TRIGGER `' + trigger + '`')
                trigger_created = False
                allowed('same ordinary add recovers after injected fault removal', 'POST', NEWS + 'add', fault_payload)
                allowed('same ordinary edit recovers after injected fault removal', 'PUT', NEWS + 'edit', edit_payload)
                check('recovered writes persist exact new canonical references', references(fault_id, keys['fault']) == 1
                      and references(edit_id, keys['fault']) == 1 and references(edit_id, keys['live']) == 0)

                race_id = prefix + 'race'
                allowed('concurrent update fixture created through business API', 'POST', NEWS + 'add',
                    {'id': race_id, 'newsTitle': prefix + 'race', 'newsStatus': 1, 'newsContent': body(encoded(keys['live']))})
                barrier = Barrier(2)
                payloads = [{'id': race_id, 'newsContent': body(encoded(keys[name]), name)} for name in ('race-a', 'race-b')]
                def update(payload):
                    barrier.wait(timeout=20)
                    return api.request('PUT', NEWS + 'edit', 'admin', payload)
                with ThreadPoolExecutor(max_workers=2) as workers:
                    replies = list(workers.map(update, payloads))
                check('two concurrent HTTP transaction updates both commit', all(status == 200 and isinstance(reply, dict)
                    and reply.get('success') is True for status, reply, _ in replies))
                persisted = content(race_id)
                urls = [html.unescape(match) for match in re.findall(r'src="([^"]+)"', persisted)]
                check('concurrent final body contains exactly one known race URL', len(urls) == 1
                      and urls[0] in [encoded(keys[name]) for name in ('race-a', 'race-b')])
                final_key = next(keys[name] for name in ('race-a', 'race-b') if encoded(keys[name]) == urls[0])
                actual_pairs = [line.split('\t') for line in sql('SELECT HEX(reference_value),reference_hash FROM '
                    + INDEX + ' WHERE source_type=\'teaching_news\' AND source_id=' + literal(race_id)).splitlines()]
                actual_values = {bytes.fromhex(value).decode('utf-8') for value, _ in actual_pairs}
                expected_values = {value for value in (persisted, urls[0], final_key) if valid_storage_key(value)}
                check('concurrent final index exactly matches authoritative persisted body', actual_values == expected_values,
                      actual_reference_values=sorted(actual_values), expected_reference_values=sorted(expected_values),
                      expectation_basis='Only one independently extracted src and its once-decoded fixture key, plus raw body if storage-key contract accepts it')
                check('concurrent reference hashes match every exact persisted reference value',
                      all(digest(bytes.fromhex(value).decode('utf-8')) == hashed for value, hashed in actual_pairs))
                check('concurrent old and losing local keys are absent', references(race_id, keys['live']) == 0
                      and all(references(race_id, keys[name]) == (1 if keys[name] == final_key else 0) for name in ('race-a', 'race-b')))
                media('concurrent winning body returns exact bytes', final_key)

                # Distinct unrelated URLs create a real large candidate index; no FORCE INDEX or latency threshold.
                count = 0
                for scale in (10, 1000) if max_scale == 1000 else (10, 1000, 10000):
                    while count < scale:
                        end = min(count + 200, scale)
                        values = []
                        for index in range(count, end):
                            ident = prefix + 'noise_' + str(index).zfill(5)
                            text = body(domain.rstrip('/') + '/' + directory + '/noise/' + str(index) + '.txt', 'unrelated ' + str(index))
                            values.append('(' + ','.join(literal(value) for value in (ident, ident, text, 1)) + ')')
                        sql('INSERT INTO teaching_news (id,news_title,news_content,news_status) VALUES ' + ','.join(values))
                        count = end
                    rebuild('explicit rebuild with ' + str(scale) + ' unrelated bodies succeeds')
                    check('scale fixture bodies and indexed candidates are present ' + str(scale),
                        sql('SELECT COUNT(*) FROM teaching_news WHERE ' + owned() + ' AND news_title LIKE ' + literal(prefix + 'noise_%')) == str(scale)
                        and int(sql('SELECT COUNT(*) FROM ' + INDEX + ' WHERE ' + owned('source_id'))) >= scale)
                    for label, value in (('unknown', keys['unknown']), ('one legacy hit', keys['legacy'])):
                        # hash() returns ASCII hex. A normal literal has the same coercibility as the
                        # JDBC bound string; CONVERT(... USING utf8mb4) would coerce the ASCII index column.
                        query = 'SELECT source_type,source_id,reference_value FROM ' + INDEX + " WHERE reference_kind='key' AND reference_hash='" + digest(value) + "'"
                        plan = json.loads(sql('EXPLAIN FORMAT=JSON ' + query))
                        table = one_table(plan)
                        plans.append({'unrelated_bodies': scale, 'lookup': label, 'explain': plan,
                                      'actual_matching_rows': int(sql('SELECT COUNT(*) FROM (' + query + ') probe_lookup'))})
                        check(str(scale) + ' bodies: ' + label + ' uses natural indexed equality', isinstance(table, dict)
                              and table.get('key') == 'idx_local_reference_lookup' and table.get('access_type') == 'ref'
                              and table.get('used_key_parts') == ['reference_kind', 'reference_hash']
                              and table.get('rows_examined_per_scan', scale) <= 2, explain=plan)
                    media(str(scale) + ' unrelated bodies do not expose unknown existing bytes', keys['unknown'], permitted=False)
                    media(str(scale) + ' unrelated bodies retain exact legacy access', keys['legacy'])
                    measure_reads(scale, 'anonymous unknown', keys['unknown'], False)
                    measure_reads(scale, 'anonymous one legacy hit', keys['legacy'], True)
                observations['scaling_scope'] = 'EXPLAIN equality/rows, existing statement digest deltas, and sequential local synthetic HTTP p95; no load/throughput capacity claim'
                observations['unrelated_rows'] = max_scale
                snapshots['with_fixtures'] = snapshot()
        except Exception as failure:
            error = type(failure).__name__ + ': ' + str(failure)
            if not cases or cases[-1]['passed']:
                check('probe completed without unexpected exception', False, fatal=False, exception=error)
        finally:
            if cleanup_ready:
                try:
                    if trigger_created:
                        sql('DROP TRIGGER `' + trigger + '`')
                        trigger_created = False
                    # No global rebuild/restore or deletion of another probe's data.
                    for table in BUSINESS_TABLES:
                        sql('DELETE FROM `' + table + '` WHERE ' + owned())
                    sql('DELETE FROM ' + INDEX + ' WHERE ' + owned('source_id'))
                    if folder.exists():
                        shutil.rmtree(folder)
                    final = snapshot()
                    snapshots['after_cleanup'] = final
                    check('original source and business rows restored exactly', final['business'] == original['business'], fatal=False)
                    check('original index rows restored exactly', final['index'] == original['index'], fatal=False)
                    check('index initialization state unchanged', final['state'] == original['state'], fatal=False)
                    check('original file bytes restored exactly', final['files'] == original['files'], fatal=False)
                    check('owned injection trigger removed', sql('SELECT COUNT(*) FROM information_schema.TRIGGERS '
                        'WHERE TRIGGER_SCHEMA=DATABASE() AND TRIGGER_NAME=' + literal(trigger)) == '0', fatal=False)
                except Exception as failure:
                    cleanup_error = type(failure).__name__ + ': ' + str(failure)
                    error = (error + '; ' if error else '') + 'cleanup: ' + cleanup_error
                    check('namespace cleanup completed', False, fatal=False, exception=cleanup_error)
        result = {'scope': 'Owned synthetic real HTTP/MySQL local-media CRUD, rebuild, rollback, concurrency and query plans',
                  'production_connected': False, 'expected_legacy': args.expect_legacy,
                  'jar_sha256': api.jar_sha256, 'verifier_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  'passed': sum(case['passed'] for case in cases), 'failed': sum(not case['passed'] for case in cases),
                  'total': len(cases), 'cases': cases, 'exception': error, 'observations': observations,
                  'query_plans': plans, 'http_measurements': measurements, 'snapshots': snapshots, 'fixture_namespace': prefix,
                  'created_at': datetime.now(timezone.utc).isoformat()}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(str(result['passed']) + '/' + str(result['total']) + ' checks passed')
    return error is None and result['failed'] == 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--jar', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--expect-legacy', action='store_true')
    parser.add_argument('--max-unrelated-rows', type=int, choices=(1000, 10000), default=1000,
                        help='Default bounded CI probe: 10/1000; use 10000 for the additional 10000-body stage')
    raise SystemExit(0 if verify(parser.parse_args()) else 1)
