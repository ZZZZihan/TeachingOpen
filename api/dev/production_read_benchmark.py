"""Bounded loopback reads, SQL-derived semantics and private aggregate evidence.

The existing production-content verifier owns environment guards and SELECT-only
SQL. This module never operates services, logs in, follows redirects, accesses
Redis, or reads protected course/unit/student resources.
"""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import http.client
import importlib.util
import json
import math
import os
from pathlib import Path
import platform
import re
import stat
import statistics
import subprocess
import time
from urllib.parse import quote, unquote, urlencode, urlsplit


HERE = Path(__file__).resolve().parent
ROUNDS, WORKERS, SAMPLES, WARMUP = 3, (1, 4), 24, 3
TIMEOUT, MAX_RUN_SECONDS = 5, 300
MAX_JSON_BYTES, MAX_COVER_BYTES, RANGE_BYTES = 8 * 1024 * 1024, 16 * 1024 * 1024, 4096
MAX_COURSES, MAX_ASSETS = 100, 4096
HOME = '/api/teaching/teachingCourse/getHomeCourse'
LABELS = ('home_full', 'home_first_page', 'home_second_page', 'home_name_filter',
          'cover_get', 'cover_head', 'cover_range')
HEX64 = re.compile('[0-9a-f]{64}')


class BenchmarkFailure(Exception):
    """Only fixed source-defined codes may be reported, never exception text."""


def load_verifier():
    spec = importlib.util.spec_from_file_location('production_content_guard', HERE / 'verify-production-content.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@dataclass(frozen=True)
class Scenario:
    # Targets, expected rows and assets remain in memory, never in the report.
    label: str
    method: str
    target: str
    expected_rows: tuple = ()
    total: int = None
    current: int = None
    size: int = None
    exact_set: bool = True
    asset_bytes: int = None
    digest: str = None
    range_end: int = None
    prefix_digest: str = None
    content_type: str = None


def home_scenario(label, rows, total, current, size, params=None, exact_set=True):
    query = {'pageNo': current, 'pageSize': size, **(params or {})}
    return Scenario(label, 'GET', HOME + '?' + urlencode(query), tuple(rows), total, current, size, exact_set)


def asset_snapshot(runtime, assets, v):
    """Stat copied course files without hashing the multi-gigabyte collection."""
    records = assets.get('files')
    if not isinstance(records, dict) or not 1 <= len(records) <= MAX_ASSETS:
        raise BenchmarkFailure('asset_manifest_shape_invalid')
    inventory, total = {}, 0
    for relative, record in sorted(records.items()):
        if (not isinstance(relative, str) or not isinstance(record, dict)
                or type(record.get('bytes')) is not int or record['bytes'] < 0
                or not isinstance(record.get('sha256'), str) or not HEX64.fullmatch(record['sha256'])):
            raise BenchmarkFailure('asset_manifest_shape_invalid')
        asset = v.ordinary_asset(runtime / 'uploads', relative)
        info = asset.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_size != record['bytes']:
            raise BenchmarkFailure('asset_metadata_manifest_mismatch')
        inventory[relative] = [info.st_size, info.st_mtime_ns, info.st_mode, info.st_ino]
        total += info.st_size
    seen = set()
    for directory, dirs, files in os.walk(runtime / 'uploads', followlinks=False):
        for name in dirs + files:
            item = Path(directory) / name
            mode = item.lstat().st_mode
            if stat.S_ISLNK(mode) or not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
                raise BenchmarkFailure('asset_metadata_unsafe_file')
            if stat.S_ISREG(mode):
                seen.add(item.relative_to(runtime / 'uploads').as_posix())
            if len(seen) > MAX_ASSETS:
                raise BenchmarkFailure('asset_metadata_exceeds_bound')
    if seen != set(records) or assets.get('count') != len(records) or assets.get('bytes') != total:
        raise BenchmarkFailure('asset_metadata_manifest_mismatch')
    digest = hashlib.sha256(json.dumps(inventory, ensure_ascii=True, sort_keys=True).encode()).hexdigest()
    return {'files': len(records), 'bytes': total, 'metadata_sha256': digest,
            'full_collection_content_rehashed': False}


def selected_cover_snapshot(runtime, selected, v):
    asset = v.ordinary_asset(runtime / 'uploads', selected['path'])
    size = asset.stat().st_size
    if type(selected.get('bytes')) is not int or not 0 < size == selected['bytes'] <= MAX_COVER_BYTES:
        raise BenchmarkFailure('selected_cover_manifest_mismatch')
    with asset.open('rb') as source:
        content = source.read(size + 1)
    if len(content) != size or asset.stat().st_size != size:
        raise BenchmarkFailure('selected_cover_manifest_mismatch')
    observed = {'bytes': size, 'sha256': hashlib.sha256(content).hexdigest()}
    if observed != {key: selected[key] for key in ('bytes', 'sha256')}:
        raise BenchmarkFailure('selected_cover_manifest_mismatch')
    return observed


def select_cover(runtime, rows, assets, v):
    image_types = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
                   '.gif': 'image/gif', '.webp': 'image/webp'}
    for row in rows:
        raw = row.get('cover')
        if not raw:
            continue
        if not isinstance(raw, str) or ',' in raw:
            raise BenchmarkFailure('cover_reference_shape_invalid')
        parsed = urlsplit(raw)
        path = unquote(parsed.path)
        marker = next((m for m in ('/sys/common/static/', '/upFiles/') if m in path), None)
        if marker:
            path = path.split(marker, 1)[1]
        elif parsed.scheme or parsed.netloc:
            continue  # A remote URL never becomes a request target.
        if parsed.query or parsed.fragment:
            raise BenchmarkFailure('cover_reference_shape_invalid')
        record = assets['files'].get(path)
        content_type = image_types.get(Path(path).suffix.lower())
        if (not isinstance(record, dict) or content_type is None
                or type(record.get('bytes')) is not int or not 0 < record['bytes'] <= MAX_COVER_BYTES):
            continue
        selected = {'path': path, 'bytes': record['bytes'], 'sha256': record['sha256']}
        selected_cover_snapshot(runtime, selected, v)
        asset = v.ordinary_asset(runtime / 'uploads', path)
        with asset.open('rb') as source:
            prefix = source.read(min(RANGE_BYTES, selected['bytes']))
        selected.update({'prefix_sha256': hashlib.sha256(prefix).hexdigest(), 'content_type': content_type})
        return selected
    raise BenchmarkFailure('eligible_bounded_public_cover_required')


