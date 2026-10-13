#!/usr/bin/env python3
"""Exercise dev-only infrastructure endpoints on an owned synthetic HTTP/MySQL runtime."""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import subprocess
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import uuid4

from local_http import FixtureApi
from local_runtime import mysql_command


SAMPLE = 'org.jeecg.modules.quartz.job.SampleJob'
PARAMETER_SAMPLE = 'org.jeecg.modules.quartz.job.SampleParamJob'


def verify(args):
    checks = []
    online_routes = []
    with FixtureApi(args.runtime.resolve(), args.jar) as api:
        def check(name, passed):
            checks.append({'case': name, 'passed': bool(passed)})
            print(('PASS ' if passed else 'FAIL ') + name, flush=True)
            if not passed:
                raise AssertionError(name)

        def sql(statement):
            result = subprocess.run(mysql_command(api.runtime) + ['teachingopen_dev', '-e', statement],
                                    capture_output=True, text=True, timeout=20)
            if result.returncode:
                raise RuntimeError('Synthetic infrastructure SQL failed: ' + result.stderr)
            return result.stdout.strip()

        def literal(value):
            # An explicit collation wins over either legacy general_ci or MySQL 8's default 0900 collation.
            # Binary comparison also prevents case-folded fixture cleanup from selecting another identity.
            return '(CONVERT(0x' + str(value).encode().hex() + ' USING utf8mb4) COLLATE utf8mb4_bin)'

        def raw(method, path, actor, payload=None, content_type='application/json'):
            request = Request('http://127.0.0.1:' + str(api.ports['backend']) + '/api' + path,
                              data=payload, method=method,
                              headers={'Content-Type': content_type, 'X-Access-Token': api.tokens[actor]})
            try:
                response = urlopen(request, timeout=20)
            except HTTPError as error:
                response = error
            with response:
                return response.status, response.read()

        def allowed(name, method, route, body=None):
            status, result, _ = api.request(method, route, 'admin', body)
            check(name, status == 200 and result is not None and result.get('success') is True)
            return result.get('result')

        prefix = 'ops_auth_' + uuid4().hex[:10]
        source_id, job_id = prefix + '_source', prefix + '_job'
        additional_source_id = additional_job_id = None
        role_link, created_role = prefix + '_grant', False
        cache_key = 'sys:cache:dbconnect:dynamic:' + prefix
        # These fixtures are synthetic; never replace a configured task or source.
        check('sample task identities are not already configured', sql(
            'SELECT COUNT(*) FROM sys_quartz_job WHERE job_class_name IN (' + literal(SAMPLE) + ',' + literal(PARAMETER_SAMPLE) + ')') == '0')
        check('sample task identities are not already scheduled', sql(
            'SELECT COUNT(*) FROM QRTZ_JOB_DETAILS WHERE JOB_NAME IN (' + literal(SAMPLE) + ',' + literal(PARAMETER_SAMPLE) + ')') == '0')
        role_id = sql("SELECT id FROM sys_role WHERE BINARY role_code='dev'")
        if '\n' in role_id:
            raise RuntimeError('Expected at most one dev role')
        # Opaque hashes only: neither source credentials nor user tokens enter the report.
        tables = {'sys_data_source': 'id', 'sys_quartz_job': 'id', 'QRTZ_JOB_DETAILS': 'SCHED_NAME,JOB_NAME,JOB_GROUP',
                  'QRTZ_TRIGGERS': 'SCHED_NAME,TRIGGER_NAME,TRIGGER_GROUP', 'QRTZ_CRON_TRIGGERS': 'SCHED_NAME,TRIGGER_NAME,TRIGGER_GROUP'}

        # Quartz JOB_DATA contains Java-serialized BLOBs; hex each field before sending it through a text client.
        columns = {table: [row.split('\t')[0] for row in sql('SHOW COLUMNS FROM ' + table).splitlines()] for table in tables}
        if any(not name.replace('_', '').isalnum() for names in columns.values() for name in names):
            raise RuntimeError('Unexpected infrastructure column name')

        def snapshot():
            value = {table: hashlib.sha256(sql('SELECT ' + ','.join("IFNULL(HEX(`" + column + "`),'NULL')" for column in columns[table])
                                              + ' FROM ' + table + ' ORDER BY ' + order).encode()).hexdigest()
                     for table, order in tables.items()}
            value['dynamic_redis'] = api.cache('EVAL', "local keys=redis.call('KEYS',ARGV[1]); table.sort(keys); local values={}; "
                "for _,key in ipairs(keys) do table.insert(values,key..':'..redis.sha1hex(redis.call('DUMP',key))) end; "
                "return redis.sha1hex(table.concat(values,'|'))", '0', 'sys:cache:dbconnect:dynamic:*')
            return value

        source = {'code': prefix, 'name': 'Synthetic infrastructure source', 'dbType': '1', 'dbDriver': 'com.mysql.jdbc.Driver',
                  'dbUrl': 'jdbc:mysql://127.0.0.1/synthetic_unconnected', 'dbName': 'synthetic',
                  'dbUsername': 'synthetic', 'dbPassword': 'synthetic-source-secret'}
        job = {'jobType': 'sample', 'cronExpression': '0 0 0 1 1 ? 2099', 'status': 0, 'description': prefix}
        source_routes = [('GET', '/list', None), ('GET', '/options', None), ('GET', '/queryById?id=' + source_id, None),
                         ('GET', '/exportXls', None), ('POST', '/exportXls', None), ('POST', '/importExcel', {}),
                         ('POST', '/add', source), ('PUT', '/edit', dict(source, id=source_id, name='forged')),
                         ('DELETE', '/delete?id=' + source_id, None), ('DELETE', '/deleteBatch?ids=' + source_id, None)]
        job_routes = [('GET', '/list', None), ('GET', '/types', None), ('GET', '/queryById?id=' + job_id, None),
                      ('GET', '/exportXls', None), ('POST', '/exportXls', None), ('POST', '/importExcel', {}),
                      ('POST', '/add', job), ('PUT', '/edit', dict(job, id=job_id, status=-1)),
                      ('DELETE', '/delete?id=' + job_id, None), ('DELETE', '/deleteBatch?ids=' + job_id, None),
                      ('GET', '/pause?' + urlencode({'jobClassName': SAMPLE}), None),
                      ('GET', '/resume?' + urlencode({'jobClassName': SAMPLE}), None)]

        def deny_all(actor):
            for base, routes in (('/sys/dataSource', source_routes), ('/sys/quartzJob', job_routes)):
                for method, suffix, body in routes:
                    before = snapshot()
                    status, result, _ = api.request(method, base + suffix, actor, body)
                    name = actor + ' denied ' + method + ' ' + base + suffix.split('?')[0]
                    check(name, status == 403 and result is not None and result.get('success') is False and result.get('code') == 403)
                    check(name + ' leaves SQL, dynamic Redis, and Quartz state unchanged', snapshot() == before)
            for suffix in ('', '/', '.json', '.js', ';fixture=1'):
                before = snapshot()
                route = '/online/cgreport/api/testConnection' + suffix
                status, result, _ = api.request('POST', route, actor,
                                               {'dbDriver': 'java.lang.String', 'dbUrl': 'jdbc:synthetic-no-driver'})
                # Full Boot disables suffix matching; standalone MVC tests deliberately also test
                # suffix-enabled handlers. Do not label a missing route as an authorization denial.
                denial = status == 403 and isinstance(result, dict) and result.get('success') is False and result.get('code') == 403
                boot_error = isinstance(result, dict) and set(result) == {'timestamp', 'status', 'error', 'message', 'path'} \
                    and isinstance(result.get('timestamp'), str) and result.get('path') == '/api' + route
                unmapped = suffix in ('.json', '.js') and status == 404 and boot_error \
                    and result.get('status') == 404 and result.get('error') == 'Not Found' and result.get('message') == 'No message available'
                invalid_matrix = suffix == ';fixture=1' and status == 400 and boot_error \
                    and result.get('status') == 400 and result.get('error') == 'Bad Request' and result.get('message') == 'Invalid request'
                kind = 'handler authorization denied 403' if denial else 'unmapped suffix 404' if unmapped \
                    else 'rejected matrix path 400' if invalid_matrix else 'unexpected response'
                online_routes.append({'actor': actor, 'suffix': suffix, 'classification': kind, 'http_status': status})
                check(actor + ' compiled Online JDBC ' + kind + ' ' + repr(suffix), denial or unmapped or invalid_matrix)
                check(actor + ' compiled Online JDBC rejection preserves infrastructure state ' + repr(suffix), snapshot() == before)

        original = snapshot()
        if getattr(args, 'expect_legacy', False):
            # Baseline mode is intentionally read-only through HTTP: no role grants,
            # management writes, resume/pause calls, arbitrary classes or executable jobs.
            observations = []
            failure = None
            try:
                assigned = sql("SELECT r.role_code FROM sys_role r JOIN sys_user_role ur ON r.id=ur.role_id "
                               "WHERE ur.user_id='fixture_student_a' ORDER BY r.role_code").splitlines()
                check('legacy actor is an ordinary student without infrastructure privileges', assigned == ['student'])
                api.login('student_a')
                sql('INSERT INTO sys_data_source(id,code,name,db_type,db_driver,db_url,db_name,db_username,db_password) VALUES ('
                    + ','.join(literal(v) for v in (source_id, prefix, source['name'], '1', source['dbDriver'], source['dbUrl'],
                                                    'synthetic', 'synthetic', source['dbPassword'])) + ')')
                # An inert metadata row is sufficient to demonstrate unauthorized reads.
                # Do not register a Quartz job or call the HTTP create/resume path.
                sql('INSERT INTO sys_quartz_job(id,job_class_name,cron_expression,status,del_flag,description) VALUES ('
                    + ','.join((literal(job_id), literal(SAMPLE), literal(job['cronExpression']), '-1', '0', literal(prefix))) + ')')
                for route in ('/sys/dataSource/queryById?id=' + source_id,
                              '/sys/dataSource/list?' + urlencode({'code': prefix})):
                    before = snapshot()
                    status, result, _ = api.request('GET', route, 'student_a')
                    successful = status == 200 and isinstance(result, dict) and result.get('success') is True
                    value = result.get('result') if successful else None
                    rows = value.get('records', []) if isinstance(value, dict) and 'records' in value else [value]
                    exposed = any(isinstance(row, dict) and row.get('id') == source_id
                                  and row.get('dbPassword') == source['dbPassword'] for row in rows)
                    name = 'legacy student reads synthetic source password through ' + route.split('?')[0]
                    check(name, successful and exposed)
                    check(name + ' without changing SQL, Redis or Quartz', snapshot() == before)
                    observations.append({'route': route.split('?')[0], 'http_status': status,
                                         'business_code': result.get('code') if isinstance(result, dict) else None,
                                         'synthetic_password_exposed': exposed})
                before = snapshot()
                status, result, _ = api.request('GET', '/sys/quartzJob/list?' + urlencode({'id': job_id}), 'student_a')
                successful = status == 200 and isinstance(result, dict) and result.get('success') is True
                rows = (result.get('result') or {}).get('records', []) if successful else []
                visible = any(isinstance(row, dict) and row.get('id') == job_id and row.get('jobClassName') == SAMPLE
                              and row.get('status') == -1 for row in rows)
                check('legacy student reads the inert synthetic Quartz task list', successful and visible)
                check('legacy Quartz read changes no SQL, Redis or scheduler state', snapshot() == before)
                observations.append({'route': '/sys/quartzJob/list', 'http_status': status,
                                     'business_code': result.get('code') if isinstance(result, dict) else None,
                                     'inert_task_visible': visible})
                before = snapshot()
                status, result, _ = api.request('POST', '/online/cgreport/api/testConnection', 'student_a',
                                               {'dbDriver': 'java.lang.String', 'dbUrl': 'jdbc:synthetic-no-driver'})
                reached = (status == 200 and isinstance(result, dict) and result.get('success') is False
                           and result.get('code') == 500 and 'No suitable driver' in result.get('message', '')
                           and 'jdbc:synthetic-no-driver' in result.get('message', ''))
                check('legacy student reaches packaged Online JDBC test without a network-capable URL', reached)
                check('legacy Online JDBC test changes no SQL, Redis or scheduler state', snapshot() == before)
                check('legacy verification has not scheduled an executable Quartz task', sql(
                    'SELECT COUNT(*) FROM QRTZ_JOB_DETAILS WHERE JOB_NAME IN (' + literal(SAMPLE) + ',' + literal(PARAMETER_SAMPLE) + ')') == '0')
                observations.append({'route': '/online/cgreport/api/testConnection', 'http_status': status,
                                     'business_code': result.get('code') if isinstance(result, dict) else None,
                                     'no_suitable_driver_reached': reached, 'network_capable_url': False})
            except Exception as error:
                failure = error
            finally:
                try:
                    # This mode never modifies scheduler tables, Redis, or any account/role rows.
                    sql('DELETE FROM sys_quartz_job WHERE id=' + literal(job_id))
                    sql('DELETE FROM sys_data_source WHERE id=' + literal(source_id))
                    check('legacy mode restores the original infrastructure state', snapshot() == original)
                except Exception as error:
                    if failure is None:
                        failure = error
                checks.append({'case': 'legacy baseline execution and restoration complete', 'passed': failure is None})
                passed = sum(item['passed'] for item in checks)
                report = {'observed_utc': datetime.now(timezone.utc).isoformat(),
                          'scope': 'owned synthetic legacy HTTP/MySQL/Redis/Quartz; limited read exposure and inert JDBC error',
                          'jar_sha256': api.jar_sha256, 'verifier_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                          'expected_legacy': True, 'production_connected': False, 'network_connection_attempted': False,
                          'passed': passed, 'failed': len(checks) - passed, 'total': len(checks), 'checks': checks,
                          'observations': observations, 'completed': failure is None,
                          'exception_type': type(failure).__name__ if failure is not None else None}
                args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
            if failure is not None:
                raise failure
            return

        try:
            for actor in ('admin', 'teacher_a', 'student_a'):
                api.login(actor)
            sql('INSERT INTO sys_data_source(id,code,name,db_type,db_driver,db_url,db_name,db_username,db_password) VALUES ('
                + ','.join(literal(v) for v in (source_id, prefix, source['name'], '1', source['dbDriver'], source['dbUrl'], 'synthetic', 'synthetic', source['dbPassword'])) + ')')
            sql('INSERT INTO sys_quartz_job(id,job_class_name,cron_expression,status,del_flag,description) VALUES ('
                + ','.join((literal(job_id), literal(SAMPLE), literal(job['cronExpression']), '-1', '0', literal(prefix))) + ')')
            api.cache('SET', cache_key, 'synthetic-cache-sentinel')
            for actor in ('student_a', 'teacher_a', 'admin'):
                deny_all(actor)
            if not role_id:
                role_id, created_role = prefix + '_role', True
                sql('INSERT INTO sys_role(id,role_code,role_name,role_level) VALUES (' + literal(role_id) + ",'dev','Synthetic ops',10)")
            sql('INSERT INTO sys_user_role(id,user_id,role_id) VALUES (' + literal(role_link) + ",'fixture_admin'," + literal(role_id) + ')')
            # Same login token gains/loses authority according to current database roles.
            detail = allowed('dev can read source without password', 'GET', '/sys/dataSource/queryById?id=' + source_id)
            check('source detail contains no password property or credential', 'dbPassword' not in detail and source['dbPassword'] not in json.dumps(detail))
            records = allowed('dev can list sources', 'GET', '/sys/dataSource/list')['records']
            check('source list contains no password property or credential', all('dbPassword' not in row for row in records) and source['dbPassword'] not in json.dumps(records))
            export_status, export_body = raw('GET', '/sys/dataSource/exportXls', 'admin')
            check('dev exports a real XLS without the source password or password column',
                  export_status == 200 and export_body.startswith(b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1')
                  and source['dbPassword'].encode() not in export_body
                  and source['dbPassword'].encode('utf-16le') not in export_body and '密码'.encode('utf-16le') not in export_body)
            allowed('dev creates source with server-generated identity', 'POST', '/sys/dataSource/add', dict(source, code=prefix + '_new', id='forged-source'))
            additional_source_id = sql('SELECT id FROM sys_data_source WHERE code=' + literal(prefix + '_new'))
            check('source create ignores caller identity', additional_source_id.isdigit() and additional_source_id != 'forged-source')
            allowed('dev creates a fixed task type', 'POST', '/sys/quartzJob/add', dict(job, jobType='sample-parameter', status=-1, id='forged-job'))
            additional_job_id = sql('SELECT id FROM sys_quartz_job WHERE job_class_name=' + literal(PARAMETER_SAMPLE))
            check('task create binds allowed class and ignores caller identity', additional_job_id.isdigit() and additional_job_id != 'forged-job')
            edited = dict(source, id=source_id, name='Synthetic edited source'); edited.pop('dbPassword')
            allowed('dev edits source with omitted password', 'PUT', '/sys/dataSource/edit', edited)
            check('omitted edit password is preserved in SQL', sql('SELECT db_password FROM sys_data_source WHERE id=' + literal(source_id)) == source['dbPassword'])
            check('successful source edit evicts derived Redis state', api.cache('EXISTS', cache_key) == '0')
            api.cache('SET', cache_key, 'synthetic-cache-sentinel')
            allowed('dev resumes the reviewed sample task', 'GET', '/sys/quartzJob/resume?' + urlencode({'jobClassName': SAMPLE}))
            check('actual Quartz has a waiting trigger', sql('SELECT TRIGGER_STATE FROM QRTZ_TRIGGERS WHERE JOB_NAME=' + literal(SAMPLE)) == 'WAITING')
            allowed('dev edits an existing task without changing its class', 'PUT', '/sys/quartzJob/edit', dict(job, id=job_id, description='Synthetic edited task'))
            check('task edit keeps a real Quartz trigger', sql('SELECT TRIGGER_STATE FROM QRTZ_TRIGGERS WHERE JOB_NAME=' + literal(SAMPLE)) == 'WAITING')
            # Repeat every negative route with a real scheduled job and a populated derived cache.
            deny_all('student_a')
            allowed('dev pauses sample task', 'GET', '/sys/quartzJob/pause?' + urlencode({'jobClassName': SAMPLE}))
            check('actual Quartz trigger is paused', sql('SELECT TRIGGER_STATE FROM QRTZ_TRIGGERS WHERE JOB_NAME=' + literal(SAMPLE)) == 'PAUSED')
            before = snapshot()
            status, result, _ = api.request('POST', '/sys/quartzJob/add', 'admin', dict(job, jobType='java.lang.Runtime'))
            check('dev cannot submit an arbitrary task class as type', result is not None and result.get('success') is False)
            check('invalid task type preserves SQL cache and scheduler', snapshot() == before)
            status, result, _ = api.request('POST', '/online/cgreport/api/testConnection', 'admin',
                                           {'dbDriver': 'java.lang.String', 'dbUrl': 'jdbc:synthetic-no-driver'})
            check('dev retains compiled Online connection-test consumer without network access',
                  status == 200 and result is not None and result.get('success') is False and 'No suitable driver' in result.get('message', ''))
            for suffix in ('.json', '.js', ';fixture=1'):
                before = snapshot()
                route = '/online/cgreport/api/testConnection' + suffix
                status, result, _ = api.request('POST', route, 'admin',
                                               {'dbDriver': 'java.lang.String', 'dbUrl': 'jdbc:synthetic-no-driver'})
                expected = 400 if suffix == ';fixture=1' else 404
                matching_shape = isinstance(result, dict) and set(result) == {'timestamp', 'status', 'error', 'message', 'path'} \
                    and result.get('path') == '/api' + route and result.get('status') == expected \
                    and result.get('error') == ('Bad Request' if expected == 400 else 'Not Found') \
                    and result.get('message') == ('Invalid request' if expected == 400 else 'No message available')
                observed = [row for row in online_routes if row['suffix'] == suffix and row['http_status'] == expected]
                # A privileged control confirms that unavailable aliases are not role-dependent
                # controller behavior. If this runtime enables suffix mapping, require the genuine
                # harmless driver error instead; the unprivileged handler must have returned 403.
                routed_control = not observed and status == 200 and isinstance(result, dict) \
                    and result.get('success') is False and result.get('code') == 500 \
                    and 'No suitable driver' in result.get('message', '') and 'jdbc:synthetic-no-driver' in result.get('message', '')
                check('dev control confirms Online alias routing ' + repr(suffix), status == expected and matching_shape or routed_control)
                check('dev Online alias control preserves infrastructure state ' + repr(suffix), snapshot() == before)
            sql('DELETE FROM sys_user_role WHERE id=' + literal(role_link))
            deny_all('admin')
            # Restore the temporary grant only to exercise authorized cleanup paths with the same token.
            sql('INSERT INTO sys_user_role(id,user_id,role_id) VALUES (' + literal(role_link) + ",'fixture_admin'," + literal(role_id) + ')')
            allowed('dev deletes scheduled task', 'DELETE', '/sys/quartzJob/delete?id=' + job_id)
            check('task deletion removes actual Quartz job', sql('SELECT COUNT(*) FROM QRTZ_JOB_DETAILS WHERE JOB_NAME=' + literal(SAMPLE)) == '0')
            allowed('dev deletes source', 'DELETE', '/sys/dataSource/delete?id=' + source_id)
            allowed('dev batch-deletes created sources', 'DELETE', '/sys/dataSource/deleteBatch?ids=' + additional_source_id)
            allowed('dev batch-deletes created tasks', 'DELETE', '/sys/quartzJob/deleteBatch?ids=' + additional_job_id)
        finally:
            # Only this probe's records may be removed, and every temporary role grant is restored.
            sql('DELETE FROM sys_user_role WHERE id=' + literal(role_link))
            if created_role:
                sql('DELETE FROM sys_role WHERE id=' + literal(role_id))
            sql('DELETE FROM QRTZ_CRON_TRIGGERS WHERE TRIGGER_NAME IN (' + literal(SAMPLE) + ',' + literal(PARAMETER_SAMPLE) + ')')
            sql('DELETE FROM QRTZ_TRIGGERS WHERE JOB_NAME IN (' + literal(SAMPLE) + ',' + literal(PARAMETER_SAMPLE) + ')')
            sql('DELETE FROM QRTZ_JOB_DETAILS WHERE JOB_NAME IN (' + literal(SAMPLE) + ',' + literal(PARAMETER_SAMPLE) + ')')
            sql('DELETE FROM sys_quartz_job WHERE id=' + literal(job_id))
            if additional_job_id:
                sql('DELETE FROM sys_quartz_job WHERE id=' + literal(additional_job_id))
            sql('DELETE FROM sys_data_source WHERE id=' + literal(source_id))
            if additional_source_id:
                sql('DELETE FROM sys_data_source WHERE id=' + literal(additional_source_id))
            api.cache('DEL', cache_key)
        check('original infrastructure state restored', snapshot() == original)
        report = {'observed_utc': datetime.now(timezone.utc).isoformat(), 'scope': 'owned synthetic HTTP/MySQL/Redis/Quartz',
                  'jar_sha256': api.jar_sha256, 'verifier_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  'production_connected': False, 'expected_legacy': False, 'passed': sum(item['passed'] for item in checks),
                  'failed': sum(not item['passed'] for item in checks), 'total': len(checks), 'checks': checks,
                  'online_route_observations': online_routes,
                  'online_route_counts': {kind: sum(row['classification'] == kind for row in online_routes) for kind in sorted({row['classification'] for row in online_routes})},
                  'remaining_scope': 'In-process connection-pool state and real XLS import/export are exercised by InfrastructureAdministrationTest; this probe does not inspect those in-process objects.'}
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--jar', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--expect-legacy', action='store_true')
    verify(parser.parse_args())
