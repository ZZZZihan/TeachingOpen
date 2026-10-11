#!/usr/bin/env python3
"""Global fill/check/category management allow/deny checks on a synthetic candidate."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory
from urllib.parse import quote, urlencode
from uuid import uuid4
from local_http import FixtureApi
from local_runtime import mysql_command

helper_spec = importlib.util.spec_from_file_location('shared_resource_probe', Path(__file__).with_name('verify-shared-resource-boundaries.py'))
helper = importlib.util.module_from_spec(helper_spec)
helper_spec.loader.exec_module(helper)
DEPARTMENT_ADD = '/sys/sysDepart/add'


def q(value):
    # CONVERT inherits utf8mb4_0900_ai_ci with the same coercibility as our
    # schema's utf8mb4_general_ci columns. Bind only this synthetic literal.
    return "(CONVERT(X'" + str(value).encode().hex() + "' USING utf8mb4) COLLATE utf8mb4_general_ci)"


def sql_failure(stderr):
    # Preserve actionable error codes without printing SQL, values or credentials.
    error = re.search(r'\bERROR ([0-9]{1,5}) \(([A-Z0-9]{5})\)', stderr or '')
    detail = ': MySQL ' + error[1] + ' (' + error[2] + ')' if error else ''
    return RuntimeError('Global-rule synthetic SQL failed' + detail)


class OrganizationRuleFixture:
    """Borrow an existing rule unchanged, or own one exact temporary record."""
    def __init__(self, sql, prefix):
        self.sql = sql
        self.prefix = prefix
        self.preexisting = None
        self.created_id = None

    def ensure(self):
        existing = self.sql("SELECT id FROM sys_fill_rule WHERE rule_code='org_num_role'")
        self.preexisting = bool(existing)
        if existing:
            return existing
        # Register ownership before the write so an uncertain insert is cleaned too.
        self.created_id = self.prefix + '_org'
        self.sql('INSERT INTO sys_fill_rule(id,rule_name,rule_code,rule_class,rule_params) VALUES ('
                 + q(self.created_id) + ',' + q('Synthetic organization generator')
                 + ",'org_num_role'," + q('org.jeecg.modules.system.rule.OrgCodeRule') + ",'{}')")
        return self.created_id

    def cleanup(self):
        if self.created_id is not None:
            self.sql('DELETE FROM sys_fill_rule WHERE id=' + q(self.created_id)
                     + " AND rule_code='org_num_role'")


def verify(args):
    if args.expect_legacy:
        raise RuntimeError('Only fixed candidate normal authorization regressions are supported')
    if args.output.exists():
        raise RuntimeError('Refusing to replace an existing evidence report')
    results = []
    with FixtureApi(args.runtime.resolve(), args.jar) as api, TemporaryDirectory(prefix='global-rule-') as temporary:
        write = helper.workbook_writer(args.jar, Path(temporary), api.runtime)
        prefix = 'ruleprobe_' + uuid4().hex[:12]
        tables = ('sys_fill_rule', 'sys_check_rule', 'sys_category', 'sys_depart', 'sys_role', 'sys_user_role')

        def sql(statement):
            result = subprocess.run(mysql_command(api.runtime) + ['teachingopen_dev', '-e', statement],
                                    capture_output=True, text=True, timeout=20)
            if result.returncode:
                raise sql_failure(result.stderr)
            return result.stdout.strip()

        def snapshot():
            return {table: hashlib.sha256(sql('SELECT * FROM ' + table + ' ORDER BY id').encode()).hexdigest() for table in tables}

        def check(name, passed):
            results.append({'case': name, 'passed': bool(passed)})
            print(('PASS ' if passed else 'FAIL ') + name, flush=True)
            if not passed:
                raise AssertionError(name)

        def ok(response):
            return response[0] == 200 and response[1] is not None and response[1].get('success') is True

        def denied(name, call):
            before = snapshot()
            response = call()
            check(name, response[0] in (200, 403) and response[1] is not None and response[1].get('success') is False
                  and response[1].get('code') in (403, 510) and snapshot() == before)

        fill = {'ruleName': prefix, 'ruleCode': prefix, 'ruleClass': 'org.jeecg.modules.system.rule.OrgCodeRule', 'ruleParams': '{}'}
        check_rule = {'ruleName': prefix, 'ruleCode': prefix, 'ruleJson': json.dumps([
            {'digits': '*', 'pattern': '^[A-Za-z]{1,12}$', 'message': 'Letters only'}])}
        category = {'name': prefix, 'code': 'R' + uuid4().hex[:12].upper(), 'pid': '0'}
        definitions = {
            'fillRule': ('sys_fill_rule', 'rule_code', fill, ['规则名称', '规则Code', '规则实现类', '规则参数'],
                         [prefix, prefix + '_import', fill['ruleClass'], '{}']),
            'checkRule': ('sys_check_rule', 'rule_code', check_rule, ['规则名称', '规则Code', '规则JSON'],
                          [prefix, prefix + '_import', check_rule['ruleJson']]),
            'category': ('sys_category', 'name', category, ['类型名称', '类型编码', '父级节点'],
                         [prefix + '_import', category['code'] + 'A', '0'])}
        original = snapshot()
        organization_rule = OrganizationRuleFixture(sql, prefix)
        class_creation = {}
        try:
            organization_rule.ensure()
            for actor in ('admin', 'teacher_a', 'student_a'):
                api.login(actor)
            for resource, (table, lookup, payload, headers, row) in definitions.items():
                base = '/sys/' + resource
                check('administrator creates ' + resource, ok(api.request('POST', base + '/add', 'admin', payload)))
                ident = sql('SELECT id FROM ' + table + ' WHERE ' + lookup + '=' + q(prefix))
                check(resource + ' fixture created exactly once', bool(ident) and '\n' not in ident)
                excel = write(headers, [row])
                for actor in ('student_a', 'teacher_a'):
                    for method, path, data in [('GET', '/rootList' if resource == 'category' else '/list', None),
                                               ('GET', '/queryById?id=' + ident, None), ('GET', '/exportXls', None),
                                               ('POST', '/add', payload), ('PUT', '/edit', dict(payload, id=ident)),
                                               ('DELETE', '/delete?id=' + ident, None), ('DELETE', '/deleteBatch?ids=' + ident, None)]:
                        denied(actor + ' cannot manage ' + resource + path.split('?')[0],
                               lambda m=method, p=path, a=actor, d=data: api.request(m, base + p, a, d))
                    denied(actor + ' cannot import ' + resource, lambda a=actor: helper.multipart(api, base + '/importExcel', a, excel))
                check('administrator edits ' + resource, ok(api.request('PUT', base + '/edit', 'admin', dict(payload, id=ident))))
                check('administrator reads ' + resource, ok(api.request('GET', base + '/queryById?id=' + ident, 'admin')))
                check('administrator imports Excel for ' + resource, ok(helper.multipart(api, base + '/importExcel', 'admin', excel)))
                imported = sql('SELECT id FROM ' + table + ' WHERE ' + lookup + '=' + q(prefix + '_import'))
                check('administrator single deletes ' + resource, bool(imported) and ok(api.request('DELETE', base + '/delete?id=' + imported, 'admin')))
                check('administrator batch deletes ' + resource, ok(api.request('DELETE', base + '/deleteBatch?ids=' + ident, 'admin')))
            core = sql("SELECT id FROM sys_fill_rule WHERE rule_code='org_num_role'")
            check('required synthetic organization rule exists', bool(core) and '\n' not in core)
            denied('student cannot remove required class-number rule', lambda: api.request('DELETE', '/sys/fillRule/delete?id=' + core, 'student_a'))
            parent_code = sql("SELECT org_code FROM sys_depart WHERE id='fixture_school'")
            check('synthetic parent has a single valid organization code', bool(re.fullmatch(r'[A-Za-z0-9]+', parent_code)))
            created = api.request('POST', DEPARTMENT_ADD, 'admin', {'departName': prefix, 'parentId': 'fixture_school', 'orgCategory': '2'})
            generated = sql('SELECT id,org_code,parent_id FROM sys_depart WHERE depart_name=' + q(prefix)).splitlines()
            class_creation = {'http_status': created[0], 'business': {key: created[1].get(key) for key in ('success', 'code', 'message')}
                              if isinstance(created[1], dict) else None, 'parent_org_code': parent_code, 'generated_rows': generated}
            print('Synthetic class creation: ' + json.dumps(class_creation, ensure_ascii=False), flush=True)
            check('normal class creation still generates a department code', ok(created)
                  and sql('SELECT COUNT(*) FROM sys_depart WHERE depart_name=' + q(prefix)
                          + " AND parent_id='fixture_school' AND org_code LIKE " + q(parent_code + '%')
                          + ' AND LENGTH(org_code)>' + str(len(parent_code))) == '1')
            check('ordinary fill generator read remains available', ok(api.request('PUT', '/sys/fillRule/executeRuleByCode/org_num_role', 'teacher_a', {'parentId': 'fixture_school'})))
            check('ordinary category picker remains available', ok(api.request('GET', '/sys/category/loadTreeData?pid=0', 'student_a')))
            check('administrator recreates benign form checker', ok(api.request('POST', '/sys/checkRule/add', 'admin', check_rule)))
            check('ordinary form validation accepts normal input', ok(api.request('GET', '/sys/checkRule/checkByCode?' + urlencode({'ruleCode': prefix, 'value': 'Abc'}), 'student_a')))
            check('ordinary form validation rejects a nonmatching input', not ok(api.request('GET', '/sys/checkRule/checkByCode?' + urlencode({'ruleCode': prefix, 'value': '123'}), 'student_a')))
            checker_id = sql('SELECT id FROM sys_check_rule WHERE rule_code=' + q(prefix))
            for label, value, pattern in [('punctuation and Unicode', 'A+B% C中文', r'^A\+B% C中文$'),
                                           ('literal percent escape', '%41', '^%41$'),
                                           ('256 Unicode characters', '中' * 256, '^中{256}$')]:
                configured = dict(check_rule, id=checker_id, ruleJson=json.dumps([
                    {'digits': '*', 'pattern': pattern, 'message': 'Exact fixture value required'}]))
                check('administrator configures ' + label + ' checker', ok(api.request('PUT', '/sys/checkRule/edit', 'admin', configured)))
                # Match validateCheckRule's encodeURIComponent followed by Axios query encoding.
                parameters = {'ruleCode': prefix, 'value': quote(value, safe="-_.!~*'()")}
                before = snapshot()
                check('existing form transport preserves ' + label,
                      ok(api.request('GET', '/sys/checkRule/checkByCode?' + urlencode(parameters), 'student_a')) and snapshot() == before)
            for value, message in [('%', '校验值编码不正确'), ('a' * 257, '校验值过长')]:
                before = snapshot()
                response = api.request('GET', '/sys/checkRule/checkByCode?' + urlencode({'ruleCode': prefix, 'value': value}), 'student_a')
                check('malformed or oversized checker input is controlled: ' + message,
                      not ok(response) and response[1] is not None and response[1].get('message') == message and snapshot() == before)
            before = snapshot()
            response = api.request('POST', '/sys/fillRule/add', 'admin', dict(fill, ruleClass='java.lang.String'))
            check('unsupported rule class is rejected before a write', not ok(response) and snapshot() == before)
            headers = definitions['fillRule'][3]
            invalid = write(headers, [[prefix, prefix + '_valid', fill['ruleClass'], '{}'], [prefix, prefix + '_bad', 'java.lang.String', '{}']])
            before = snapshot()
            check('mixed invalid fill-rule Excel writes no partial records', not ok(helper.multipart(api, '/sys/fillRule/importExcel', 'admin', invalid)) and snapshot() == before)
            dev = sql("SELECT id FROM sys_role WHERE role_code='dev' ORDER BY id LIMIT 1")
            if not dev:
                dev = prefix + '_dev'
                sql('INSERT INTO sys_role(id,role_code,role_name) VALUES (' + q(dev) + ",'dev','Synthetic dev')")
            sql('INSERT INTO sys_user_role(id,user_id,role_id) VALUES (' + q(prefix) + ",'fixture_teacher_a'," + q(dev) + ')')
            check('live dev grant enables rule management with same token', ok(api.request('POST', '/sys/fillRule/add', 'teacher_a', fill)))
            sql('DELETE FROM sys_user_role WHERE id=' + q(prefix))
            denied('same token revocation disables global rule management', lambda: api.request('POST', '/sys/fillRule/add', 'teacher_a', fill))
        finally:
            for table, column in [('sys_fill_rule', 'rule_code'), ('sys_check_rule', 'rule_code'), ('sys_category', 'name'), ('sys_depart', 'depart_name')]:
                sql('DELETE FROM ' + table + ' WHERE ' + column + ' LIKE ' + q(prefix + '%'))
            sql('DELETE FROM sys_user_role WHERE id=' + q(prefix))
            sql('DELETE FROM sys_role WHERE id=' + q(prefix + '_dev'))
            organization_rule.cleanup()
            check('all synthetic rule and department changes are cleaned', snapshot() == original)
        args.output.write_text(json.dumps({'scope': 'owned synthetic global configuration management and ordinary form/class workflows',
                                           'expected_legacy': False, 'production_connected': False, 'jar_sha256': api.jar_sha256,
                                           'organization_rule_fixture': {'preexisting': organization_rule.preexisting,
                                                                        'temporary_created': organization_rule.created_id is not None,
                                                                        'restored': True},
                                           'class_creation': class_creation,
                                           'verifier_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                                           'passed': len(results), 'failed': 0, 'checks': results}, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--jar', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--expect-legacy', action='store_true')
    verify(parser.parse_args())