def build_scenarios(runtime, manifest, v):
    database = manifest.get('database', {})
    bound = database.get('teaching_course', {}).get('rows')
    if type(bound) is not int or not 1 <= bound <= MAX_COURSES:
        raise BenchmarkFailure('course_snapshot_exceeds_bound')
    rows = v.course_rows(runtime)
    if not 1 <= len(rows) <= bound or len({row['id'] for row in rows}) != len(rows):
        raise BenchmarkFailure('eligible_home_rows_invalid')
    name = next((row['name'] for row in rows if isinstance(row.get('name'), str) and row['name'].strip()), None)
    if name is None or len(name.encode()) > 1024:
        raise BenchmarkFailure('positive_name_filter_unavailable')
    value = "CONVERT(UNHEX('" + name.encode().hex() + "') USING utf8mb4)"
    filtered = v.course_rows(runtime, v.ELIGIBLE + " AND course_name LIKE CONCAT('%'," + value + ",'%')")
    if not filtered or not {row['id'] for row in filtered} <= {row['id'] for row in rows}:
        raise BenchmarkFailure('positive_name_filter_sql_invalid')
    assets = json.loads(v.read_private(runtime / 'assets-result.json'))
    selected = select_cover(runtime, rows, assets, v)
    target = '/api/sys/common/static/' + quote(selected['path'], safe='/')
    scenarios = [home_scenario('home_full', rows, len(rows), 1, bound),
                 home_scenario('home_first_page', rows, len(rows), 1, 2, exact_set=False),
                 home_scenario('home_second_page', rows, len(rows), 2, 2, exact_set=False),
                 home_scenario('home_name_filter', filtered, len(filtered), 1, bound, {'courseName': name})]
    for label, method in (('cover_get', 'GET'), ('cover_head', 'HEAD'), ('cover_range', 'GET')):
        scenarios.append(Scenario(label, method, target, asset_bytes=selected['bytes'], digest=selected['sha256'],
                                  range_end=min(RANGE_BYTES, selected['bytes']) - 1 if label == 'cover_range' else None,
                                  prefix_digest=selected['prefix_sha256'], content_type=selected['content_type']))
    table_count = int(v.sql(runtime, "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='teachingopen_dev'"))
    actual_courses, actual_units = map(int, v.sql(runtime, 'SELECT (SELECT COUNT(*) FROM teaching_course),'
                                                '(SELECT COUNT(*) FROM teaching_course_unit)').split('\t'))
    if not 1 <= actual_courses <= MAX_COURSES or len(rows) > actual_courses:
        raise BenchmarkFailure('course_snapshot_exceeds_bound')
    counts = {'database_tables': table_count, 'courses': actual_courses, 'units': actual_units,
              'manifest_courses': bound, 'manifest_units': database.get('teaching_course_unit', {}).get('rows'),
              'public_home_courses': len(rows),
              'name_filter_matches': len(filtered), 'course_assets': assets['count'], 'course_asset_bytes': assets['bytes']}
    return scenarios, counts, selected


