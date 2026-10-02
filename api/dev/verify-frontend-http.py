#!/usr/bin/env python3
"""Actual same-origin login, protected media and SPA reads on synthetic data."""
import argparse
import hashlib
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from local_http import FixtureApi
from local_recovery import database_inventory, file_inventory, private_write


def verify(args):
    cases = []
    def check(name, passed):
        cases.append({'case': name, 'passed': bool(passed)})
        print(('PASS ' if passed else 'FAIL ') + name, flush=True)

    with FixtureApi(args.runtime, args.jar) as api:
        before, files = database_inventory(api.runtime), file_inventory(api.runtime / 'uploads')
        backend_port = api.ports['backend']
        api.ports['backend'] = api.ports['frontend']
        base = 'http://127.0.0.1:' + str(api.ports['frontend'])
        def request(path, headers=None):
            try:
                response = urlopen(Request(base + path, headers=headers or {}), timeout=10)
            except HTTPError as error:
                response = error
            with response:
                return response.status, response.headers, response.read()

        cookies = {}
        for actor in ('student_a', 'student_b'):
            api.login(actor)
            values = api.last_response_headers.get_all('Set-Cookie', [])
            cookies[actor] = next((v.split(';')[0] for v in values if v.startswith('teaching_media_' + str(backend_port) + '=')), '')
            check('real login through proxy preserves media cookie ' + actor, bool(cookies[actor]))
        code, body, _ = api.request('GET', '/teaching/teachingCourse/queryById?id=fixture_course_a', 'student_a')
        check('authenticated course GET through proxy', code == 200 and body and body.get('success') and body['result']['id'] == 'fixture_course_a')
        path = '/api/sys/common/static/fixture-work-a.txt'
        expected = (api.runtime / 'uploads/fixture-work-a.txt').read_bytes()
        status, headers, data = request(path, {'Cookie': cookies['student_a']})
        check('owner cookie-only media bytes and cache policy', status == 200 and data == expected and headers.get('Cache-Control') == 'no-store')
        status, headers, data = request(path, {'Cookie': cookies['student_a'], 'Range': 'bytes=0-3'})
        check('protected media Range bytes and headers', status == 206 and data == expected[:4] and headers.get('Content-Range') == 'bytes 0-3/' + str(len(expected)))
        status, _, data = request(path)
        check('anonymous media request denied through proxy', status == 401 and expected not in data)
        status, _, data = request(path, {'Cookie': cookies['student_b']})
        check('other student media request denied through proxy', status == 403 and expected not in data)
        expected_index = (args.dist / 'index.html').read_bytes()
        for route in ('/index.html', '/index', '/user/login'):
            status, headers, data = request(route)
            check('unchanged static/SPA bytes ' + route, status == 200 and data == expected_index and "connect-src 'self'" in headers.get('Content-Security-Policy', ''))
        status, _, _ = request('/fixture-proxy-does-not-exist.js')
        check('missing static resource remains 404', status == 404)
        after = database_inventory(api.runtime)
        check('all non-audit tables unchanged', all(before[t] == after[t] for t in before if t != 'sys_log'))
        check('all attachment bytes unchanged', files == file_inventory(api.runtime / 'uploads'))
        result = {'cases': cases, 'passed': sum(c['passed'] for c in cases), 'total': len(cases),
                  'jar_sha256': api.jar_sha256, 'index_sha256': hashlib.sha256(expected_index).hexdigest(),
                  'scope': 'Actual synthetic CLI login and HTTP through the frontend; not browser authentication or UI acceptance'}
    private_write(args.output, json.dumps(result, indent=2) + '\n')
    return result['passed'] == result['total']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--jar', type=Path, required=True)
    parser.add_argument('--dist', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    raise SystemExit(0 if verify(parser.parse_args()) else 1)
