#!/usr/bin/env python3
"""News authorization and rich HTML regressions against an owned synthetic MySQL runtime."""
import argparse
import base64
import hashlib
import json
import os
import zipfile
from pathlib import Path
import subprocess
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from local_http import FixtureApi
from local_runtime import mysql_command

PREFIX = 'news_content_probe_'
BASE = '/teaching/teachingNews/'
ATTACK = "<h2 style='text-align:center;color:#123abc'>标题</h2><table><tr><td>表格</td></tr></table><pre><code class='language-java'>code</code></pre><video src='/media/a.mp4' controls></video><img src='/fixture.png' onerror='window.newsXss=1'><a href='java&#x73;cript:alert(1)'>链接</a><svg onload='window.newsXss=2'></svg><math><mtext>x</mtext></math><p data-mce-src='javascript:alert(2)' style='background:url(javascript:alert(3))'>安全文本</p>"


def literal(value):
    return 'CONVERT(0x' + str(value).encode().hex() + ' USING utf8mb4)'


def safe(html):
    lower = str(html).lower()
    return not any(value in lower for value in ('onerror', 'onload', 'javascript:', '<svg', '<math', '<script', 'data-mce-', 'background:url'))


def verify(args):
    runtime = args.runtime.resolve()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    cases = []
    def check(name, passed, **details):
        cases.append(dict(case=name, passed=bool(passed), **details))
        print(('PASS ' if passed else 'FAIL ') + name, flush=True)
    with FixtureApi(runtime, args.jar) as api:
        def sql(query):
            return subprocess.check_output(mysql_command(runtime) + ['--default-character-set=utf8mb4', 'teachingopen_dev', '-e', query], text=True).strip()
        def snapshot():
            return hashlib.sha256(sql('SELECT * FROM teaching_news ORDER BY id').encode()).hexdigest()
        def ok(reply):
            return reply[0] == 200 and reply[1] and reply[1].get('success') is True
        def denied(reply, actor):
            expected = (401,) if actor is None else (403, 510)
            return isinstance(reply[1], dict) and reply[1].get('success') is False and reply[1].get('code') in expected and reply[0] in (200, 401, 403)
        def multipart(actor, payload):
            boundary = 'news-probe-boundary'
            raw = ('--' + boundary + '\r\nContent-Disposition: form-data; name="file"; filename="news.xls"\r\nContent-Type: application/vnd.ms-excel\r\n\r\n').encode() + payload + ('\r\n--' + boundary + '--\r\n').encode()
            headers = {'Content-Type': 'multipart/form-data; boundary=' + boundary}
            if actor: headers['X-Access-Token'] = api.tokens[actor]
            request = Request('http://127.0.0.1:' + str(api.ports['backend']) + '/api' + BASE + 'importExcel', data=raw, headers=headers, method='POST')
            try: response = urlopen(request, timeout=30)
            except HTTPError as error: response = error
            with response: return response.status, json.loads(response.read()), response.headers.get('Content-Type')
        original = snapshot()
        if sql('SELECT COUNT(*) FROM teaching_news WHERE id LIKE ' + literal(PREFIX + '%') + ' OR news_title LIKE ' + literal(PREFIX + '%')) != '0':
            raise ValueError('Existing probe rows; refusing to overwrite')
        original_role = sql("SELECT role_id FROM sys_user_role WHERE id='role_fixture_admin'")
        # Compile the Excel probe against dependencies from the verified running candidate.
        jar = (args.jar or Path(__file__).resolve().parents[1] / 'jeecg-boot-module-system/target/teaching-open-2.8.0.jar').resolve()
        libraries = args.output.parent / 'excel-libraries'; libraries.mkdir(exist_ok=True)
        jars = []
        with zipfile.ZipFile(jar) as archive:
            for name in archive.namelist():
                if name.startswith('BOOT-INF/lib/') and name.endswith('.jar') and name.count('/') == 2:
                    target = libraries / Path(name).name
                    target.write_bytes(archive.read(name)); jars.append(str(target))
        if not jars: raise ValueError('Verified candidate has no packaged runtime libraries')
        cp = os.pathsep.join(jars)
        java_home = Path(os.environ['JAVA_HOME']) if os.environ.get('JAVA_HOME') else runtime / 'tools/zulu8.96.0.205-ca-jdk8.0.504-macosx_aarch64/Contents/Home'
        java = java_home / 'bin'
        classes = args.output.parent / 'excel-classes'; classes.mkdir(exist_ok=True)
        subprocess.run([str(java / 'javac'), '-cp', cp, '-d', str(classes), str(Path(__file__).with_name('NewsExcelFixture.java')), str(Path(__file__).with_name('ReadXlsCells.java'))], check=True)
        xls = args.output.parent / 'news-import.xls'
        subprocess.run([str(java / 'java'), '-cp', str(classes) + os.pathsep + cp, 'NewsExcelFixture', str(xls), PREFIX + 'import'], check=True)
        try:
            for actor in ('admin', 'teacher_a', 'student_a'): api.login(actor)
            sql('INSERT INTO teaching_news (id,news_title,news_content,news_status) VALUES (' + literal(PREFIX + 'legacy') + ',' + literal(PREFIX + 'legacy') + ',' + literal(ATTACK) + ',1)')
            denied_before = snapshot()
            for actor in (None, 'student_a', 'teacher_a'):
                endpoints = [('POST', 'add', dict(id=PREFIX + 'denied', newsTitle=PREFIX + 'denied', newsContent=ATTACK, newsStatus=1)),
                             ('PUT', 'edit', dict(id=PREFIX + 'legacy', newsContent=ATTACK + 'changed')),
                             ('DELETE', 'delete?id=' + PREFIX + 'legacy', None),
                             ('DELETE', 'deleteBatch?ids=' + PREFIX + 'legacy', None)]
                for method, path, data in endpoints:
                    reply = api.request(method, BASE + path, actor, data)
                    check(str(actor) + ' denied ' + path.split('?')[0], denied(reply, actor), http_status=reply[0], code=reply[1].get('code') if reply[1] else None)
                reply = multipart(actor, xls.read_bytes())
                check(str(actor) + ' denied importExcel', denied(reply, actor), http_status=reply[0], code=reply[1].get('code') if reply[1] else None)
                check(str(actor) + ' denied requests preserve DB', snapshot() == denied_before)
            for actor, endpoint in ((None, 'newsDetail?id=' + PREFIX + 'legacy'), ('admin', 'queryById?id=' + PREFIX + 'legacy')):
                reply = api.request('GET', BASE + endpoint, actor)
                html = reply[1].get('result', {}).get('newsContent', '') if ok(reply) else ''
                check(endpoint.split('?')[0] + ' sanitizes historical content', ok(reply) and safe(html) and '<table>' in html and '<video' in html and 'language-java' in html)
            reply = api.request('GET', BASE + 'list?pageSize=100', 'admin')
            check('management list sanitizes historical content', ok(reply) and all(safe(row.get('newsContent')) for row in reply[1]['result']['records']))
            reply = api.request('GET', BASE + 'newsList?pageSize=100')
            check('anonymous newsList returns no HTML body', ok(reply) and all(not row.get('newsContent') for row in reply[1]['result']['records']))
            check('historical reads do not rewrite stored content', sql('SELECT HEX(news_content) FROM teaching_news WHERE id=' + literal(PREFIX + 'legacy')).lower() == ATTACK.encode().hex())
            for role in ('admin', 'dev'):
                if role == 'dev':
                    sql("INSERT INTO sys_role (id,role_code,role_name) VALUES ('news_content_probe_dev','dev','新闻测试dev'); UPDATE sys_user_role SET role_id='news_content_probe_dev' WHERE id='role_fixture_admin'")
                    api.request('GET', '/sys/logout', 'admin'); api.login('admin')
                row_id = PREFIX + role
                check(role + ' can add', ok(api.request('POST', BASE + 'add', 'admin', dict(id=row_id, newsTitle=PREFIX + role, newsContent=ATTACK, newsStatus=1))))
                check(role + ' add stores sanitized HTML', safe(bytes.fromhex(sql('SELECT HEX(news_content) FROM teaching_news WHERE id=' + literal(row_id))).decode()))
                check(role + ' can edit', ok(api.request('PUT', BASE + 'edit', 'admin', dict(id=row_id, newsContent=ATTACK + '<p>更新</p>'))))
                check(role + ' edit stores sanitized HTML', safe(bytes.fromhex(sql('SELECT HEX(news_content) FROM teaching_news WHERE id=' + literal(row_id))).decode()))
                check(role + ' can delete', ok(api.request('DELETE', BASE + 'delete?id=' + row_id, 'admin')) and sql('SELECT COUNT(*) FROM teaching_news WHERE id=' + literal(row_id)) == '0')
            reply = multipart('admin', xls.read_bytes())
            imported = sql('SELECT HEX(news_content) FROM teaching_news WHERE news_title=' + literal(PREFIX + 'import'))
            check('dev Excel import uses shared write sanitizer', ok(reply) and bool(imported) and safe(bytes.fromhex(imported).decode()) and '导入正文' in bytes.fromhex(imported).decode())
            request = Request('http://127.0.0.1:' + str(api.ports['backend']) + '/api' + BASE + 'exportXls?selections=' + PREFIX + 'legacy', headers={'X-Access-Token': api.tokens['admin']})
            with urlopen(request, timeout=30) as response:
                export = args.output.parent / 'news-export.xls'; export.write_bytes(response.read()); status = response.status
            cells = subprocess.check_output([str(java / 'java'), '-cp', str(classes) + os.pathsep + cp, 'ReadXlsCells', str(export)], text=True)
            cells = [base64.b64decode(cell).decode() for cell in cells.splitlines()]
            check('Excel export sanitizes historical HTML', status == 200 and any('<table>' in cell and safe(cell) for cell in cells))
            imported_id = sql('SELECT id FROM teaching_news WHERE news_title=' + literal(PREFIX + 'import'))
            check('dev can batch delete', ok(api.request('DELETE', BASE + 'deleteBatch?ids=' + PREFIX + 'legacy,' + imported_id, 'admin')) and sql('SELECT COUNT(*) FROM teaching_news WHERE news_title LIKE ' + literal(PREFIX + '%')) == '0')
        finally:
            sql('DELETE FROM teaching_news WHERE id LIKE ' + literal(PREFIX + '%') + ' OR news_title LIKE ' + literal(PREFIX + '%'))
            sql('UPDATE sys_user_role SET role_id=' + literal(original_role) + " WHERE id='role_fixture_admin'; DELETE FROM sys_role WHERE id='news_content_probe_dev'")
            api.request('GET', '/sys/logout', 'admin')
        check('original news rows restored', snapshot() == original)
        check('original admin role restored', sql("SELECT role_id FROM sys_user_role WHERE id='role_fixture_admin'") == original_role)
        result = dict(scope='Real login, HTTP CRUD/import/export, synthetic MySQL, Java8; no production access', jar_sha256=api.jar_sha256, passed=sum(case['passed'] for case in cases), total=len(cases), cases=cases)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(str(result['passed']) + '/' + str(result['total']) + ' checks passed')
    return result['passed'] == result['total']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True); parser.add_argument('--jar', type=Path); parser.add_argument('--output', type=Path, required=True)
    raise SystemExit(0 if verify(parser.parse_args()) else 1)