def validate_sample(scenario, status, headers, content):
    """Validate after the HTTP completion timer; never serialize content."""
    headers = {key.lower(): value for key, value in headers.items()}
    if scenario.label.startswith('home_'):
        if status != 200 or not headers.get('content-type', '').lower().startswith('application/json'):
            raise BenchmarkFailure('home_status_or_content_type_invalid')
        try:
            body = json.loads(content)
        except (ValueError, UnicodeError):
            raise BenchmarkFailure('home_json_invalid') from None
        if (not isinstance(body, dict) or body.get('success') is not True
                or body.get('code') != 200 or not isinstance(body.get('result'), dict)):
            raise BenchmarkFailure('home_business_response_invalid')
        page = body['result']
        if (not isinstance(page.get('records'), list)
                or any(type(page.get(key)) is not int for key in ('total', 'current', 'size', 'pages'))
                or (page['total'], page['current'], page['size'], page['pages']) !=
                (scenario.total, scenario.current, scenario.size, math.ceil(scenario.total / scenario.size))):
            raise BenchmarkFailure('home_page_metadata_invalid')
        rows, expected = page['records'], {row['id']: row for row in scenario.expected_rows}
        if any(not isinstance(row, dict) or not isinstance(row.get('id'), str) for row in rows):
            raise BenchmarkFailure('home_record_shape_invalid')
        identities = [row['id'] for row in rows]
        required_count = max(0, min(scenario.size, scenario.total - (scenario.current - 1) * scenario.size))
        if (len(identities) != required_count or len(set(identities)) != len(identities)
                or not set(identities) <= set(expected)
                or (scenario.exact_set and set(identities) != set(expected))):
            raise BenchmarkFailure('home_record_set_invalid')
        fields = {'courseName': 'name', 'courseType': 'type', 'courseCategory': 'category',
                  'courseCover': 'cover', 'delFlag': 'delFlag'}
        if any(row.get('showHome') is not True or any(type(row.get(key)) is not type(expected[row['id']].get(source))
               or row.get(key) != expected[row['id']].get(source)
               for key, source in fields.items()) for row in rows):
            raise BenchmarkFailure('home_record_sql_fields_invalid')
        return
    if scenario.label not in LABELS or scenario.asset_bytes is None:
        raise BenchmarkFailure('scenario_not_allowed')
    expected_status = 206 if scenario.range_end is not None else 200
    expected_length = scenario.range_end + 1 if scenario.range_end is not None else scenario.asset_bytes
    if status != expected_status:
        raise BenchmarkFailure('cover_status_invalid')
    if (headers.get('content-length') != str(expected_length) or headers.get('accept-ranges') != 'bytes'
            or headers.get('content-type', '').split(';', 1)[0].lower() != scenario.content_type):
        raise BenchmarkFailure('cover_headers_invalid')
    if scenario.range_end is not None:
        if headers.get('content-range') != 'bytes 0-' + str(scenario.range_end) + '/' + str(scenario.asset_bytes):
            raise BenchmarkFailure('cover_content_range_invalid')
    elif 'content-range' in headers:
        raise BenchmarkFailure('cover_unexpected_content_range')
    if len(content) != (0 if scenario.method == 'HEAD' else expected_length):
        raise BenchmarkFailure('cover_body_length_invalid')
    if scenario.method != 'HEAD' and hashlib.sha256(content).hexdigest() != (
            scenario.prefix_digest if scenario.range_end is not None else scenario.digest):
        raise BenchmarkFailure('cover_body_digest_invalid')


