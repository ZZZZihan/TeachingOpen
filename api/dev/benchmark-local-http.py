#!/usr/bin/env python3
"""Bounded HTTP compatibility/latency comparison on the private synthetic runtime.

Small fixtures and a shared developer machine: this is not a capacity benchmark.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timezone
import http.client
import json
import math
from pathlib import Path
import platform
import statistics
import subprocess
from threading import Barrier
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from local_http import FixtureApi
from local_recovery import database_inventory, file_inventory, private_write, sql


PREFIX = 'fixture_httpbench_'
SAMPLES = 48
WARMUP = 4


def benchmark(args):
    measurements, checks = [], []

    def check(name, passed):
        checks.append({'case': name, 'passed': bool(passed)})
        print(('PASS ' if passed else 'FAIL ') + name, flush=True)

    with FixtureApi(args.runtime, args.jar) as api:
        before = database_inventory(api.runtime)
        before_files = file_inventory(api.runtime / 'uploads')
        if sql(api.runtime, "SELECT COUNT(*) FROM teachingopen_dev.teaching_work WHERE id LIKE '" + PREFIX + "%'") != '0':
            raise RuntimeError('Existing benchmark works must not be overwritten')
        if sql(api.runtime, "SELECT COUNT(*) FROM teachingopen_dev.sys_data_log WHERE data_id LIKE '" + PREFIX + "%'") != '0':
            raise RuntimeError('Existing benchmark history must not be overwritten')
        try:
            api.login('student_a')
            for suffix in ['view'] + [str(i) for i in range(4)]:
                sql(api.runtime, "INSERT INTO teachingopen_dev.teaching_work (id,user_id,depart_id,work_name,work_type,work_status,work_file,create_by,create_time,work_scene) VALUES ('" + PREFIX + suffix + "','fixture_student_a','fixture_class_a','http-benchmark','2','0','fixture_file_a','fixture_student_a','2026-10-03 00:00:00','create')")
            base = 'http://127.0.0.1:' + str(api.ports['backend']) + '/api'

            def request_once(endpoint, worker):
                headers = {'Content-Type': 'application/json'}
                if endpoint != 'home_courses':
                    headers['X-Access-Token'] = api.tokens['student_a']
                routes = {
                    'home_courses': '/teaching/teachingCourse/getHomeCourse?pageNo=1&pageSize=12',
                    'assigned_course': '/teaching/teachingCourse/queryById?id=fixture_course_a',
                    'work_detail': '/teaching/teachingWork/studentWorkInfo?workId=' + PREFIX + 'view',
                    'draft_save': '/teaching/teachingWork/submit',
                }
                data = None
                if endpoint == 'draft_save':
                    data = json.dumps({'id': PREFIX + str(worker), 'workName': 'http-benchmark-saved',
                                       'workType': '2', 'workStatus': '0', 'workFile': 'fixture_file_a'}).encode()
                request = Request(base + routes[endpoint], data=data, headers=headers)
                started = time.perf_counter()
                try:
                    response = urlopen(request, timeout=15)
                except HTTPError as error:
                    response = error
                with response:
                    raw = response.read()
                    elapsed = (time.perf_counter() - started) * 1000
                    body = json.loads(raw)
                    ok = response.status == 200 and body.get('success') is True
                    result = body.get('result') or {}
                    if endpoint == 'home_courses':
                        ok = ok and result.get('total', 0) >= 2 and len(result.get('records', [])) >= 2
                    else:
                        expected = 'fixture_course_a' if endpoint == 'assigned_course' else PREFIX + ('view' if endpoint == 'work_detail' else str(worker))
                        ok = ok and result.get('id') == expected
                    return {'ms': round(elapsed, 3), 'ok': bool(ok), 'bytes': len(raw), 'http': response.status}

            # Separate fixed workers keep save requests on different work IDs.
            # urllib creates one connection per request, recorded in the report.
            for endpoint in ('home_courses', 'assigned_course', 'work_detail', 'draft_save'):
                for workers in (1, 4):
                    warm = [request_once(endpoint, i % workers) for i in range(WARMUP)]
                    check(endpoint + ' warmup ' + str(workers), all(x['ok'] for x in warm))
                    barrier = Barrier(workers, timeout=30)

                    def run_worker(worker):
                        barrier.wait()
                        return [request_once(endpoint, worker) for _ in range(SAMPLES // workers)]

                    started = time.perf_counter()
                    with ThreadPoolExecutor(max_workers=workers) as pool:
                        samples = [sample for group in pool.map(run_worker, range(workers)) for sample in group]
                    elapsed = time.perf_counter() - started
                    latencies = sorted(x['ms'] for x in samples)
                    measurements.append({'endpoint': endpoint, 'workers': workers, 'requests': len(samples),
                                         'successes': sum(x['ok'] for x in samples),
                                         'median_ms': round(statistics.median(latencies), 3),
                                         'p95_ms': latencies[math.ceil(len(latencies) * .95) - 1],
                                         'max_ms': max(latencies), 'batch_seconds': round(elapsed, 3),
                                         'requests_per_second': round(len(samples) / elapsed, 2), 'samples': samples})
                    check(endpoint + ' measured responses ' + str(workers), all(x['ok'] for x in samples) and len(samples) == SAMPLES)

            check('all benchmark detail views persist', sql(api.runtime, "SELECT view_num FROM teachingopen_dev.teaching_work WHERE id='" + PREFIX + "view'") == str(2 * (WARMUP + SAMPLES)))
            check('all four draft workers persist their saved content', sql(api.runtime, "SELECT COUNT(*) FROM teachingopen_dev.teaching_work WHERE id IN ('" + "','".join(PREFIX + str(i) for i in range(4)) + "') AND work_name='http-benchmark-saved' AND work_status='0'") == '4')

            # Check actual connection reuse independently of the timed urllib
            # samples, which intentionally use fresh connections.
            with closing(http.client.HTTPConnection('127.0.0.1', api.ports['backend'], timeout=15)) as conn:
                conn.request('GET', '/api/actuator/health')
                first = conn.getresponse(); first_body = first.read()
                peer = conn.sock.getsockname() if conn.sock else None
                conn.request('GET', '/api/teaching/teachingCourse/getHomeCourse?pageSize=2')
                second = conn.getresponse(); second_body = second.read()
                check('HTTP keep-alive reuses one connection across health and course requests',
                      first.status == second.status == 200 and json.loads(first_body).get('status') == 'UP'
                      and json.loads(second_body).get('success') is True and peer is not None
                      and conn.sock is not None and conn.sock.getsockname() == peer)
            jar_hash = api.jar_sha256
        finally:
            sql(api.runtime, "DELETE FROM teachingopen_dev.sys_data_log WHERE data_id LIKE '" + PREFIX + "%'; DELETE FROM teachingopen_dev.teaching_work WHERE id LIKE '" + PREFIX + "%'")
        after = database_inventory(api.runtime)
        check('all non-audit-log tables restored', all(before[t] == after[t] for t in before if t != 'sys_log'))
        check('all original attachment bytes unchanged', file_inventory(api.runtime / 'uploads') == before_files)
    hardware = {name: subprocess.check_output(['sysctl', '-n', name], text=True).strip()
                for name in ('hw.model', 'hw.ncpu', 'hw.memsize')}
    report = {'observed_utc': datetime.now(timezone.utc).isoformat(), 'jar_sha256': jar_hash,
              'os': platform.platform(), 'python': platform.python_version(), 'hardware': hardware,
              'fixture_row_counts': {t: before[t]['rows'] for t in ('sys_user', 'teaching_course', 'teaching_work')},
              'warmup_per_case': WARMUP, 'timed_requests_per_case': SAMPLES,
              'measurements': measurements, 'checks': checks, 'total': len(checks),
              'passed': sum(x['passed'] for x in checks),
              'method': 'localhost, fresh HTTP/1.1 connection per timed request; one batch per endpoint/concurrency, shared developer hardware, original synthetic fixtures plus five temporary works',
              'limitations': 'No throttled WAN, browser rendering, large dataset, saturation, sustained load, TLS, HTTP/2 or production capacity conclusion.'}
    private_write(args.output, json.dumps(report, indent=2) + '\n')
    return report['passed'] == report['total']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', required=True, type=Path)
    parser.add_argument('--jar', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    raise SystemExit(0 if benchmark(parser.parse_args()) else 1)
