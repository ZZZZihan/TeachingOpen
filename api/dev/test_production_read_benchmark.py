"""Independent fail-closed checks; only an owned temporary loopback HTTP fixture.

No product runtime, MySQL, Redis, login, user file, or external connection is used.
"""
from contextlib import ExitStack, contextmanager, redirect_stdout
import copy
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
from pathlib import Path
import stat
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import production_read_benchmark as bench


PRIVATE_NAME = 'PRIVATE_COURSE_NAME_DO_NOT_REPORT'
PRIVATE_ID = 'PRIVATE_COURSE_ID_DO_NOT_REPORT'
PRIVATE_PATH = 'PRIVATE_ASSET_PATH_DO_NOT_REPORT.png'
PRIVATE_ERROR = 'secret=password PRIVATE_RUNTIME_PATH PRIVATE_EXCEPTION_TEXT'
MEDIA = bytes(range(256)) * 20
ROWS = (
    {'id': PRIVATE_ID, 'name': PRIVATE_NAME, 'type': '1', 'category': None,
     'cover': PRIVATE_PATH, 'showHome': 1, 'delFlag': None},
    {'id': 'second-private-id', 'name': 'Second private course', 'type': None,
     'category': '2', 'cover': None, 'showHome': 1, 'delFlag': 1},
)