def run_sample(port, scenario, connection_factory=None, identity_sink=None):
    # HTTPConnection ignores environment proxy settings and uses no shared
    # session. Each sample owns one new HTTP/1.1 connection and closes it.
    sample = {'duration_ms': None, 'status': None, 'body_bytes': 0,
              'http_completed': False, 'successful': False, 'failure_code': None}
    connection, started = None, time.perf_counter()
    try:
        if (type(port) is not int or not 1024 <= port <= 65535 or scenario.label not in LABELS
                or scenario.method != ('HEAD' if scenario.label == 'cover_head' else 'GET')
                or not (scenario.target.startswith(HOME + '?') if scenario.label.startswith('home_')
                        else scenario.target.startswith('/api/sys/common/static/'))
                or any(char in scenario.target for char in ('\r', '\n', '#'))):
            raise BenchmarkFailure('request_not_allowed')
        if not scenario.label.startswith('home_') and (
                type(scenario.asset_bytes) is not int or not 0 < scenario.asset_bytes <= MAX_COVER_BYTES
                or (scenario.range_end is not None and (type(scenario.range_end) is not int
                    or not 0 <= scenario.range_end < min(RANGE_BYTES, scenario.asset_bytes)))):
            raise BenchmarkFailure('cover_exceeds_http_byte_bound')
        connection = (connection_factory or http.client.HTTPConnection)('127.0.0.1', port, timeout=TIMEOUT)
        headers = {'Accept': 'application/json' if scenario.label.startswith('home_') else 'application/octet-stream',
                   'Accept-Encoding': 'identity', 'Connection': 'close'}
        if scenario.range_end is not None:
            headers['Range'] = 'bytes=0-' + str(scenario.range_end)
        started = time.perf_counter()
        connection.request(scenario.method, scenario.target, headers=headers)
        response = connection.getresponse()
        sample['status'] = response.status
        ceiling = MAX_JSON_BYTES if scenario.label.startswith('home_') else (
            0 if scenario.method == 'HEAD' else
            scenario.range_end + 1 if scenario.range_end is not None else scenario.asset_bytes)
        content = response.read(ceiling + 1)
        sample.update({'duration_ms': (time.perf_counter() - started) * 1000,
                       'body_bytes': len(content), 'http_completed': True})
        if len(content) > ceiling:
            raise BenchmarkFailure('response_exceeds_bound')
        validate_sample(scenario, response.status, dict(response.getheaders()), content)
        if identity_sink is not None and scenario.label.startswith('home_'):
            identity_sink.extend(row['id'] for row in json.loads(content)['result']['records'])
        sample['successful'] = True
    except BenchmarkFailure as error:
        sample['failure_code'] = str(error)
    except Exception:
        sample['failure_code'] = 'http_transport_failure'
    finally:
        if sample['duration_ms'] is None:
            sample['duration_ms'] = (time.perf_counter() - started) * 1000
        if connection is not None:
            try:
                connection.close()
            except Exception:
                sample.update({'successful': False, 'failure_code': 'http_transport_failure'})
    return sample


