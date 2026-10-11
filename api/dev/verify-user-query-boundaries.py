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
  try (Workbook book=WorkbookFactory.create(new File(args[0]))) {
   DataFormatter formatter=new DataFormatter();
   for(Sheet sheet:book) { int username=-1;
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
  }
 }
}''')
    command = [javac, '-encoding', 'UTF-8', '-cp', str(libraries / '*'), str(source)]
    built = subprocess.run(command, capture_output=True, timeout=60)
    if built.returncode:
        raise RuntimeError('Candidate POI export reader did not compile')
    java = str(Path(javac).parent / 'java')
    return [java, '-cp', str(directory) + os.pathsep + str(libraries / '*'), 'ReadUserExport']


def verify(args):
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
                usernames = {line.split('\t', 1)[1] for line in parsed.stdout.splitlines() if line.startswith('USER\t')}
                check('actual Excel exact user set ' + actor + str(parameters), usernames == expected)
        finally:
            for table in ('sys_user_role', 'sys_user_depart', 'sys_user'):
                sql('DELETE FROM ' + table + " WHERE id LIKE '" + prefix + "_%'")
        report = {'scope': 'owned synthetic HTTP/MySQL and actual POI Excel', 'production_connected': False,
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
