#!/usr/bin/env python3
"""Teaching menu authorization/URL regressions on an owned, isolated synthetic runtime only."""
import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from uuid import uuid4
from local_http import FixtureApi
from local_runtime import mysql_command


def verify(args):
    checks = []
    failure = None
    legacy = bool(getattr(args, 'expect_legacy', False))
    with FixtureApi(args.runtime.resolve(), args.jar) as api:
        def check(name, passed):
            checks.append({'case': name, 'passed': bool(passed)})
            print(('PASS ' if passed else 'FAIL ') + name, flush=True)
            if not passed:
                raise AssertionError(name)

        def sql(statement):
            result = subprocess.run(mysql_command(api.runtime) + ['teachingopen_dev', '-e', statement], capture_output=True, text=True, timeout=20)
            if result.returncode:
                raise RuntimeError('Synthetic menu SQL failed: ' + result.stderr)
            return result.stdout.strip()

        def lit(value):
            return '(CONVERT(0x' + str(value).encode().hex() + ' USING utf8mb4) COLLATE utf8mb4_bin)'

        prefix = 'menu_auth_' + uuid4().hex[:10]
        root_id, child_id = prefix + '_r', prefix + '_c'
        grant_id, dev_grant_id, dev_role_id = prefix + '_grant', prefix + '_devlink', None
        created_dev_role = False
        created_ids = []
        tables = ('teaching_menu', 'sys_user_role')
        columns = {table: [line.split('\t')[0] for line in sql('SHOW COLUMNS FROM ' + table).splitlines()] for table in tables}
        if any(not name.replace('_', '').isalnum() for names in columns.values() for name in names):
            raise RuntimeError('Unexpected fixture schema')

        def snapshot():
            return {table: hashlib.sha256(sql('SELECT ' + ','.join("IFNULL(HEX(`" + col + "`),'NULL')" for col in columns[table]) + ' FROM ' + table + ' ORDER BY id').encode()).hexdigest() for table in tables}

        original = snapshot()
        body = {'name': prefix + '_new', 'menuType': 0, 'parentId': '', 'url': '/courseList', 'sortNo': 1, 'route': True,
                'internalOrExternal': False, 'hidden': False, 'needLogin': 0}

        def request(method, suffix, actor, data=None):
            return api.request(method, '/teaching/menu' + suffix, actor, data)

        def success(name, method, suffix, actor='admin', data=None):
            status, result, _ = request(method, suffix, actor, data)
            check(name, status == 200 and isinstance(result, dict) and result.get('success') is True)
            return result.get('result')

        def find_created(name):
            value = sql('SELECT id FROM teaching_menu WHERE name=' + lit(name))
            check('exactly one synthetic created menu for ' + name[len(prefix):], bool(value) and '\n' not in value)
            if value not in created_ids:
                created_ids.append(value)
            return value

        def flatten(rows):
            output = []
            for row in rows:
                output.append(row)
                output += flatten(row.get('children') or [])
            return output

        read_routes = ['/list', '/getSystemMenuList', '/getSystemSubmenu?' + urlencode({'parentId': root_id}),
                       '/getSystemSubmenuBatch?' + urlencode({'parentIds': root_id}), '/queryTreeList', '/queryListAsync']
        routes = [('GET', route, None) for route in read_routes] + [
            ('POST', '/add', body), ('PUT', '/edit', dict(body, id=root_id)), ('POST', '/edit', dict(body, id=root_id)),
            ('DELETE', '/delete?' + urlencode({'id': root_id}), None), ('DELETE', '/deleteBatch?' + urlencode({'ids': root_id + ',' + child_id}), None)]

        def deny_all(actor):
            for method, route, payload in routes:
                before = snapshot()
                status, result, _ = request(method, route, actor, payload)
                label = actor + ' ' + method + ' ' + route.split('?')[0]
                check(label + ' denied 403', status == 403 and isinstance(result, dict) and result.get('success') is False and result.get('code') == 403)
                check(label + ' leaves menus and role links unchanged', snapshot() == before)

        def invalid_url(url, route, external):
            for method, suffix in [('POST', '/add'), ('PUT', '/edit'), ('POST', '/edit')]:
                before = snapshot()
                payload = dict(body, id=root_id, url=url, route=route, internalOrExternal=external)
                status, result, _ = request(method, suffix, 'admin', payload)
                label = method + suffix + ' rejects ' + repr(url) + ' route=' + str(route) + ' external=' + str(external)
                check(label, status == 400 and isinstance(result, dict) and result.get('success') is False and result.get('code') == 400)
                check(label + ' without persistence', snapshot() == before)

        try:
            for actor in ('student_a', 'teacher_a', 'admin'):
                api.login(actor)
            check('student starts without management grants', sql("SELECT r.role_code FROM sys_role r JOIN sys_user_role ur ON ur.role_id=r.id WHERE ur.user_id='fixture_student_a' ORDER BY r.role_code") == 'student')
            # Deliberately stored legacy records, isolated by exact synthetic IDs. These no-op URLs never fetch or execute code.
            sql('INSERT INTO teaching_menu(id,parent_id,name,url,menu_type,sort_no,is_leaf,is_route,del_flag,hidden,need_login,internal_or_external) VALUES ('
                + ','.join((lit(root_id), "''", lit(prefix + '_root'), lit('javascript:void(0)'), '0', '1', '0', '0', '0', '0', '0', '0')) + '),('
                + ','.join((lit(child_id), lit(root_id), lit(prefix + '_child'), lit('data:text/plain,synthetic'), '1', '1', '1', '0', '0', '0', '0', '0')) + ')')
            before = snapshot()
            public_rows = flatten(success('anonymous public navigation loads', 'GET', '/getUserMenu', None))
            published = {row['id']: row for row in public_rows if row['id'] in (root_id, child_id)}
            check('public navigation contains both synthetic levels', set(published) == {root_id, child_id})
            if legacy:
                check('legacy public navigation exposes dangerous root URL and native same-tab flags', published[root_id]['url'] == 'javascript:void(0)' and published[root_id]['route'] is False and published[root_id]['internalOrExternal'] is False)
                check('legacy public navigation exposes dangerous child URL', published[child_id]['url'] == 'data:text/plain,synthetic')
                check('legacy public read does not modify state', snapshot() == before)
                success('legacy student can create global menu', 'POST', '/add', 'student_a', dict(body, url='javascript:void(0)', route=False))
                new_id = find_created(body['name'])
                check('legacy ordinary student write persists active URL', sql('SELECT url FROM teaching_menu WHERE id=' + lit(new_id)) == 'javascript:void(0)')
                for method in ('PUT', 'POST'):
                    success('legacy student can edit global menu using ' + method, method, '/edit', 'student_a', dict(body, id=new_id, name=prefix + '_' + method))
                    check('legacy edit ' + method + ' persists', sql('SELECT name FROM teaching_menu WHERE id=' + lit(new_id)) == prefix + '_' + method)
                success('legacy student can delete global menu', 'DELETE', '/delete?' + urlencode({'id': new_id}), 'student_a')
                check('legacy single deletion persists', sql('SELECT COUNT(*) FROM teaching_menu WHERE id=' + lit(new_id)) == '0')
                success('legacy student can batch delete global menu tree', 'DELETE', '/deleteBatch?' + urlencode({'ids': child_id + ',' + root_id}), 'student_a')
                check('legacy tree deletion persists', sql('SELECT COUNT(*) FROM teaching_menu WHERE id IN (' + lit(root_id) + ',' + lit(child_id) + ')') == '0')
            else:
                check('historical root and child URL are disabled in public output', all(row['url'] == '' and row['route'] is False and row['internalOrExternal'] is False for row in published.values()))
                check('read protection does not rewrite historical database values', snapshot() == before)
                for actor in ('student_a', 'teacher_a'):
                    deny_all(actor)
                for route in read_routes:
                    success('administrator reads ' + route.split('?')[0], 'GET', route)
                for url in ('javascript:void(0)', 'JaVaScRiPt:void(0)', 'data:text/html,synthetic', '//example.invalid/', '/%2fexample.invalid', '/%0aevil', 'https://user:pass@example.invalid'):
                    for route in (False, True):
                        for external in (False, True):
                            invalid_url(url, route, external)
                # Server owns IDs, audit fields, deletion state, and leaf state.
                forged = dict(body, id=prefix + '_forged', createBy='forged', updateBy='forged', delFlag=1, leaf=False)
                success('administrator creates a normal route', 'POST', '/add', data=forged)
                new_id = find_created(body['name'])
                check('creation ignores client identity and protected fields', new_id != forged['id'] and sql('SELECT CONCAT(create_by,\':\',del_flag,\':\',is_leaf) FROM teaching_menu WHERE id=' + lit(new_id)) == 'fixture_admin:0:1')
                for method, destination in [('PUT', '/scratch3/index.html?scene=create'), ('POST', 'https://example.invalid/course')]:
                    success('administrator edits via ' + method, method, '/edit', data=dict(body, id=new_id, url=destination, route=True, internalOrExternal=True, sortNo=4, createBy='forged', delFlag=1))
                    check('edit preserves creator, records current updater and persists supported destination', sql('SELECT CONCAT(create_by,\':\',update_by,\':\',del_flag,\':\',url) FROM teaching_menu WHERE id=' + lit(new_id)) == 'fixture_admin:fixture_admin:0:' + destination)
                check('external destination cannot be stored as a router link', sql('SELECT is_route FROM teaching_menu WHERE id=' + lit(new_id)) == '0')
                nested_name = prefix + '_nested'
                success('administrator adds nested item', 'POST', '/add', data=dict(body, name=nested_name, menuType=1, parentId=new_id, url='/safe-child'))
                nested_id = find_created(nested_name)
                check('parent leaf state is derived from persisted children', sql('SELECT is_leaf FROM teaching_menu WHERE id=' + lit(new_id)) == '0')
                before = snapshot()
                status, result, _ = request('PUT', '/edit', 'admin', dict(body, id=new_id, menuType=1, parentId=nested_id))
                check('parent cycle is rejected', status == 400 and isinstance(result, dict) and result.get('success') is False)
                check('cycle rejection leaves whole tree unchanged', snapshot() == before)
                before = snapshot()
                status, result, _ = request('DELETE', '/deleteBatch?' + urlencode({'ids': new_id + ',' + prefix + '_missing'}), 'admin')
                check('batch with missing identity fails', status == 400 and isinstance(result, dict) and result.get('success') is False)
                check('failed batch does not partially delete valid tree', snapshot() == before)
                # Same JWT: a temporary database grant becomes effective, then immediate revocation closes every operation.
                admin_role = sql("SELECT id FROM sys_role WHERE BINARY role_code='admin'")
                check('one fixture admin role exists', bool(admin_role) and '\n' not in admin_role)
                sql('INSERT INTO sys_user_role(id,user_id,role_id) VALUES (' + lit(grant_id) + ",'fixture_student_a'," + lit(admin_role) + ')')
                same_token = api.tokens['student_a']
                success('same student token receives live admin grant', 'GET', '/list', 'student_a')
                success('same granted token can edit', 'PUT', '/edit', 'student_a', dict(body, id=new_id, name=body['name'], url='/courseList'))
                sql('DELETE FROM sys_user_role WHERE id=' + lit(grant_id))
                check('revocation reuses exact token', api.tokens['student_a'] == same_token)
                deny_all('student_a')
                dev_role_id = sql("SELECT id FROM sys_role WHERE BINARY role_code='dev'")
                check('at most one fixture dev role exists', '\n' not in dev_role_id)
                if not dev_role_id:
                    dev_role_id, created_dev_role = prefix + '_role', True
                    sql('INSERT INTO sys_role(id,role_code,role_name,role_level) VALUES (' + lit(dev_role_id) + ",'dev','Synthetic menu operator',10)")
                sql('INSERT INTO sys_user_role(id,user_id,role_id) VALUES (' + lit(dev_grant_id) + ",'fixture_student_a'," + lit(dev_role_id) + ')')
                success('same token with current dev grant can read management', 'GET', '/list', 'student_a')
                success('current dev can edit grouping label', 'POST', '/edit', 'student_a', dict(body, id=new_id, url='', route=True, internalOrExternal=True))
                check('empty grouping label stores no navigation flags', sql('SELECT CONCAT(is_route,\':\',internal_or_external) FROM teaching_menu WHERE id=' + lit(new_id)) == '0:0')
                sql('DELETE FROM sys_user_role WHERE id=' + lit(dev_grant_id))
                before = snapshot()
                status, result, _ = request('PUT', '/edit', 'student_a', dict(body, id=new_id))
                check('revoked dev token is denied', status == 403 and isinstance(result, dict) and result.get('success') is False)
                check('revoked dev write has no effect', snapshot() == before)
                success('administrator deletes whole nested tree atomically', 'DELETE', '/deleteBatch?' + urlencode({'ids': new_id + ',' + nested_id}))
                check('legitimate batch removes both requested tree records', sql('SELECT COUNT(*) FROM teaching_menu WHERE id IN (' + lit(new_id) + ',' + lit(nested_id) + ')') == '0')
                success('administrator deletes historical root and descendants', 'DELETE', '/delete?' + urlencode({'id': root_id}))
                check('legitimate single delete cascades to child', sql('SELECT COUNT(*) FROM teaching_menu WHERE id IN (' + lit(root_id) + ',' + lit(child_id) + ')') == '0')
        except Exception as error:
            failure = error
        finally:
            try:
                # Only exact identities created by this run are removed; no production connection/configuration is possible through FixtureApi.
                sql('DELETE FROM teaching_menu WHERE id IN (' + ','.join(lit(i) for i in [root_id, child_id] + created_ids) + ')')
                # Also catch a successful HTTP create followed by a failed response/assertion before its server ID was read.
                sql('DELETE FROM teaching_menu WHERE name IN (' + ','.join(lit(prefix + suffix) for suffix in ('_new', '_PUT', '_POST', '_nested')) + ')')
                sql('DELETE FROM sys_user_role WHERE id IN (' + lit(grant_id) + ',' + lit(dev_grant_id) + ')')
                if created_dev_role:
                    sql('DELETE FROM sys_role WHERE id=' + lit(dev_role_id))
                check('fixture cleanup restores original menu and role-link tables', snapshot() == original)
            except Exception as error:
                if failure is None:
                    failure = error
            checks.append({'case': 'all required operations and cleanup completed', 'passed': failure is None})
            passed = sum(item['passed'] for item in checks)
            report = {'observed_utc': datetime.now(timezone.utc).isoformat(), 'scope': 'owned synthetic TeachingMenu HTTP/MySQL; no production connection',
                      'jar_sha256': api.jar_sha256, 'verifier_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'expected_legacy': legacy,
                      'passed': passed, 'failed': len(checks) - passed, 'total': len(checks), 'checks': checks, 'completed': failure is None,
                      'exception_type': type(failure).__name__ if failure else None}
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        if failure is not None:
            raise failure


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--jar', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--expect-legacy', action='store_true')
    verify(parser.parse_args())