def distribution(values):
    ordered = sorted(values)
    if not ordered:
        return {'count': 0, 'min': None, 'max': None, 'median': None, 'p95': None}
    return {'count': len(ordered), 'min': ordered[0], 'max': ordered[-1],
            'median': statistics.median(ordered), 'p95': ordered[math.ceil(.95 * len(ordered)) - 1]}


def summarize(samples):
    return {'attempted': len(samples), 'successful': sum(sample['successful'] for sample in samples),
            'failed': sum(not sample['successful'] for sample in samples),
            'all_latency_ms': distribution([sample['duration_ms'] for sample in samples]),
            'successful_latency_ms': distribution([sample['duration_ms'] for sample in samples if sample['successful']]),
            'failure_counts': dict(sorted(Counter(sample['failure_code'] for sample in samples if not sample['successful']).items()))}


def machine():
    result = {'os': platform.platform(), 'python': platform.python_version(), 'model': None,
              'cpus': os.cpu_count(), 'ram_bytes': None}
    if platform.system() == 'Darwin':
        for key, name in (('model', 'hw.model'), ('ram_bytes', 'hw.memsize')):
            value = subprocess.run(['sysctl', '-n', name], capture_output=True, text=True, timeout=5)
            if value.returncode or not re.fullmatch('[A-Za-z0-9,._ -]{1,100}', value.stdout.strip()):
                raise BenchmarkFailure('machine_metadata_unavailable')
            result[key] = int(value.stdout) if key == 'ram_bytes' else value.stdout.strip()
    else:
        result['model'] = platform.machine()
        result['ram_bytes'] = os.sysconf('SC_PAGE_SIZE') * os.sysconf('SC_PHYS_PAGES')
    return result


def bindings(runtime, process, v):
    scripts = {'benchmark_cli': HERE / 'benchmark-production-read.py', 'benchmark_module': Path(__file__),
               'production_content_verifier': HERE / 'verify-production-content.py',
               'schema_policy': v.SCHEMA_PROFILE, 'production_fixture_helper': HERE / 'production_fixture.py',
               'local_runtime_helper': HERE / 'local_runtime.py', 'local_recovery_helper': HERE / 'local_recovery.py',
               'snapshot_backend_helper': HERE / 'snapshot_backend.py'}
    manifest = json.loads(v.read_private(runtime / 'snapshot-manifest.json'))
    return {'jar_sha256': process['jar_sha256'], 'snapshot_manifest_sha256': v.sha256(runtime / 'snapshot-manifest.json'),
            'source_sha256': manifest['source_sha256'], 'source_manifest_sha256': manifest['source_manifest_sha256'],
            'assets_manifest_sha256': v.sha256(runtime / 'assets-result.json'),
            'backend_receipt_sha256': v.sha256(runtime / 'backend-process.json'),
            'scripts': {key: v.sha256(path) for key, path in scripts.items()}}


def preflight_pages(port, scenarios, report):
    """Observe a complete partition; the endpoint does not promise ordering."""
    full = scenarios[0]
    expected = {row['id'] for row in full.expected_rows}
    observed = []
    for number in range(1, math.ceil(full.total / 2) + 1):
        scenario = home_scenario('home_first_page' if number == 1 else 'home_second_page',
                                 full.expected_rows, full.total, number, 2, exact_set=False)
        sample = run_sample(port, scenario, identity_sink=observed)
        report['preflight_samples'].append({'page': number, **sample})
        if not sample['successful']:
            raise BenchmarkFailure('preflight_pagination_response_failed')
    if len(observed) != len(set(observed)) or set(observed) != expected:
        raise BenchmarkFailure('preflight_pagination_partition_invalid')


