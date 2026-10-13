#!/usr/bin/env python3
"""Query SQL, private profile and department boundaries on the owned synthetic runtime."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import uuid4
from zipfile import ZipFile
from local_http import FixtureApi
from local_runtime import mysql_command


def excel_reader(jar, directory, runtime):
    """Use the candidate's real POI dependency to inspect actual HTTP Excel bytes."""
    libraries = directory / 'lib'
    libraries.mkdir()
    with ZipFile(jar) as archive:
        for item in archive.namelist():
            if item.startswith('BOOT-INF/lib/') and item.endswith('.jar'):
                (libraries / Path(item).name).write_bytes(archive.read(item))
    candidates = sorted((runtime / 'tools').glob('*jdk*/Contents/Home/bin/javac'))
    javac = (str(Path(os.environ['JAVA_HOME']) / 'bin/javac') if os.environ.get('JAVA_HOME')
             else str(candidates[0]) if candidates else shutil.which('javac'))
    if not javac:
        raise RuntimeError('Java 8 compiler is required for actual Excel inspection')
    source = directory / 'ReadUserExport.java'
    source.write_text('''import java.io.*; import org.apache.poi.ss.usermodel.*;
public class ReadUserExport {
 public static void main(String[] args) throws Exception {
  try (InputStream input=new FileInputStream(args[0])) {
   Workbook book=WorkbookFactory.create(input);
   try {
   DataFormatter formatter=new DataFormatter();
   for(int index=0;index<book.getNumberOfSheets();index++) {
    Sheet sheet=book.getSheetAt(index); int username=-1;
    for(Row row:sheet) {
     if(username < 0) {
      for(Cell cell:row) if("登录账号".equals(formatter.formatCellValue(cell))) {
       username=cell.getColumnIndex();
       for(Cell header:row) System.out.println("HEADER\\t"+formatter.formatCellValue(header));
       break;
      }
     } else { String value=formatter.formatCellValue(row.getCell(username));
      if(!value.isEmpty()) System.out.println("USER\\t"+value);
     }
    }
   }
   } finally { if(book instanceof Closeable) ((Closeable)book).close(); }
  }
 }
}''')
    command = [javac, '-encoding', 'UTF-8', '-cp', str(libraries / '*'), str(source)]
    built = subprocess.run(command, capture_output=True, timeout=60)
    if built.returncode:
        raise RuntimeError('Candidate POI export reader did not compile: ' + built.stderr.decode('utf-8', errors='replace')[:4000])
    java = str(Path(javac).parent / 'java')
    return [java, '-cp', str(directory) + os.pathsep + str(libraries / '*'), 'ReadUserExport']


