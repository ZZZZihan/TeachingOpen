#!/usr/bin/env python3
"""Exercise community disclosure and interactions on a private synthetic runtime."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
from local_http import FixtureApi
from local_runtime import mysql_command

PREFIX = 'fixture_cprobe_'
BASE = '/teaching/teachingWork/'
TABLES = ('teaching_work', 'teaching_work_correct', 'teaching_work_comment', 'sys_file')


def verify(args):
    cases = []
    with FixtureApi(args.runtime.resolve(), args.jar) as api:
        def sql(query):
            return subprocess.check_output(mysql_command(api.runtime) + ['teachingopen_dev', '-e', query], text=True).strip()

        def snapshot():
            return {t: hashlib.sha256(sql('SELECT * FROM ' + t + ' ORDER BY id').encode()).hexdigest() for t in TABLES}

        def likes():
            return api.cache('KEYS', 'starWork:' + PREFIX + '*').splitlines()

        def check(name, condition):
            cases.append({'case': name, 'passed': bool(condition)})
            print(('PASS ' if condition else 'FAIL ') + name, flush=True)

        def request(path, actor=None, method='GET', data=None, token=None):
            return api.request(method, BASE + path, actor, data, token)[:2]

        def successful(response):
            status, body = response
            return status == 200 and body and body.get('success') is True

        def records(path, actor=None):
            response = request(path, actor)
            if not successful(response):
                raise RuntimeError('List request failed: ' + path)
            return response[1]['result']['records']

        def denied(name, path, actor=None, method='GET', data=None, token=None, code=510):
            before, cache_before = snapshot(), likes()
            status, body = request(path, actor, method, data, token)
            check(name, status == (401 if code == 401 else 200) and body and body.get('success') is False
                  and body.get('code') == code and not body.get('result')
                  and snapshot() == before and likes() == cache_before)

        original = snapshot()
        uploads = api.runtime / 'uploads'
        original_files = {str(p.relative_to(uploads)): hashlib.sha256(p.read_bytes()).hexdigest() for p in uploads.rglob('*') if p.is_file()}
        if likes() or any(sql("SELECT COUNT(*) FROM " + t + " WHERE id LIKE '" + PREFIX + "%'") != '0' for t in TABLES):
            raise RuntimeError('Probe data already exists')
        try:
            for actor in ('admin', 'teacher_a', 'teacher_b', 'student_a', 'student_b'):
                api.login(actor)
            # Dedicated rows ensure view/star updates never touch the baseline fixtures.
            for suffix, status, deleted in [('draft', '0', 0), ('submitted', '1', 0), ('graded', '2', 0),
                                             ('published', '3', 0), ('featured', '4', 0), ('unknown', '9', 0),
                                             ('deleted', '4', 1), ('deleted_draft', '0', 1)]:
                ident = PREFIX + suffix
                sql("INSERT INTO teaching_work (id,user_id,depart_id,work_name,work_type,work_status,work_file,work_cover,del_flag,create_by,create_time) VALUES ('" + ident + "','fixture_student_a','fixture_class_a','community-probe-" + suffix + "','1','" + status + "','fixture_file_a','fixture_file_a'," + str(deleted) + ",'fixture_student_a','2026-10-03 00:00:00')")
                sql("INSERT INTO teaching_work_correct (id,work_id,score,comment) VALUES ('" + ident + "','" + ident + "',3,'private teaching feedback')")
                sql("INSERT INTO teaching_work_comment (id,work_id,user_id,comment) VALUES ('" + ident + "','" + ident + "','fixture_student_a','community probe comment')")
            sql("UPDATE teaching_work SET view_num=20 WHERE id='" + PREFIX + "published'")

            if args.expect_legacy:
                for suffix in ('draft', 'submitted', 'graded', 'deleted'):
                    response = request('studentWorkInfo?workId=' + PREFIX + suffix)
                    check('legacy anonymous detail leaks ' + suffix, successful(response) and response[1]['result'].get('workFileKey_url'))
                check('legacy anonymous private comments exposed', successful(request('getWorkComments?workId=' + PREFIX + 'draft')))
                for path, actor in [('starWork?workId=' + PREFIX + 'draft', None), ('saveComment', 'student_b')]:
                    before = snapshot()
                    response = request(path, actor, 'POST' if actor else 'GET', {'workId': PREFIX + 'draft', 'comment': 'unauthorized probe'} if actor else None)
                    check('legacy unauthorized ' + path.split('?')[0] + ' changes data', successful(response) and snapshot() != before)
                check('legacy missing-work comment accepted', successful(request('saveComment', 'student_b', 'POST', {'workId': PREFIX + 'missing', 'comment': 'orphan probe'})))
                great = records('greatWork?pageSize=100')
                board = records('leaderboard?pageSize=100')
                check('legacy featured list exposes graded work', PREFIX + 'graded' in {r['id'] for r in great})
                check('legacy ranking exposes unknown and deleted states', {PREFIX + 'unknown', PREFIX + 'deleted'} <= {r['id'] for r in board})
                check('legacy public list discloses teacher feedback and score', any(r.get('teacherComment') == 'private teaching feedback' and r.get('score') == 3 for r in board))
                check('legacy invalid credential bypasses anonymous detail route', successful(request('studentWorkInfo?workId=' + PREFIX + 'draft', token='invalid-probe-token')))
            else:
                # List filters remain public regardless of the caller's private work privileges.
                for actor in (None, 'student_a', 'admin'):
                    for endpoint, expected in [('greatWork', {'featured'}), ('leaderboard', {'published', 'featured'})]:
                        rows = records(endpoint + '?pageSize=100', actor)
                        ours = [r for r in rows if r['id'].startswith(PREFIX)]
                        check(str(actor) + ' ' + endpoint + ' only explicit live public states', {r['id'] for r in ours} == {PREFIX + s for s in expected})
                        check(str(actor) + ' ' + endpoint + ' omits grading feedback', all(r.get('score') is None and r.get('teacherComment') is None for r in ours))
                for state in (0, 1, 2, 9):
                    check('status filter cannot widen public list ' + str(state), not records('leaderboard?pageSize=100&workStatus=' + str(state)))
                check('author filter cannot expose private works', {r['id'] for r in records('leaderboard?userId=fixture_student_a&pageSize=100')} == {PREFIX + 'published', PREFIX + 'featured'})
                paged = records('leaderboard?pageSize=1&pageNo=1') + records('leaderboard?pageSize=1&pageNo=2')
                check('visibility applies before pagination', {r['id'] for r in paged} == {PREFIX + 'published', PREFIX + 'featured'})

                for suffix in ('draft', 'submitted', 'graded', 'unknown', 'deleted', 'deleted_draft', 'missing'):
                    ident = PREFIX + suffix
                    actors = (None, 'student_b', 'teacher_b') if suffix not in ('deleted', 'deleted_draft', 'missing') else (None, 'student_a', 'teacher_a', 'admin', 'student_b')
                    for actor in actors:
                        for endpoint in ('studentWorkInfo', 'getWorkComments', 'starWork'):
                            denied(str(actor) + ' denied ' + suffix + ' ' + endpoint + ' without effects', endpoint + '?workId=' + ident, actor)
                        denied(str(actor) + ' denied ' + suffix + ' comment without effects', 'saveComment', actor, 'POST', {'workId': ident, 'comment': 'denied probe'}, code=401 if actor is None else 510)

                for suffix in ('draft', 'submitted', 'graded', 'unknown', 'published', 'featured'):
                    ident = PREFIX + suffix
                    actors = ('student_a', 'teacher_a', 'admin') if suffix not in ('published', 'featured') else (None, 'student_b', 'teacher_b')
                    for actor in actors:
                        before_view = int(sql("SELECT view_num FROM teaching_work WHERE id='" + ident + "'"))
                        response = request('studentWorkInfo?workId=' + ident, actor)
                        check(str(actor) + ' allowed ' + suffix + ' detail and one view', successful(response) and response[1]['result'].get('workFileKey_url')
                              and int(sql("SELECT view_num FROM teaching_work WHERE id='" + ident + "'")) == before_view + 1)
                        response = request('getWorkComments?workId=' + ident, actor)
                        check(str(actor) + ' allowed ' + suffix + ' comment read', successful(response) and any(c['comment'] == 'community probe comment' for c in response[1]['result']))
                        before_star = int(sql("SELECT star_num FROM teaching_work WHERE id='" + ident + "'"))
                        for key in likes():
                            if key.startswith('starWork:' + ident):
                                api.cache('DEL', key)
                        check(str(actor) + ' allowed ' + suffix + ' like', successful(request('starWork?workId=' + ident, actor))
                              and int(sql("SELECT star_num FROM teaching_work WHERE id='" + ident + "'")) == before_star + 1)
                        before_repeat = snapshot()
                        check(str(actor) + ' repeated ' + suffix + ' like is unchanged', successful(request('starWork?workId=' + ident, actor)) and snapshot() == before_repeat)
                        if actor is not None:
                            before_count = int(sql("SELECT COUNT(*) FROM teaching_work_comment WHERE work_id='" + ident + "'"))
                            check(str(actor) + ' allowed ' + suffix + ' comment with server identity', successful(request('saveComment', actor, 'POST', {'workId': ident, 'comment': 'allowed probe ' + actor, 'userId': 'fixture_student_b'}))
                                  and int(sql("SELECT COUNT(*) FROM teaching_work_comment WHERE work_id='" + ident + "'")) == before_count + 1
                                  and sql("SELECT user_id FROM teaching_work_comment WHERE work_id='" + ident + "' AND comment='allowed probe " + actor + "'") == 'fixture_' + actor)
                        else:
                            denied('anonymous cannot comment on ' + suffix, 'saveComment', method='POST', data={'workId': ident, 'comment': 'anonymous probe'}, code=401)

                sql("UPDATE teaching_work SET work_status='0' WHERE id='" + PREFIX + "published'")
                for endpoint in ('studentWorkInfo', 'getWorkComments', 'starWork'):
                    denied('withdrawn public work blocks anonymous ' + endpoint, endpoint + '?workId=' + PREFIX + 'published')
                check('owner can reopen withdrawn work', successful(request('studentWorkInfo?workId=' + PREFIX + 'published', 'student_a')))
                check('withdrawn work immediately disappears from ranking', PREFIX + 'published' not in {r['id'] for r in records('leaderboard?pageSize=100')})
                sql("UPDATE teaching_work SET work_status='3' WHERE id='" + PREFIX + "published'")
                for token_label, token in [('malformed', 'invalid-probe-token'), ('empty', '')]:
                    for endpoint in ('studentWorkInfo', 'getWorkComments', 'starWork'):
                        denied(token_label + ' token rejected on public ' + endpoint, endpoint + '?workId=' + PREFIX + 'published', token=token, code=401)
                revoked = api.tokens['student_a']
                api.request('GET', '/sys/logout', 'student_a')
                del api.tokens['student_a']
                for endpoint in ('studentWorkInfo', 'getWorkComments', 'starWork'):
                    denied('revoked token rejected on ' + endpoint, endpoint + '?workId=' + PREFIX + 'draft', token=revoked, code=401)
                check('anonymous public request still works after authenticated requests', successful(request('studentWorkInfo?workId=' + PREFIX + 'published')))
                denied('anonymous identity does not inherit previous owner', 'studentWorkInfo?workId=' + PREFIX + 'draft')
            jar_hash = api.jar_sha256
        finally:
            sql("DELETE FROM teaching_work_comment WHERE work_id LIKE '" + PREFIX + "%'; DELETE FROM teaching_work_correct WHERE work_id LIKE '" + PREFIX + "%'; DELETE FROM teaching_work WHERE id LIKE '" + PREFIX + "%'")
            for key in likes():
                api.cache('DEL', key)
        check('original work feedback comment file rows restored', snapshot() == original)
        check('original file bytes unchanged', {str(p.relative_to(uploads)): hashlib.sha256(p.read_bytes()).hexdigest() for p in uploads.rglob('*') if p.is_file()} == original_files)
        check('temporary like cache removed', not likes())
    report = {'observed_utc': datetime.now(timezone.utc).isoformat(), 'jar_sha256': jar_hash, 'expected_legacy': args.expect_legacy,
              'passed': sum(c['passed'] for c in cases), 'total': len(cases), 'cases': cases,
              'scope': 'real synthetic HTTP/auth/DB/cache and disclosure checks; no browser editor, direct static-file security, concurrency or full public-profile privacy acceptance'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(str(report['passed']) + '/' + str(report['total']) + ' checks passed')
    return report['passed'] == report['total']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', required=True, type=Path)
    parser.add_argument('--jar', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--expect-legacy', action='store_true')
    raise SystemExit(0 if verify(parser.parse_args()) else 1)