def page_body(rows=ROWS, total=None, current=1, size=2):
    records = [{'id': row['id'], 'courseName': row['name'], 'courseType': row['type'],
                'courseCategory': row['category'], 'courseCover': row['cover'],
                'showHome': True, 'delFlag': row['delFlag']} for row in rows]
    total = len(rows) if total is None else total
    return {'success': True, 'code': 200, 'result': {'records': records, 'total': total,
            'current': current, 'size': size, 'pages': (total + size - 1) // size}}


def json_bytes(payload):
    return json.dumps(payload).encode()


def home_scenario(exact=True, rows=ROWS, current=1, size=2, total=2):
    return bench.Scenario(label='home_full' if exact else ('home_first_page' if current == 1 else 'home_second_page'), method='GET',
                          target='/api/teaching/teachingCourse/getHomeCourse?pageNo=1&pageSize=2',
                          expected_rows=tuple(rows), total=total, current=current,
                          size=size, exact_set=exact)


def cover_scenario(method='GET', partial=False):
    end = min(bench.RANGE_BYTES, len(MEDIA)) - 1
    return bench.Scenario(label='cover_range' if partial else ('cover_head' if method == 'HEAD' else 'cover_get'), method=method,
                          target='/api/sys/common/static/' + PRIVATE_PATH,
                          asset_bytes=len(MEDIA), digest=hashlib.sha256(MEDIA).hexdigest(),
                          range_end=end if partial else None,
                          prefix_digest=hashlib.sha256(MEDIA[:end + 1]).hexdigest(),
                          content_type='image/png')


class HomepageContracts(unittest.TestCase):
    def validate(self, payload, scenario=None, status=200, headers=None):
        return bench.validate_sample(scenario or home_scenario(), status,
                                     headers or {'content-type': 'application/json'}, json_bytes(payload))

    def test_successful_exact_set_and_nullable_metadata(self):
        self.validate(page_body())

    def test_page_order_is_not_invented(self):
        self.validate(page_body(tuple(reversed(ROWS))))

    def test_http_success_does_not_hide_business_failure(self):
        body = page_body(); body['success'] = False
        with self.assertRaises(bench.BenchmarkFailure): self.validate(body)

    def test_http_redirect_is_not_an_accepted_homepage(self):
        with self.assertRaises(bench.BenchmarkFailure): self.validate(page_body(), status=302)

    def test_non_json_or_html_is_not_an_accepted_homepage(self):
        with self.assertRaises(bench.BenchmarkFailure):
            bench.validate_sample(home_scenario(), 200, {'content-type': 'text/html'}, b'<html>secret</html>')

    def test_wrong_set_duplicate_missing_and_extra_records_fail(self):
        variants = [page_body(ROWS[:1]), page_body(ROWS + (ROWS[0],)), page_body((ROWS[0], ROWS[0]))]
        foreign = copy.deepcopy(page_body()); foreign['result']['records'][0]['id'] = 'unknown-private-id'
        variants.append(foreign)
        for payload in variants:
            with self.subTest(payload=payload), self.assertRaises(bench.BenchmarkFailure): self.validate(payload)

    def test_wrong_page_metadata_and_bool_integers_fail(self):
        for key, value in [('total', 3), ('current', 2), ('size', 3), ('pages', 2), ('total', True), ('current', True), ('size', True)]:
            body = page_body(); body['result'][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(bench.BenchmarkFailure): self.validate(body)

    def test_success_must_be_boolean_true(self):
        for value in [1, 'true', None]:
            body = page_body(); body['success'] = value
            with self.subTest(value=value), self.assertRaises(bench.BenchmarkFailure): self.validate(body)

    def test_flags_and_stored_course_fields_must_equal_sql(self):
        for key, value in [('showHome', False), ('showHome', 1), ('delFlag', 0), ('courseName', 'changed'),
                           ('courseType', '2'), ('courseCategory', '1'), ('courseCover', 'unexpected.png')]:
            body = page_body(); body['result']['records'][0][key] = value
            with self.subTest(key=key), self.assertRaises(bench.BenchmarkFailure): self.validate(body)

    def test_boolean_delete_flag_cannot_impersonate_stored_integer_zero(self):
        row = dict(ROWS[0], delFlag=0)
        body = page_body((row,), size=2); body['result']['records'][0]['delFlag'] = False
        with self.assertRaises(bench.BenchmarkFailure): self.validate(body, home_scenario(rows=(row,), total=1))

    def test_subset_page_accepts_eligible_rows_with_correct_count(self):
        scenario = home_scenario(exact=False, current=2, size=1)
        self.validate(page_body(ROWS[1:], total=2, current=2, size=1), scenario)

    def test_subset_page_rejects_foreign_duplicate_and_wrong_count(self):
        scenario = home_scenario(exact=False, size=1)
        payloads = [page_body((), total=2, size=1), page_body(ROWS, total=2, size=1)]
        foreign = page_body(ROWS[:1], total=2, size=1); foreign['result']['records'][0]['id'] = 'foreign'
        payloads.append(foreign)
        for payload in payloads:
            with self.subTest(payload=payload), self.assertRaises(bench.BenchmarkFailure): self.validate(payload, scenario)

    def test_positive_filter_requires_its_exact_sql_set(self):
        scenario = home_scenario(rows=ROWS[:1], total=1)
        self.validate(page_body(ROWS[:1], size=2), scenario)
        with self.assertRaises(bench.BenchmarkFailure): self.validate(page_body(ROWS[1:], size=2), scenario)


class MediaContracts(unittest.TestCase):
    def headers(self, length=None, **extra):
        result = {'content-type': 'image/png', 'content-length': str(len(MEDIA) if length is None else length),
                  'accept-ranges': 'bytes'}
        result.update(extra); return result

    def test_get_hash_status_type_and_length_are_validated(self):
        scenario = cover_scenario()
        bench.validate_sample(scenario, 200, self.headers(), MEDIA)
        cases = [(206, self.headers(), MEDIA), (200, self.headers(), b'x' * len(MEDIA)),
                 (200, self.headers(), MEDIA[:-1]), (200, self.headers(len(MEDIA) + 1), MEDIA),
                 (200, self.headers(**{'content-type': 'text/html'}), MEDIA),
                 (200, self.headers(**{'content-range': 'bytes 0-10/5120'}), MEDIA)]
        for status, headers, body in cases:
            with self.subTest(status=status, headers=headers), self.assertRaises(bench.BenchmarkFailure):
                bench.validate_sample(scenario, status, headers, body)

    def test_head_has_no_body_and_reports_full_length(self):
        scenario = cover_scenario(method='HEAD')
        bench.validate_sample(scenario, 200, self.headers(), b'')
        for status, headers, body in [(206, self.headers(), b''), (200, self.headers(0), b''), (200, self.headers(), b'x')]:
            with self.subTest(status=status, body=body), self.assertRaises(bench.BenchmarkFailure):
                bench.validate_sample(scenario, status, headers, body)

    def test_range_requires_exact_bounds_length_and_prefix_hash(self):
        scenario = cover_scenario(partial=True); end = scenario.range_end
        headers = self.headers(end + 1, **{'content-range': f'bytes 0-{end}/{len(MEDIA)}'})
        bench.validate_sample(scenario, 206, headers, MEDIA[:end + 1])
        cases = [(200, headers, MEDIA[:end + 1]), (206, self.headers(end + 1), MEDIA[:end + 1]),
                 (206, dict(headers, **{'content-range': f'bytes 1-{end + 1}/{len(MEDIA)}'}), MEDIA[:end + 1]),
                 (206, dict(headers, **{'content-range': f'bytes 0-{end}/{len(MEDIA) + 1}'}), MEDIA[:end + 1]),
                 (206, dict(headers, **{'content-length': str(end)}), MEDIA[:end + 1]),
                 (206, headers, b'x' * (end + 1))]
        for status, response_headers, body in cases:
            with self.subTest(status=status, headers=response_headers), self.assertRaises(bench.BenchmarkFailure):
                bench.validate_sample(scenario, status, response_headers, body)


class FixtureHandler(BaseHTTPRequestHandler):
    def do_GET(self): self.reply()
    def do_HEAD(self): self.reply()

    def reply(self):
        self.server.observed.append((self.command, self.path, dict(self.headers)))
        status, headers, body = self.server.reply
        self.send_response(status)
        for key, value in headers.items(): self.send_header(key, value)
        self.end_headers()
        if self.command != 'HEAD':
            try: self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError): pass

    def log_message(self, *_): pass


class LoopbackTransport(unittest.TestCase):
    def setUp(self):
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), FixtureHandler)
        self.server.observed = []
        self.server.reply = (200, {'Content-Type': 'application/json'}, json_bytes(page_body()))
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={'poll_interval': .01}, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop)

    def stop(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(2)

    def test_real_loopback_sample_validates_body_and_sends_no_credentials(self):
        with patch.dict('os.environ', {'HTTP_PROXY': 'http://127.0.0.1:1', 'HTTPS_PROXY': 'http://127.0.0.1:1'}):
            sample = bench.run_sample(self.server.server_port, home_scenario())
        self.assertTrue(sample['successful']); self.assertEqual(sample['status'], 200)
        self.assertGreaterEqual(sample['duration_ms'], 0)
        method, path, headers = self.server.observed[0]
        self.assertEqual(method, 'GET'); self.assertEqual(path, home_scenario().target)
        for name in ('Cookie', 'Authorization', 'X-Access-Token'):
            self.assertNotIn(name.lower(), {key.lower() for key in headers})

    def test_real_http_200_invalid_body_is_failed_sample(self):
        body = page_body(); body['success'] = False
        self.server.reply = (200, {'Content-Type': 'application/json'}, json_bytes(body))
        sample = bench.run_sample(self.server.server_port, home_scenario())
        self.assertFalse(sample['successful']); self.assertEqual(sample['status'], 200)
        self.assertIsInstance(sample['failure_code'], str); self.assertGreaterEqual(sample['duration_ms'], 0)

    def test_redirect_is_one_failed_request_and_never_followed(self):
        self.server.reply = (302, {'Location': 'http://127.0.0.1:1/' + PRIVATE_NAME}, b'')
        sample = bench.run_sample(self.server.server_port, home_scenario())
        self.assertFalse(sample['successful']); self.assertEqual(sample['status'], 302)
        self.assertEqual(len(self.server.observed), 1); self.assertNotIn(PRIVATE_NAME, json.dumps(sample))

    def test_real_get_head_and_range_use_expected_anonymous_methods(self):
        for scenario in (cover_scenario(), cover_scenario('HEAD'), cover_scenario(partial=True)):
            partial = scenario.range_end is not None; body = MEDIA[:scenario.range_end + 1] if partial else MEDIA
            headers = {'Content-Type': 'image/png', 'Content-Length': str(len(body)), 'Accept-Ranges': 'bytes'}
            if partial: headers['Content-Range'] = f'bytes 0-{scenario.range_end}/{len(MEDIA)}'
            self.server.reply = (206 if partial else 200, headers, body)
            sample = bench.run_sample(self.server.server_port, scenario)
            self.assertTrue(sample['successful'], sample)
            method, target, sent = self.server.observed[-1]
            self.assertEqual(method, scenario.method); self.assertEqual(target, scenario.target)
            self.assertEqual(sent.get('Range'), f'bytes=0-{scenario.range_end}' if partial else None)

    def test_arbitrary_urls_protected_routes_and_write_methods_fail_before_connection(self):
        from dataclasses import replace
        candidates = [replace(home_scenario(), target='http://example.invalid/private'),
                      replace(home_scenario(), target='//example.invalid/private'),
                      replace(home_scenario(), target='/api/sys/login'),
                      replace(home_scenario(), target='/api/teaching/teachingCourse/queryById?id=private'),
                      replace(home_scenario(), method='POST'),
                      replace(cover_scenario(), method='DELETE')]
        for scenario in candidates:
            with self.subTest(target=scenario.target), patch.object(bench.http.client, 'HTTPConnection') as connection:
                sample = bench.run_sample(self.server.server_port, scenario)
                self.assertFalse(sample['successful']); connection.assert_not_called()
        self.assertEqual(self.server.observed, [])


class ControlledResponse:
    def __init__(self, body, status=200, headers=None):
        self.body = body
        self.status = status
        self.headers = headers or {'Content-Type': 'application/json'}
        self.read_limits = []

    def getheaders(self): return list(self.headers.items())

    def read(self, amount=None):
        self.read_limits.append(amount)
        return self.body if amount is None else self.body[:amount]


class ControlledConnection:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.closed = False
        self.request_args = None

    def request(self, method, target, body=None, headers=None):
        self.request_args = (method, target, body, headers)
        if self.error is not None: raise self.error

    def getresponse(self): return self.response
    def close(self): self.closed = True


class TransportBoundsAndPrivacy(unittest.TestCase):
    def sample(self, response=None, error=None, scenario=None):
        connection = ControlledConnection(response, error)
        factory_calls = []
        def factory(host, port, timeout):
            factory_calls.append((host, port, timeout)); return connection
        result = bench.run_sample(12345, scenario or home_scenario(), connection_factory=factory)
        return result, connection, factory_calls

    def test_payload_bound_reads_only_one_byte_past_ceiling(self):
        response = ControlledResponse(b'x' * 10000)
        with patch.object(bench, 'MAX_JSON_BYTES', 64):
            sample, connection, calls = self.sample(response)
        self.assertFalse(sample['successful']); self.assertTrue(connection.closed)
        self.assertEqual(response.read_limits, [65])
        self.assertNotIn(PRIVATE_ERROR, json.dumps(sample))

    def test_private_exception_text_is_redacted_and_connection_closes(self):
        sample, connection, calls = self.sample(error=OSError(PRIVATE_ERROR))
        self.assertFalse(sample['successful']); self.assertTrue(connection.closed)
        self.assertGreaterEqual(sample['duration_ms'], 0)
        serialized = json.dumps(sample)
        for forbidden in (PRIVATE_ERROR, 'password', 'PRIVATE_RUNTIME_PATH', 'PRIVATE_EXCEPTION_TEXT'):
            self.assertNotIn(forbidden, serialized)
        self.assertEqual(calls[0][:2], ('127.0.0.1', 12345))
        self.assertGreater(calls[0][2], 0); self.assertLessEqual(calls[0][2], 5)

    def test_validation_failure_still_closes_connection(self):
        sample, connection, _ = self.sample(ControlledResponse(json_bytes({'success': False})))
        self.assertFalse(sample['successful']); self.assertTrue(connection.closed)

    def test_connection_close_failure_is_retained_as_a_sanitized_sample(self):
        connection = ControlledConnection(ControlledResponse(json_bytes(page_body())))
        def fail_close(): raise OSError(PRIVATE_ERROR)
        connection.close = fail_close
        sample = bench.run_sample(12345, home_scenario(), connection_factory=lambda *a, **kw: connection)
        self.assertFalse(sample['successful']); self.assertEqual(sample['status'], 200)
        self.assertGreaterEqual(sample['duration_ms'], 0); self.assertNotIn(PRIVATE_ERROR, json.dumps(sample))

    def test_cover_manifest_bound_is_checked_before_connection(self):
        for amount in (0, True, -1, bench.MAX_COVER_BYTES + 1):
            # dataclasses.replace supports both mutable and frozen Scenario types.
            from dataclasses import replace
            scenario = replace(cover_scenario(), asset_bytes=amount)
            connection = ControlledConnection(ControlledResponse(MEDIA))
            with self.subTest(amount=amount):
                calls = []
                def factory(*args, **kwargs): calls.append((args, kwargs)); return connection
                sample = bench.run_sample(12345, scenario, connection_factory=factory)
                self.assertFalse(sample['successful']); self.assertEqual(calls, [])

    def test_range_body_is_bounded_to_requested_prefix_plus_sentinel(self):
        scenario = cover_scenario(partial=True)
        response = ControlledResponse(MEDIA, 206, {'Content-Type': 'image/png', 'Content-Length': str(len(MEDIA))})
        sample, connection, _ = self.sample(response, scenario=scenario)
        self.assertFalse(sample['successful']); self.assertTrue(connection.closed)
        self.assertEqual(response.read_limits, [scenario.range_end + 2])

    def test_socket_timeout_is_a_failed_timed_sample(self):
        import socket
        sample, connection, _ = self.sample(error=socket.timeout(PRIVATE_ERROR))
        self.assertFalse(sample['successful']); self.assertEqual(sample['failure_code'], 'http_transport_failure')
        self.assertGreaterEqual(sample['duration_ms'], 0); self.assertTrue(connection.closed)
        self.assertNotIn(PRIVATE_ERROR, json.dumps(sample))


def sample_result(duration=1, success=True, code=None):
    return {'duration_ms': duration, 'status': 200, 'body_bytes': 10, 'http_completed': True,
            'successful': success, 'failure_code': code}


class StatisticalContracts(unittest.TestCase):
    def test_failed_samples_are_in_attempts_and_all_latency_p95(self):
        samples = [sample_result(value, value < 23, 'home_record_set_invalid' if value >= 23 else None)
                   for value in range(1, 25)]
        summary = bench.summarize(samples)
        self.assertEqual((summary['attempted'], summary['successful'], summary['failed']), (24, 22, 2))
        self.assertEqual(summary['failure_counts'], {'home_record_set_invalid': 2})
        self.assertEqual(summary['all_latency_ms'], {'count': 24, 'min': 1, 'max': 24, 'median': 12.5, 'p95': 23})
        self.assertEqual(summary['successful_latency_ms'], {'count': 22, 'min': 1, 'max': 22, 'median': 11.5, 'p95': 21})

    def test_empty_and_all_failed_cells_do_not_invent_success_latency(self):
        empty = bench.summarize([])
        self.assertEqual((empty['attempted'], empty['successful'], empty['failed']), (0, 0, 0))
        self.assertEqual(empty['all_latency_ms'], {'count': 0, 'min': None, 'max': None, 'median': None, 'p95': None})
        failed = bench.summarize([sample_result(4, False, 'http_transport_failure')])
        self.assertEqual(failed['all_latency_ms']['p95'], 4)
        self.assertEqual(failed['successful_latency_ms'], empty['all_latency_ms'])


class PaginationPreflight(unittest.TestCase):
    def run_partition(self, ids):
        full = home_scenario(rows=ROWS, total=2, size=2)
        report = {'preflight_samples': []}
        def request(port, scenario, identity_sink=None):
            identity_sink.extend(ids); return sample_result()
        with patch.object(bench, 'run_sample', side_effect=request):
            bench.preflight_pages(12345, [full], report)
        return report

    def test_complete_partition_can_use_different_order(self):
        report = self.run_partition([row['id'] for row in reversed(ROWS)])
        self.assertEqual(len(report['preflight_samples']), 1)
        self.assertNotIn(PRIVATE_ID, json.dumps(report))

    def test_partition_missing_foreign_or_repeated_ids_fail(self):
        for ids in [[ROWS[0]['id']], [ROWS[0]['id'], 'foreign'], [ROWS[0]['id'], ROWS[0]['id']]]:
            with self.subTest(ids=ids), self.assertRaises(bench.BenchmarkFailure): self.run_partition(ids)

    def test_failed_page_is_reported_and_preflight_stops(self):
        report = {'preflight_samples': []}; failed = sample_result(9, False, 'home_record_set_invalid')
        with patch.object(bench, 'run_sample', return_value=failed) as request, self.assertRaises(bench.BenchmarkFailure):
            bench.preflight_pages(12345, [home_scenario()], report)
        request.assert_called_once(); self.assertEqual(report['preflight_samples'][0]['duration_ms'], 9)


class BenchmarkOrchestration(unittest.TestCase):
    def setUp(self):
        import local_recovery
        from unittest.mock import Mock
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve(); (self.root / '.devspace').mkdir()
        self.runtime = self.root / '.devspace' / 'snapshot'; self.runtime.mkdir(mode=0o700)
        self.args = SimpleNamespace(runtime=self.runtime, jar=None, output=self.runtime / 'report.json')
        self.business = {name: {'rows': 1, 'sha256': 'a' * 64} for name in
                         ('teaching_course', 'teaching_course_unit', 'teaching_course_dept', 'teaching_additional_work',
                          'teaching_student', 'teaching_work', 'teaching_work_correct')}
        self.assets = {'files': 1, 'bytes': len(MEDIA), 'metadata_sha256': 'b' * 64,
                       'full_collection_content_rehashed': False}
        self.cover = {'bytes': len(MEDIA), 'sha256': hashlib.sha256(MEDIA).hexdigest()}
        self.v = SimpleNamespace(local_path=local_recovery.local_path, private_write=local_recovery.private_write,
            guard=Mock(return_value=(self.runtime, {'backend': 12345}, {}, {'jar_sha256': 'c' * 64})),
            business_snapshot=Mock(return_value=self.business), read_private=Mock(return_value=b'{"files":{}}'))
        self.scenarios = [home_scenario(), home_scenario(False), home_scenario(False, current=2),
                          home_scenario(rows=ROWS[:1], total=1), cover_scenario(), cover_scenario('HEAD'), cover_scenario(partial=True)]
        from dataclasses import replace
        self.scenarios = [replace(scenario, label=label) for scenario, label in zip(self.scenarios, bench.LABELS)]

    @contextmanager
    def environment(self, request=None, preflight=None):
        def default_preflight(port, scenarios, report): report['preflight_samples'].append(sample_result())
        with ExitStack() as stack:
            stack.enter_context(patch.object(bench, 'load_verifier', return_value=self.v))
            stack.enter_context(patch.object(bench, 'bindings', return_value={'jar_sha256': 'c' * 64, 'scripts': {}}))
            stack.enter_context(patch.object(bench, 'machine', return_value={'os': 'test fixture'}))
            snapshots = stack.enter_context(patch.object(bench, 'asset_snapshot', return_value=self.assets))
            cover = stack.enter_context(patch.object(bench, 'selected_cover_snapshot', return_value=self.cover))
            stack.enter_context(patch.object(bench, 'build_scenarios', return_value=(self.scenarios, {'courses': 2},
                               {'path': PRIVATE_PATH, **self.cover})))
            stack.enter_context(patch.object(bench, 'preflight_pages', side_effect=preflight or default_preflight))
            samples = stack.enter_context(patch.object(bench, 'run_sample', side_effect=request or (lambda *a, **kw: sample_result())))
            stdout = io.StringIO(); stack.enter_context(redirect_stdout(stdout))
            yield samples, snapshots, cover, stdout

    def report(self): return json.loads(self.args.output.read_text())

    def test_guard_failure_performs_no_http_and_writes_private_sanitized_failure(self):
        self.v.guard.side_effect = RuntimeError(PRIVATE_ERROR)
        with self.environment() as (request, assets, cover, stdout): self.assertEqual(bench.benchmark(self.args), 1)
        request.assert_not_called(); self.v.business_snapshot.assert_not_called(); assets.assert_not_called()
        report = self.report(); self.assertFalse(report['executed']); self.assertFalse(report['successful'])
        self.assertEqual(report['measured_summary']['attempted'], 0)
        self.assertEqual(stat.S_IMODE(self.args.output.stat().st_mode), 0o600)
        self.assertNotIn(PRIVATE_ERROR, self.args.output.read_text() + stdout.getvalue())

    def test_existing_output_and_symlink_are_preserved_before_guard(self):
        for symlink in (False, True):
            destination = self.runtime / ('link-report.json' if symlink else 'existing-report.json')
            target = self.root / 'prior-output.json'; target.write_text('prior user work')
            if symlink: destination.symlink_to(target)
            else: destination.write_text('prior user work')
            args = SimpleNamespace(**vars(self.args)); args.output = destination
            with self.subTest(symlink=symlink), self.environment() as (request, *_), self.assertRaises(bench.BenchmarkFailure):
                bench.benchmark(args)
            self.assertEqual(target.read_text(), 'prior user work'); self.assertEqual(destination.read_text(), 'prior user work')
            self.v.guard.assert_not_called(); request.assert_not_called()

    def test_wrong_output_directory_fails_before_guard(self):
        self.args.output = self.root / 'report.json'
        with self.environment() as (request, *_), self.assertRaises(bench.BenchmarkFailure): bench.benchmark(self.args)
        self.v.guard.assert_not_called(); request.assert_not_called(); self.assertFalse(self.args.output.exists())

    def test_full_plan_counts_and_private_report_do_not_leak_in_memory_identifiers(self):
        with self.environment() as (request, assets, cover, stdout): self.assertEqual(bench.benchmark(self.args), 0)
        report = self.report()
        self.assertEqual(request.call_count, 1134); self.assertEqual(len(report['cells']), 42)
        self.assertEqual((report['measured_summary']['attempted'], report['warmup_summary']['attempted']), (1008, 126))
        self.assertTrue(report['successful']); self.assertEqual(self.v.guard.call_count, 2)
        self.assertEqual(self.v.business_snapshot.call_count, 2); self.assertEqual(assets.call_count, 2); self.assertEqual(cover.call_count, 2)
        for cell in report['cells']:
            self.assertEqual((len(cell['samples']), len(cell['warmup_samples'])), (24, 3))
        text = self.args.output.read_text() + stdout.getvalue()
        for forbidden in (PRIVATE_NAME, PRIVATE_ID, PRIVATE_PATH, str(self.runtime), PRIVATE_ERROR): self.assertNotIn(forbidden, text)
        self.assertEqual(stat.S_IMODE(self.args.output.stat().st_mode), 0o600)

    def test_first_failed_measurement_retained_and_final_snapshots_still_run(self):
        calls = []
        def request(*args, **kwargs):
            calls.append(1); return sample_result(99, False, 'http_transport_failure') if len(calls) == 4 else sample_result()
        with self.environment(request=request) as (_, assets, cover, stdout): self.assertEqual(bench.benchmark(self.args), 1)
        report = self.report()
        self.assertEqual((report['warmup_summary']['attempted'], report['measured_summary']['attempted'], report['measured_summary']['failed']), (3, 1, 1))
        self.assertEqual(report['measured_summary']['all_latency_ms']['p95'], 99)
        self.assertEqual(report['measured_summary']['successful_latency_ms']['count'], 0)
        self.assertEqual(self.v.guard.call_count, 2); self.assertEqual(self.v.business_snapshot.call_count, 2)
        self.assertEqual(assets.call_count, 2); self.assertEqual(cover.call_count, 2)
        self.assertFalse(report['successful']); self.assertNotIn(PRIVATE_ID, stdout.getvalue())

    def test_failure_in_concurrent_batch_keeps_all_completed_batch_samples(self):
        calls = []
        def request(*args, **kwargs):
            calls.append(1); return sample_result(99, False, 'http_transport_failure') if len(calls) == 4 else sample_result()
        with self.environment(request=request), patch.object(bench, 'WORKERS', (4,)):
            self.assertEqual(bench.benchmark(self.args), 1)
        report = self.report()
        self.assertEqual((report['warmup_summary']['attempted'], report['measured_summary']['attempted'], report['measured_summary']['failed']), (3, 4, 1))
        self.assertEqual(len(calls), 7); self.assertEqual(report['measured_summary']['successful'], 3)
        self.assertEqual(report['measured_summary']['all_latency_ms']['p95'], 99)

    def test_end_guard_failure_prevents_further_sql_snapshot(self):
        self.v.guard.side_effect = [self.v.guard.return_value, RuntimeError(PRIVATE_ERROR)]
        with self.environment() as (_, assets, cover, stdout): self.assertEqual(bench.benchmark(self.args), 1)
        report = self.report(); checks = {entry['case']: entry['passed'] for entry in report['checks']}
        self.assertEqual(self.v.business_snapshot.call_count, 1)
        self.assertFalse(checks['owned_backend_and_bindings_unchanged']); self.assertFalse(checks['selected_business_rows_unchanged'])
        self.assertTrue(report['business_after_unavailable']); self.assertFalse(report['successful'])
        self.assertNotIn(PRIVATE_ERROR, self.args.output.read_text() + stdout.getvalue())

    def test_changed_business_rows_fail_even_if_every_sample_succeeds(self):
        changed = copy.deepcopy(self.business); changed['teaching_course']['sha256'] = 'd' * 64
        self.v.business_snapshot.side_effect = [self.business, changed]
        with self.environment(): self.assertEqual(bench.benchmark(self.args), 1)
        report = self.report()
        checks = {entry['case']: entry['passed'] for entry in report['checks']}
        self.assertFalse(checks['selected_business_rows_unchanged']); self.assertFalse(report['successful'])
        self.assertNotEqual(report['business_before'], report['business_after'])

    def test_unavailable_final_business_snapshot_fails_without_exception_text(self):
        self.v.business_snapshot.side_effect = [self.business, RuntimeError(PRIVATE_ERROR)]
        with self.environment() as (_, assets, cover, stdout): self.assertEqual(bench.benchmark(self.args), 1)
        report = self.report(); checks = {entry['case']: entry['passed'] for entry in report['checks']}
        self.assertFalse(checks['selected_business_rows_unchanged']); self.assertFalse(report['successful'])
        self.assertEqual(assets.call_count, 2); self.assertEqual(cover.call_count, 2)
        self.assertNotIn(PRIVATE_ERROR, self.args.output.read_text() + stdout.getvalue())

    def test_asset_metadata_or_selected_cover_change_fails(self):
        changed_assets = dict(self.assets, metadata_sha256='e' * 64)
        with self.environment() as (_, assets, cover, _):
            assets.side_effect = [self.assets, changed_assets]
            cover.side_effect = [self.cover, bench.BenchmarkFailure('selected_cover_manifest_mismatch')]
            self.assertEqual(bench.benchmark(self.args), 1)
        report = self.report(); checks = {entry['case']: entry['passed'] for entry in report['checks']}
        self.assertFalse(checks['asset_metadata_unchanged']); self.assertFalse(checks['selected_cover_bytes_unchanged'])
        self.assertFalse(report['successful'])

    def test_elapsed_measurement_budget_stops_scheduling_and_preserves_final_checks(self):
        with self.environment() as (request, assets, cover, _), patch.object(bench, 'MAX_RUN_SECONDS', -1):
            self.assertEqual(bench.benchmark(self.args), 1)
        request.assert_not_called(); report = self.report()
        self.assertEqual(report['failure_code'], 'measurement_budget_exhausted')
        self.assertEqual(report['measured_summary']['attempted'], 0); self.assertEqual(self.v.business_snapshot.call_count, 2)
        self.assertEqual(assets.call_count, 2); self.assertEqual(cover.call_count, 2)


class AssetAndScenarioContracts(unittest.TestCase):
    def setUp(self):
        import production_fixture
        from unittest.mock import Mock
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.runtime = Path(self.tmp.name).resolve()
        (self.runtime / 'uploads').mkdir()
        self.path = self.runtime / 'uploads' / PRIVATE_PATH; self.path.write_bytes(MEDIA)
        self.selected = {'path': PRIVATE_PATH, 'bytes': len(MEDIA), 'sha256': hashlib.sha256(MEDIA).hexdigest()}
        self.assets = {'files': {PRIVATE_PATH: {key: self.selected[key] for key in ('bytes', 'sha256')}},
                       'count': 1, 'bytes': len(MEDIA)}
        self.v = SimpleNamespace(ordinary_asset=production_fixture.ordinary_asset, sha256=production_fixture.sha256,
            read_private=Mock(return_value=json_bytes(self.assets)), course_rows=Mock(side_effect=[list(ROWS), [ROWS[0]]]),
            sql=Mock(side_effect=['69', '2\t3']), ELIGIBLE='show_home=1')

    def test_selected_cover_has_manifest_size_and_content_hash(self):
        self.assertEqual(bench.selected_cover_snapshot(self.runtime, self.selected, self.v),
                         {key: self.selected[key] for key in ('bytes', 'sha256')})
        self.path.write_bytes(b'x' * len(MEDIA))
        with self.assertRaises(bench.BenchmarkFailure): bench.selected_cover_snapshot(self.runtime, self.selected, self.v)

    def test_size_over_bound_is_rejected_before_asset_open(self):
        from unittest.mock import Mock
        fake = Mock(); fake.stat.return_value = SimpleNamespace(st_size=bench.MAX_COVER_BYTES + 1)
        self.v.ordinary_asset = Mock(return_value=fake)
        selected = dict(self.selected, bytes=bench.MAX_COVER_BYTES + 1)
        with self.assertRaises(bench.BenchmarkFailure): bench.selected_cover_snapshot(self.runtime, selected, self.v)
        fake.open.assert_not_called()

    def test_manifest_does_not_allow_symlink_or_unmanifested_assets(self):
        before = bench.asset_snapshot(self.runtime, self.assets, self.v)
        self.assertNotIn(PRIVATE_PATH, json.dumps(before))
        extra = self.runtime / 'uploads' / 'unmanifested'; extra.write_bytes(b'extra')
        with self.assertRaises(bench.BenchmarkFailure): bench.asset_snapshot(self.runtime, self.assets, self.v)
        extra.unlink(); self.path.unlink(); self.path.symlink_to(self.runtime / 'outside')
        with self.assertRaises(ValueError): bench.asset_snapshot(self.runtime, self.assets, self.v)

    def test_cover_selection_uses_only_eligible_known_local_asset(self):
        rows = [dict(ROWS[0], cover='https://example.invalid/private-image.png'), ROWS[0]]
        with patch.object(bench.http.client, 'HTTPConnection') as http:
            selected = bench.select_cover(self.runtime, rows, self.assets, self.v)
        self.assertEqual(selected['path'], PRIVATE_PATH); self.assertEqual(selected['content_type'], 'image/png')
        self.assertEqual(selected['prefix_sha256'], hashlib.sha256(MEDIA[:bench.RANGE_BYTES]).hexdigest())
        http.assert_not_called()

    def test_no_eligible_manifest_cover_fails_without_http(self):
        for reference in ['https://example.invalid/private.png', 'unknown.png', PRIVATE_PATH + '?credential=secret']:
            with self.subTest(reference=reference), patch.object(bench.http.client, 'HTTPConnection') as http, self.assertRaises(bench.BenchmarkFailure):
                bench.select_cover(self.runtime, [dict(ROWS[0], cover=reference)], self.assets, self.v)
            http.assert_not_called()

    def test_build_scenarios_uses_live_counts_select_only_and_sql_hex_name(self):
        manifest = {'database': {'teaching_course': {'rows': 4}, 'teaching_course_unit': {'rows': 10}}}
        scenarios, counts, selected = bench.build_scenarios(self.runtime, manifest, self.v)
        self.assertEqual([scenario.label for scenario in scenarios], list(bench.LABELS))
        self.assertEqual((counts['courses'], counts['units'], counts['manifest_courses'], counts['manifest_units']), (2, 3, 4, 10))
        self.assertFalse(scenarios[1].exact_set); self.assertFalse(scenarios[2].exact_set)
        self.assertTrue(scenarios[3].exact_set); self.assertEqual(scenarios[3].expected_rows, (ROWS[0],))
        condition = self.v.course_rows.call_args_list[1].args[1]
        self.assertIn(PRIVATE_NAME.encode().hex(), condition); self.assertNotIn(PRIVATE_NAME, condition)
        for call in self.v.sql.call_args_list:
            self.assertTrue(call.args[1].startswith('SELECT ')); self.assertNotIn(';', call.args[1])
        self.assertTrue(all(scenario.method in ('GET', 'HEAD') for scenario in scenarios))

    def test_course_bound_and_empty_or_foreign_filter_reject_before_cover_request(self):
        for count in (True, 0, bench.MAX_COURSES + 1):
            with self.subTest(count=count), self.assertRaises(bench.BenchmarkFailure):
                bench.build_scenarios(self.runtime, {'database': {'teaching_course': {'rows': count}}}, self.v)
        for filtered in ([], [dict(ROWS[0], id='foreign')]):
            self.v.course_rows.side_effect = [list(ROWS), filtered]
            with self.subTest(filtered=filtered), self.assertRaises(bench.BenchmarkFailure):
                bench.build_scenarios(self.runtime, {'database': {'teaching_course': {'rows': 2}}}, self.v)
