#!/usr/bin/env python3
"""Compare teacher search semantics on an owned synthetic Java/MySQL runtime."""
import argparse
import json
from pathlib import Path
from urllib.parse import urlencode
from local_http import FixtureApi
from local_recovery import database_inventory, file_inventory, sql, private_write


def verify(args):
    if args.output.exists():
        raise RuntimeError('Output already exists; choose a fresh evidence path')
    cases = []
    observations = []
    prefix = 'fixture_search_'
    ids = [prefix + str(i) for i in range(3)]
    with FixtureApi(args.runtime, args.jar) as api:
        before = database_inventory(api.runtime)
        files = file_inventory(api.runtime / 'uploads')

        def query(statement):
            return sql(api.runtime, 'USE teachingopen_dev; ' + statement)

        def check(name, passed):
            cases.append({'case': name, 'passed': bool(passed)})
            print(('PASS ' if passed else 'FAIL ') + name, flush=True)

        def search(name, parameters, expected, actor='teacher_a', total=None):
            params = {'pageNo': 1, 'pageSize': 10, 'column': 'createTime', 'order': 'desc', **parameters}
            status, body, _ = api.request('GET', '/teaching/teachingWork/list?' + urlencode(params), actor)
            page = (body or {}).get('result') or {}
            actual = [row['id'] for row in page.get('records', [])]
            observations.append({'case': name, 'http': status, 'total': page.get('total'), 'ids': actual})
            check(name, status == 200 and body and body.get('success') is True
                  and actual == expected and page.get('total') == (len(expected) if total is None else total))

        for table in ('teaching_work', 'teaching_work_correct', 'teaching_work_comment'):
            if query("SELECT COUNT(*) FROM " + table + " WHERE id LIKE '" + prefix + "%'") != '0':
                raise RuntimeError('Existing same-prefix probe must be preserved')
        realname = query("SELECT realname FROM sys_user WHERE id='fixture_student_a'")
        if len(realname) < 3:
            raise RuntimeError('Synthetic name is too short for a substring check')
        error = None
        try:
            for actor in ('teacher_a', 'teacher_b', 'student_a', 'admin'):
                api.login(actor)
            for index, work_id in enumerate(ids):
                owner = 'fixture_student_b' if index == 2 else 'fixture_student_a'
                depart = 'fixture_class_b' if index == 2 else 'fixture_class_a'
                status = '2' if index == 1 else '1'
                query("INSERT INTO teaching_work (id,user_id,depart_id,work_name,work_file,work_type,work_status,work_scene,del_flag,create_by,create_time) VALUES ('"
                      + work_id + "','" + owner + "','" + depart + "','" + work_id
                      + "','','0','" + status + "','create',0,'" + owner + "','2026-10-01 10:0" + str(index) + ":00')")

            fuzzy = lambda rows: [] if args.expect_legacy else rows
            search('exact work name remains usable', {'workName': ids[0]}, [ids[0]])
            search('work name substring matches own pending work', {'workName': prefix, 'workStatus': '1'}, fuzzy([ids[0]]))
            search('work name infix matches own work', {'workName': 'search_0'}, fuzzy([ids[0]]))
            search('student name substring with exact work name', {'workName': ids[0], 'realname': realname[1:-1]}, fuzzy([ids[0]]))
            search('both fuzzy fields compose with status', {'workName': prefix, 'realname': realname[1:-1], 'workStatus': '2'}, fuzzy([ids[1]]))
            search('both exact text fields remain usable', {'workName': ids[0], 'realname': realname}, [ids[0]])
            search('unknown student name yields no work', {'workName': ids[0], 'realname': '不存在的合成学生'}, [])
            search('all states and descending order', {'workName': prefix}, fuzzy([ids[1], ids[0]]))
            search('ascending order and first page', {'workName': prefix, 'order': 'asc', 'pageSize': 1}, fuzzy([ids[0]]), total=0 if args.expect_legacy else 2)
            search('second page retains same total', {'workName': prefix, 'order': 'asc', 'pageSize': 1, 'pageNo': 2}, fuzzy([ids[1]]), total=0 if args.expect_legacy else 2)
            search('exact username filter remains usable', {'workName': ids[0], 'username': 'fixture_student_a'}, [ids[0]])
            search('username remains exact', {'workName': ids[0], 'username': 'fixture_student'}, [])
            search('status mismatch yields no work', {'workName': ids[0], 'workStatus': '2'}, [])
            search('scene mismatch yields no work', {'workName': ids[0], 'workScene': 'additional'}, [])
            search('type mismatch yields no work', {'workName': ids[0], 'workType': '4'}, [])
            search('class filter cannot widen teacher scope', {'workName': prefix, 'departId': 'fixture_class_b'}, [])
            search('other teacher sees only own class match', {'workName': prefix}, fuzzy([ids[2]]), actor='teacher_b')
            search('other teacher cannot retrieve exact class A work', {'workName': ids[0]}, [], actor='teacher_b')
            search('admin can search across both classes', {'workName': prefix}, fuzzy([ids[2], ids[1], ids[0]]), actor='admin')
            search('unmatched work name returns empty', {'workName': prefix + 'missing'}, [])
            search('quote text is a bound search value', {'workName': "' OR 1=1 --"}, [])
            for actor in ('student_a', None):
                status, body, _ = api.request('GET', '/teaching/teachingWork/list?' + urlencode({'workName': prefix}), actor)
                check('list denied ' + str(actor), status == (200 if actor else 401) and body
                      and body.get('success') is False and body.get('code') == (510 if actor else 401)
                      and not body.get('result'))
        except Exception as exc:
            error = type(exc).__name__
            raise
        finally:
            for work_id in ids:
                query("DELETE FROM teaching_work_correct WHERE work_id='" + work_id
                      + "'; DELETE FROM teaching_work_comment WHERE work_id='" + work_id
                      + "'; DELETE FROM teaching_work WHERE id='" + work_id + "'")
            after = database_inventory(api.runtime)
            check('all non-audit tables restored', all(before[t] == after[t] for t in before if t != 'sys_log'))
            check('attachment bytes unchanged', files == file_inventory(api.runtime / 'uploads'))
            result = {'legacy_expectations': args.expect_legacy, 'jar_sha256': api.jar_sha256,
                      'passed': sum(c['passed'] for c in cases), 'total': len(cases), 'exception': error,
                      'cases': cases, 'observations': observations,
                      'scope': 'Actual synthetic HTTP and database checks; legacy mode reproduces broken fuzzy search, not fixed acceptance.'}
            private_write(args.output, json.dumps(result, ensure_ascii=False, indent=2) + '\n')
        if not all(c['passed'] for c in cases):
            raise AssertionError('Teacher search checks failed; inspect result file')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--jar', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--expect-legacy', action='store_true')
    verify(parser.parse_args())