def benchmark(args):
    v = load_verifier()
    runtime = v.local_path(args.runtime)
    output = Path(args.output).absolute()
    if output.parent != runtime or output.exists() or output.is_symlink():
        raise BenchmarkFailure('output_requires_fresh_private_runtime_file')
    report = {'format': 1, 'observed_utc': datetime.now(timezone.utc).isoformat(), 'executed': False, 'successful': False,
              'scope': 'Anonymous owned-loopback private-copy reads; no production capacity or browser acceptance claim.',
              'plan': {'rounds': ROUNDS, 'workers': list(WORKERS), 'measured_samples_per_cell': SAMPLES,
                       'warmup_samples_per_cell': WARMUP, 'planned_measured_requests': len(LABELS) * ROUNDS * len(WORKERS) * SAMPLES,
                       'planned_warmup_requests': len(LABELS) * ROUNDS * len(WORKERS) * WARMUP,
                       'request_timeout_seconds': TIMEOUT, 'measurement_budget_seconds': MAX_RUN_SECONDS,
                       'json_byte_ceiling': MAX_JSON_BYTES, 'cover_byte_ceiling': MAX_COVER_BYTES, 'range_bytes': RANGE_BYTES},
              'method': {'connection': 'Fresh loopback HTTP/1.1 connection per request; full bounded body completion.',
                         'timer': 'perf_counter; excludes semantic validation, SQL, local hashing and report writing.',
                         'p95': 'Nearest rank over the individual sample durations.',
                         'failure_policy': 'Retain each failure; stop scheduling after the current bounded worker batch.',
                         'timeout_contract': 'Socket inactivity timeout; measurement budget checked between batches, not an absolute wall-clock termination deadline.',
                         'page_contract': 'SQL eligible subsets with correct counts; preflight observes complete nonoverlapping pages, without ordering guarantee.'},
              'preflight_samples': [], 'cells': [], 'checks': [],
              'limitations': ['Shared local developer hardware; no WAN, TLS, browser rendering, playback, soak, saturation or production capacity conclusion.',
                              'Only anonymous homepage and one eligible course-cover asset are sampled.',
                              'Selected business-table digests and asset metadata are checked; operational logs and unrelated tables are outside the unchanged-data claim.',
                              'Full asset collection content is not rehashed; the selected cover is hashed before and after.']}
    before, asset_before, selected, deadline = None, None, None, None
    def check(label, passed):
        report['checks'].append({'case': label, 'passed': bool(passed)})
    try:
        runtime, ports, manifest, process = v.guard(runtime, args.jar)
        report.update({'executed': True, 'binding_before': bindings(runtime, process, v), 'machine': machine()})
        before = v.business_snapshot(runtime)
        assets = json.loads(v.read_private(runtime / 'assets-result.json'))
        asset_before = asset_snapshot(runtime, assets, v)
        scenarios, report['data_counts'], selected = build_scenarios(runtime, manifest, v)
        report['selected_cover_before'] = selected_cover_snapshot(runtime, selected, v)
        preflight_pages(ports['backend'], scenarios, report)
        check('preflight_pages_observe_sql_partition', True)
        deadline = time.perf_counter() + MAX_RUN_SECONDS
        for round_number in range(ROUNDS):
            for workers in WORKERS:
                offset = (round_number * len(WORKERS) + WORKERS.index(workers)) % len(scenarios)
                order = scenarios[offset:] + scenarios[:offset]
                for scenario in order:
                    cell = {'round': round_number + 1, 'workers': workers, 'scenario': scenario.label,
                            'order_in_round': [item.label for item in order], 'warmup_samples': [], 'samples': []}
                    report['cells'].append(cell)
                    with ThreadPoolExecutor(max_workers=workers) as pool:
                        for phase, count in (('warmup_samples', WARMUP), ('samples', SAMPLES)):
                            while len(cell[phase]) < count:
                                if time.perf_counter() > deadline:
                                    raise BenchmarkFailure('measurement_budget_exhausted')
                                batch = min(workers, count - len(cell[phase]))
                                futures = [pool.submit(run_sample, ports['backend'], scenario) for _ in range(batch)]
                                cell[phase].extend(future.result() for future in futures)
                                if any(not sample['successful'] for sample in cell[phase][-batch:]):
                                    raise BenchmarkFailure('sample_validation_failed')
                    cell['summary'] = summarize(cell['samples'])
                    cell['warmup_summary'] = summarize(cell['warmup_samples'])
        check('all_planned_measurements_completed', True)
    except KeyboardInterrupt:
        report['failure_code'] = 'interrupted'
    except BenchmarkFailure as error:
        report['failure_code'] = str(error)
    except Exception:
        report['failure_code'] = 'precondition_or_collection_failure'
    finally:
        # A partial run still attempts final guards and unchanged-data evidence.
        if report['executed']:
            final_guard_passed = False
            try:
                _, _, _, process_after = v.guard(runtime, args.jar)
                final_guard_passed = True
                report['binding_after'] = bindings(runtime, process_after, v)
                check('owned_backend_and_bindings_unchanged', report['binding_before'] == report['binding_after'])
            except Exception:
                check('owned_backend_and_bindings_unchanged', False)
            if before is not None:
                report['business_before'] = before
                try:
                    if not final_guard_passed:
                        raise BenchmarkFailure('final_guard_required_for_sql')
                    report['business_after'] = v.business_snapshot(runtime)
                    check('selected_business_rows_unchanged', before == report['business_after'])
                except Exception:
                    report['business_after_unavailable'] = True
                    check('selected_business_rows_unchanged', False)
            if asset_before is not None:
                report['asset_metadata_before'] = asset_before
                try:
                    assets_after = json.loads(v.read_private(runtime / 'assets-result.json'))
                    report['asset_metadata_after'] = asset_snapshot(runtime, assets_after, v)
                    check('asset_metadata_unchanged', asset_before == report['asset_metadata_after'])
                except Exception:
                    check('asset_metadata_unchanged', False)
            if selected is not None:
                try:
                    report['selected_cover_after'] = selected_cover_snapshot(runtime, selected, v)
                    check('selected_cover_bytes_unchanged', report['selected_cover_before'] == report['selected_cover_after'])
                except Exception:
                    check('selected_cover_bytes_unchanged', False)
        for cell in report['cells']:
            cell['summary'] = summarize(cell['samples'])
            cell['warmup_summary'] = summarize(cell['warmup_samples'])
        all_samples = [sample for cell in report['cells'] for sample in cell['samples']]
        all_warmups = [sample for cell in report['cells'] for sample in cell['warmup_samples']]
        report['measured_summary'], report['warmup_summary'] = summarize(all_samples), summarize(all_warmups)
        report['aggregates'] = [{'scenario': label, 'workers': workers,
                                 'summary': summarize([sample for cell in report['cells'] if cell['scenario'] == label
                                                       and cell['workers'] == workers for sample in cell['samples']])}
                                for label in LABELS for workers in WORKERS]
        report['successful'] = bool(report['executed'] and report['checks'] and not report.get('failure_code')
                                    and all(item['passed'] for item in report['checks'])
                                    and len(all_samples) == report['plan']['planned_measured_requests']
                                    and len(all_warmups) == report['plan']['planned_warmup_requests'])
        v.private_write(output, json.dumps(report, ensure_ascii=True, indent=2) + '\n')
    print(json.dumps({'executed': report['executed'], 'successful': report['successful'],
                      'measured_requests': report['measured_summary']['attempted'],
                      'failed_measured_requests': report['measured_summary']['failed'],
                      'warmup_requests': report['warmup_summary']['attempted'],
                      'preflight_requests': len(report['preflight_samples']), 'failure_code': report.get('failure_code')}))
    return 0 if report['successful'] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path, help='Fresh private JSON directly in the owned runtime')
    parser.add_argument('--jar', type=Path, help='Exact owned JAR; omitted uses the bound process receipt')
    try:
        return benchmark(parser.parse_args())
    except BenchmarkFailure as error:
        code = str(error)
    except Exception:
        code = 'precondition_or_report_failure'
    print(json.dumps({'executed': False, 'successful': False, 'failure_code': code}))
    return 1
