#!/usr/bin/env python3
"""Real HTTP pagination checks, exclusively in an owned synthetic runtime."""
import argparse
import json
from pathlib import Path
import subprocess
from urllib.parse import urlencode
from uuid import uuid4
from local_http import FixtureApi
from local_runtime import mysql_command


def verify(args):
    checks = []
    with FixtureApi(args.runtime.resolve(), args.jar) as api:
        def sql(statement):
            result = subprocess.run(mysql_command(api.runtime) + ['teachingopen_dev', '-e', statement],
                                    capture_output=True, text=True, timeout=20)
            if result.returncode:
                raise RuntimeError('Synthetic pagination SQL failed')
            return result.stdout.strip()

        def check(name, passed):
            checks.append({'case': name, 'passed': bool(passed)})
            print(('PASS ' if passed else 'FAIL ') + name, flush=True)
            if not passed:
                raise AssertionError(name)

        api.login('admin'); api.login('student_a')
        routes = [('/teaching/teachingNews/newsList', None), ('/teaching/teachingCourseUnit/list', 'admin'),
                  ('/teaching/teachingWork/mine', 'student_a')]
        for route, actor in routes:
            for key, values in [('pageNo', ['-1', '0', '2147483648', '1.5', 'abc', '']),
                                ('pageSize', ['-1', '0', '101', '99999999999999999999', '1.5', 'abc', ''])]:
                for value in values:
                    status, result, _ = api.request('GET', route + '?' + urlencode({key: value}), actor)
                    check(route + ' rejects ' + key + '=' + value,
                          status == 400 and result is not None and result.get('success') is False)
            status, result, _ = api.request('GET', route + '?pageSize=10&pageSize=-1', actor)
            check(route + ' rejects duplicate pagination values', status == 400 and result.get('success') is False)
            status, result, _ = api.request('GET', route + '?pageNo=1&pageSize=100', actor)
            check(route + ' accepts positive bounded pagination', status == 200 and result.get('success') is True
                  and len(result['result']['records']) <= 100)
        prefix = 'page_probe_' + uuid4().hex[:10]
        original_count = sql('SELECT COUNT(*) FROM teaching_news')
        try:
            sql('INSERT INTO teaching_news(id,news_title,news_content,news_status) VALUES ' + ','.join(
                "('" + prefix + '_' + str(i) + "','" + prefix + "','synthetic',1)" for i in range(101)))
            query = {'newsTitle': prefix, 'column': 'id', 'order': 'asc', 'pageSize': 100}
            pages = []
            for page_no in (1, 2):
                status, result, _ = api.request('GET', routes[0][0] + '?' + urlencode({**query, 'pageNo': page_no}))
                check('published news page ' + str(page_no) + ' returns a real bounded SQL page',
                      status == 200 and result.get('success') is True and len(result['result']['records']) == (100 if page_no == 1 else 1))
                pages.extend(row['id'] for row in result['result']['records'])
            check('101 published records remain reachable exactly once', len(set(pages)) == 101 and all(x.startswith(prefix) for x in pages))
        finally:
            sql("DELETE FROM teaching_news WHERE id LIKE '" + prefix + "_%'")
        check('original news records preserved', sql('SELECT COUNT(*) FROM teaching_news') == original_count)
        args.output.write_text(json.dumps({'scope': 'owned synthetic HTTP/MySQL', 'production_connected': False,
            'jar_sha256': api.jar_sha256, 'passed': len(checks), 'failed': 0, 'checks': checks}, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--jar', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    verify(parser.parse_args())