def verify_legacy(args):
    """Read-only before comparison. Never runs the repair-only mutations or exports."""
    checks = []
    observations = {}
    with FixtureApi(args.runtime.resolve(), args.jar) as api:
        def sql(statement):
            result = subprocess.run(mysql_command(api.runtime) + ['teachingopen_dev', '-e', statement],
                                    capture_output=True, text=True, timeout=20)
            if result.returncode:
                raise RuntimeError('Synthetic legacy boundary SQL failed')
            return result.stdout.strip()

        def check(name, passed):
            checks.append({'case': name, 'passed': bool(passed)})
            print(('PASS ' if passed else 'FAIL ') + name, flush=True)
            if not passed:
                raise AssertionError(name)

        def snapshot():
            return {table: hashlib.sha256(sql('SELECT * FROM ' + table + ' ORDER BY id').encode()).hexdigest()
                    for table in ('sys_user', 'sys_user_role', 'sys_user_depart', 'sys_depart')}

        def cache_snapshot():
            return api.cache('EVAL', "local keys={}; for _,pattern in ipairs(ARGV) do "
                             "for _,key in ipairs(redis.call('KEYS',pattern)) do table.insert(keys,key) end end; "
                             "table.sort(keys); local values={}; for _,key in ipairs(keys) do "
                             "table.insert(values,key..':'..redis.sha1hex(redis.call('DUMP',key))) end; "
                             "return redis.sha1hex(table.concat(values,'|'))", '0', 'sys:cache:user::*',
                             'shiro:cache:org.jeecg.modules.shiro.authc.ShiroRealm.*')

        def query(path, actor, **parameters):
            return api.request('GET', path + '?' + urlencode(parameters), actor)

        def ids(result):
            return {row['id'] for row in result.get('result', {}).get('records', [])}

        check('legacy comparison is restricted to the five synthetic accounts',
              sql('SELECT username FROM sys_user ORDER BY username').splitlines()
              == ['fixture_admin', 'fixture_student_a', 'fixture_student_b', 'fixture_teacher_a', 'fixture_teacher_b'])
        for actor in ('admin', 'teacher_a'):
            api.login(actor)
            status, result, _ = api.request('GET', '/teaching/user/info', actor)
            check('legacy comparison warms own authenticated cache ' + actor,
                  status == 200 and result is not None and result.get('success') is True)
        original, cached = snapshot(), cache_snapshot()
        try:
            status, result, _ = query('/sys/user/queryByOrgCode', 'teacher_a', orgCode='A99A01', pageSize=100)
            check('legacy canonical organization control returns only class A',
                  status == 200 and result is not None and result.get('success') is True
                  and ids(result) == {'fixture_student_a', 'fixture_teacher_a'})
            # Contains no statement terminator, comment, write or external channel.
            # Both branches name only the owned class fixtures. With interpolation the
            # second branch becomes SQL; parameter binding treats the entire input as data.
            payload = "A99A01%' OR sys_depart.org_code LIKE 'A99A02"
            status, result, _ = query('/sys/user/queryByOrgCode', 'teacher_a', orgCode=payload, pageSize=100)
            expanded = (status == 200 and result is not None and result.get('success') is True
                        and ids(result) == {'fixture_student_a', 'fixture_teacher_a', 'fixture_student_b', 'fixture_teacher_b'})
            observations['organization_expression'] = {'expanded_to_other_fixture_class': expanded,
                                                       'http_status': status,
                                                       'business_code': result.get('code') if result else None}
            check('legacy interpolated organization expression expands the synthetic class scope', expanded)
            # A nonexistent identifier is sufficient to prove that a client field has
            # reached the database, without reading credentials or any unrelated table.
            advanced = json.dumps([{'field': 'nonexistent_boundary_column', 'rule': 'eq', 'val': 'synthetic'}])
            status, result, _ = query('/sys/user/list', 'admin', superQueryParams=advanced)
            message = str(result.get('message', '')).lower() if result else ''
            database_reached = (result is not None and result.get('success') is False
                                and 'unknown column' in message and 'nonexistent_boundary_column' in message)
            observations['advanced_column'] = {'database_rejected_unknown_identifier': database_reached,
                                               'http_status': status,
                                               'business_code': result.get('code') if result else None}
            check('legacy advanced field reaches MySQL as an identifier', database_reached)
        finally:
            # This mode intentionally makes no SQL/Redis writes beyond normal login.
            # Assert equality even on failed observations; FixtureApi closes tokens.
            check('legacy comparison preserves all account and membership records', snapshot() == original)
            check('legacy comparison preserves warmed user and authorization cache values', cache_snapshot() == cached)
        report = {'scope': 'owned five-account synthetic read-only before comparison',
                  'expected_legacy': True, 'production_connected': False,
                  'interpretation': 'Expected defects observed only in this owned legacy JAR/runtime; not evidence of a production attack or a passing candidate.',
                  'jar_sha256': api.jar_sha256, 'verifier_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  'passed': len(checks), 'failed': 0, 'checks': checks, 'observations': observations}
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')


def verify_department_selection(api, sql, check):
    def snapshot():
        return {table: hashlib.sha256(sql('SELECT * FROM ' + table + ' ORDER BY id').encode()).hexdigest()
                for table in ('sys_user', 'sys_user_depart')}

    def cache_snapshot():
        return api.cache('EVAL', "local out={}; for _,key in ipairs(KEYS) do "
                         "table.insert(out,key..':'..redis.sha1hex(redis.call('DUMP',key) or '')) end; "
                         "return redis.sha1hex(table.concat(out,'|'))", '2',
                         'sys:cache:user::fixture_student_a', 'sys:cache:user::fixture_student_b')

    for actor in ('student_a', 'student_b'):
        api.request('GET', '/teaching/user/info', actor)
    for body in ({'username': 'fixture_student_b', 'orgCode': 'A99A02'},
                 {'username': 'fixture_student_a', 'orgCode': 'A99A02'},
                 {'orgCode': 'A99'}, {'orgCode': "A99A01' OR 1=1 --"}):
        before, cached = snapshot(), cache_snapshot()
        status, result, _ = api.request('PUT', '/sys/selectDepart', 'student_a', body)
        check('department selection requires current identity and membership ' + str(body),
              status == 403 or result is not None and result.get('success') is False and result.get('code') in (403, 510))
        check('denied department selection preserves database ' + str(body), snapshot() == before)
        check('denied department selection preserves cache values ' + str(body), cache_snapshot() == cached)
    member = 'query_select_' + uuid4().hex[:10]
    original = sql("SELECT IFNULL(HEX(org_code),'NULL') FROM sys_user WHERE id='fixture_student_a'")
    try:
        sql("INSERT INTO sys_user_depart(id,user_id,dep_id) VALUES ('" + member + "','fixture_student_a','fixture_class_b')")
        status, result, _ = api.request('PUT', '/sys/selectDepart', 'student_a', {'orgCode': 'A99A02'})
        check('own newly joined organization can be selected', status == 200 and result is not None and result.get('success') is True)
        check('own organization selection is persisted', sql("SELECT org_code FROM sys_user WHERE id='fixture_student_a'") == 'A99A02')
        sql("DELETE FROM sys_user_depart WHERE id='" + member + "'")
        before, cached = snapshot(), cache_snapshot()
        status, result, _ = api.request('PUT', '/sys/selectDepart', 'student_a', {'orgCode': 'A99A02'})
        check('revoked membership rejects with the same token',
              status == 403 or result is not None and result.get('success') is False and result.get('code') in (403, 510))
        check('revoked selection preserves database and cache', snapshot() == before and cache_snapshot() == cached)
    finally:
        sql("DELETE FROM sys_user_depart WHERE id='" + member + "'")
        sql("UPDATE sys_user SET org_code=" + ('NULL' if original == 'NULL' else "CONVERT(X'" + original + "' USING utf8mb4)")
            + " WHERE id='fixture_student_a'")
        api.cache('DEL', 'sys:cache:user::fixture_student_a')


def verify_private_profiles(api, sql, check):
    columns = ('avatar', 'sex', 'birthday', 'email', 'phone', 'telephone', 'school', 'work_no', 'post', 'create_time', 'update_time')
    originals = {}
    prefix = 'profile_' + uuid4().hex[:10]
    def route(path, **parameters):
        return path + '?' + urlencode(parameters)
    def read(path, actor):
        status, result, _ = api.request('GET', path, actor)
        check('profile allowed ' + actor + ' ' + path, status == 200 and result is not None and result.get('success') is True)
        return result['result']
    def denied(path, actor):
        status, result, _ = api.request('GET', path, actor)
        check('private profile authorization rejects ' + actor + ' ' + path,
              status == 403 or result is not None and result.get('success') is False and result.get('code') in (403, 510))
    try:
        for index, actor in enumerate(('student_a', 'student_b')):
            identifier = 'fixture_' + actor
            originals[identifier] = sql('SELECT ' + ','.join("IFNULL(HEX(CAST(`" + col + "` AS BINARY)),'NULL')" for col in columns)
                                        + " FROM sys_user WHERE id='" + identifier + "'").split('\t')
            phone = '18' + str(100000000 + int(uuid4().hex[:6], 16))[-9:]
            sql("UPDATE sys_user SET avatar='',sex=1,birthday='2001-01-01',email='" + prefix + str(index) + "@example.test',phone='" + phone
                + "',telephone='synthetic',school='synthetic',work_no='" + prefix + str(index)
                + "',post='synthetic',create_time='2026-01-01',update_time='2026-01-01' WHERE id='" + identifier + "'")
            api.cache('DEL', 'sys:cache:user::' + identifier)
        target = '/sys/user/queryById?id=fixture_student_a'
        base_fields = {'id', 'username', 'realname', 'avatar'}
        own_fields = base_fields | {'sex', 'birthday', 'email', 'phone', 'telephone', 'school', 'workNo', 'post', 'orgCode'}
        admin_fields = own_fields | {'status', 'delFlag', 'userIdentity', 'departIds', 'createTime', 'updateTime'}
        check('own profile has exact allowed fields', set(read(target, 'student_a')) == own_fields)
        check('managed student has exact minimal fields', set(read(target, 'teacher_a')) == base_fields)
        check('administrator profile has exact allowed fields', set(read(target, 'admin')) == admin_fields)
        denied(target, 'student_b')
        denied(target, 'teacher_b')
        # Same-class membership still does not grant an ordinary student private profiles.
        denied('/sys/user/queryById?id=fixture_teacher_a', 'student_a')
        for actor in ('student_a', 'teacher_a'):
            denied('/sys/user/queryByIds?userIds=fixture_student_a,fixture_student_b', actor)
        returned = read('/sys/user/queryByIds?userIds=fixture_student_a,fixture_teacher_a', 'teacher_a')
        check('authorized batch returns complete known IDs', {row['id'] for row in returned} == {'fixture_student_a', 'fixture_teacher_a'})
        check('authorized batch does not disclose student contacts', set(next(row for row in returned if row['id'] == 'fixture_student_a')) == base_fields)
        status, result, _ = api.request('GET', route('/sys/user/queryByIds', userIds=','.join(['fixture_student_a'] * 101)), 'admin')
        check('oversized profile batch rejected before reads', status == 200 and result is not None and result.get('success') is False
              and result.get('message') == '请选择1至100个目标')
        for path, parameter in (('/sys/user/departUserList', 'depId'), ('/sys/user/queryUserByDepId', 'id')):
            denied(route(path, **{parameter: 'fixture_class_b'}), 'teacher_a')
            denied(route(path, **{parameter: 'fixture_class_a'}), 'student_a')
            response = read(route(path, **{parameter: 'fixture_class_a'}), 'teacher_a')
            records = response['records'] if isinstance(response, dict) else response
            student = next(row for row in records if row['id'] == 'fixture_student_a')
            check('department alias does not disclose contact fields ' + path, not {'birthday', 'email', 'phone', 'password', 'salt'} & set(student))
        for path in ('/sys/user/appUserList', '/sys/user/userRoleList?roleId=fixture_role_student'):
            denied(path, 'student_a'); denied(path, 'teacher_a'); read(path, 'admin')
        for path in ('/sys/user/queryUserRole?userid=fixture_student_b', '/sys/user/userDepartList?userId=fixture_student_b'):
            denied(path, 'student_a'); denied(path, 'teacher_a'); read(path, 'admin')
        section = read('/sys/user/getUserSectionInfoByToken?token=not-the-current-user', 'student_a')
        check('section info always uses authenticated principal', section['sysUserId'] == 'fixture_student_a')
        before = sql("SELECT depart_ids FROM sys_user WHERE id='fixture_teacher_a'")
        try:
            sql("UPDATE sys_user SET depart_ids='fixture_class_b' WHERE id='fixture_teacher_a'")
            denied(target, 'teacher_a')
            denied('/sys/user/queryByOrgCode?orgCode=A99A01', 'teacher_a')
        finally:
            sql("UPDATE sys_user SET depart_ids=CONVERT(X'" + before.encode().hex() + "' USING utf8mb4) WHERE id='fixture_teacher_a'")
            api.cache('DEL', 'sys:cache:user::fixture_teacher_a')
    finally:
        for identifier, values in originals.items():
            assignments = ["`" + col + "`=" + ('NULL' if value == 'NULL' else "CONVERT(X'" + value + "' USING utf8mb4)")
                           for col, value in zip(columns, values)]
            sql('UPDATE sys_user SET ' + ','.join(assignments) + " WHERE id='" + identifier + "'")
            api.cache('DEL', 'sys:cache:user::' + identifier)


def verify(args):
    if getattr(args, 'expect_legacy', False):
        return verify_legacy(args)
    checks = []
    with FixtureApi(args.runtime.resolve(), args.jar) as api, TemporaryDirectory(prefix='query-boundary-') as temporary:
        def sql(statement):
            result = subprocess.run(mysql_command(api.runtime) + ['teachingopen_dev', '-e', statement],
                                    capture_output=True, text=True, timeout=30)
            if result.returncode:
                raise RuntimeError('Synthetic query-boundary SQL failed')
            return result.stdout.strip()

        def check(name, passed):
            checks.append({'case': name, 'passed': bool(passed)})
            print(('PASS ' if passed else 'FAIL ') + name, flush=True)
            if not passed:
                raise AssertionError(name)

        def route(path, **parameters):
            return path + '?' + urlencode(parameters)

        def read(path, actor):
            status, result, _ = api.request('GET', path, actor)
            check('allowed ' + actor + ' ' + path, status == 200 and result is not None and result.get('success') is True)
            return result['result']

        def denied(path, actor):
            status, result, _ = api.request('GET', path, actor)
            check('authorization rejects ' + actor + ' ' + path,
                  status == 403 or result is not None and result.get('success') is False and result.get('code') in (403, 510))

        for actor in ('admin', 'teacher_a', 'teacher_b', 'student_a', 'student_b'):
            api.login(actor)
        for path in ('/sys/user/queryByOrgCode', '/sys/user/queryByOrgCodeForAddressList'):
            for code in ("A99A01' OR 1=1 --", 'A99%', 'A99A02', 'A9'):
                denied(route(path, orgCode=code), 'teacher_a')
            denied(route(path, orgCode='A99A01'), 'student_a')
            response = read(route(path, orgCode='A99A01', pageSize=100), 'teacher_a')
            records = response['records']
            ids = {r.get('id', r.get('userId')) for r in records}
            expected = set(sql("SELECT u.id FROM sys_user u JOIN sys_user_depart ud ON ud.user_id=u.id "
                               "WHERE ud.dep_id='fixture_class_a' AND u.del_flag=0").splitlines())
            check('authorized canonical organization rows ' + path, ids == expected)
        for path in ('/sys/dict/list', '/sys/user/list'):
            for field in ('id) OR 1=1 --', 'nonexistent_field', '(select 1)', 'sys_user.password'):
                advanced = json.dumps([{'field': field, 'rule': 'eq', 'val': 'x'}])
                for parameter in ({'column': field, 'order': 'asc'}, {'superQueryParams': advanced}):
                    status, result, _ = api.request('GET', route(path, **parameter), 'admin')
                    check('entity columns reject before SQL ' + path + ' ' + str(parameter),
                          status == 200 and result is not None and result.get('success') is False
                          and result.get('message') == '不支持的查询字段')
        response = read(route('/sys/user/list', column='createTime', order='desc',
                              superQueryParams=json.dumps([{'field': 'username', 'rule': 'eq', 'val': "' OR 1=1 --"}])), 'admin')
        check('advanced hostile value is a literal and has no matches', response['records'] == [])
        for field in ('id) OR 1=1 --', '(select 1)', 'nonexistent_field'):
            status, result, _ = api.request('GET', route('/sys/category/loadOne', field=field, val='x'), 'admin')
            check('category single-column query rejects expression ' + field,
                  status == 200 and result is not None and result.get('success') is False)
            status, result, _ = api.request('GET', route('/sys/category/loadTreeData', pid='0', condition=json.dumps({field: 'x'})), 'admin')
            check('category tree rejects expression before mapper ' + field,
                  status == 200 and result is not None and result.get('success') is False
                  and result.get('message') == '不支持的查询字段')
        for selector in ('roleId', 'departId'):
            response = read(route('/sys/user/list', **{selector: "x') OR 1=1 --"}), 'admin')
            check('hostile relationship ID is a bound literal ' + selector, response['records'] == [])

        verify_department_selection(api, sql, check)
        verify_private_profiles(api, sql, check)
        prefix = 'query_boundary_' + uuid4().hex[:10]
        directory = Path(temporary)
        jar = (args.jar or Path(__file__).resolve().parents[1] / 'jeecg-boot-module-system/target/teaching-open-2.8.0.jar').resolve()
        reader = excel_reader(jar, directory, api.runtime)
        try:
            for index in range(101):
                identifier = prefix + '_' + str(index)
                sql("INSERT INTO sys_user(id,username,realname,status,del_flag) VALUES ('" + identifier + "','" + identifier + "','synthetic',1,0)")
                sql("INSERT INTO sys_user_role(id,user_id,role_id) VALUES ('" + identifier + "','" + identifier + "','fixture_role_student')")
                sql("INSERT INTO sys_user_depart(id,user_id,dep_id) VALUES ('" + identifier + "','" + identifier + "','fixture_class_a')")
            cases = [('admin', {}), ('admin', {'roleId': 'fixture_role_student'}),
                     ('admin', {'departId': 'fixture_class_a'}),
                     ('admin', {'roleId': 'fixture_role_student', 'departId': 'fixture_class_a'}),
                     ('teacher_a', {'roleId': 'fixture_role_student'}),
                     ('teacher_a', {'departId': 'fixture_class_b'})]
            for index, (actor, parameters) in enumerate(cases):
                predicates = ["u.del_flag=0", "u.username<>'_reserve_user_external'"]
                if parameters.get('roleId'):
                    predicates.append("EXISTS(SELECT 1 FROM sys_user_role r WHERE r.user_id=u.id AND r.role_id='fixture_role_student')")
                if parameters.get('departId'):
                    predicates.append("EXISTS(SELECT 1 FROM sys_user_depart d WHERE d.user_id=u.id AND d.dep_id='" + parameters['departId'] + "')")
                if actor == 'teacher_a':
                    predicates.append("EXISTS(SELECT 1 FROM sys_user_depart a WHERE a.user_id=u.id AND a.dep_id='fixture_class_a')")
                expected = set(sql('SELECT u.username FROM sys_user u WHERE ' + ' AND '.join(predicates)).splitlines())
                list_response = read(route('/sys/user/list', pageSize=100, **parameters), actor)
                check('list relationship total ' + actor + str(parameters), list_response['total'] == len(expected))
                path = route('/sys/user/exportXls', **parameters)
                request = Request('http://127.0.0.1:' + str(api.ports['backend']) + '/api' + path,
                                  headers={'X-Access-Token': api.tokens[actor]})
                with urlopen(request, timeout=60) as response:
                    content = response.read()
                    check('actual Excel HTTP success ' + actor + str(parameters), response.status == 200 and content[:8] == bytes.fromhex('d0cf11e0a1b11ae1'))
                export = directory / (str(index) + '.xls')
                export.write_bytes(content)
                parsed = subprocess.run(reader + [str(export)], capture_output=True, text=True, timeout=30)
                check('candidate POI reads actual Excel ' + str(index), parsed.returncode == 0)
                headers = {line.split('\t', 1)[1] for line in parsed.stdout.splitlines() if line.startswith('HEADER\t')}
                check('Excel never exposes password column ' + str(index), '密码' not in headers)
                if actor == 'teacher_a':
                    check('teacher Excel omits private contact columns ' + str(index), not {'生日', '电子邮件', '电话', '座机号'} & headers)
                usernames = {line.split('\t', 1)[1] for line in parsed.stdout.splitlines() if line.startswith('USER\t')}
                check('actual Excel exact user set ' + actor + str(parameters), usernames == expected)
        finally:
            for table in ('sys_user_role', 'sys_user_depart', 'sys_user'):
                sql('DELETE FROM ' + table + " WHERE id LIKE '" + prefix + "_%'")
        report = {'scope': 'owned synthetic HTTP/MySQL and actual POI Excel', 'production_connected': False, 'expected_legacy': False,
                  'jar_sha256': api.jar_sha256, 'verifier_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  'passed': len(checks), 'failed': 0, 'checks': checks}
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--jar', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--expect-legacy', action='store_true')
    verify(parser.parse_args())
