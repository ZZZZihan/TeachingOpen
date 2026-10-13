#!/usr/bin/env python3
"""Synthetic HTTP regression for ancillary global management boundaries.

Requires exclusive FixtureApi access. Cloud uploads use an empty multipart body,
so even the unprotected implementation cannot reach a cloud client; actual file
upload/delete success is tested with mocked clients in the Java suite. Existing
OSS objects are never passed to an allowed HTTP deletion. No cloud requests.
"""
import argparse
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from xml.sax.saxutils import escape
from zipfile import ZipFile, ZIP_DEFLATED

from local_http import FixtureApi
from local_runtime import mysql_command

PREFIX = 'fixture_gm_'
MARKER = PREFIX + 'private_metadata'
TABLES = ('sys_user_agent', 'sys_position', 'oss_file', 'sys_user_role', 'sys_role', 'sys_log')


def excel_reader(jar, directory, runtime):
    """Compile the workbook cell reader against this exact candidate's POI runtime."""
    libraries = directory / 'lib'
    libraries.mkdir()
    with ZipFile(jar) as archive:
        for name in archive.namelist():
            if name.startswith('BOOT-INF/lib/') and name.endswith('.jar') and name.count('/') == 2:
                (libraries / Path(name).name).write_bytes(archive.read(name))
    candidates = sorted((runtime / 'tools').glob('*jdk*/Contents/Home/bin/javac'))
    javac = (str(Path(os.environ['JAVA_HOME']) / 'bin/javac') if os.environ.get('JAVA_HOME')
             else str(candidates[0]) if candidates else shutil.which('javac'))
    if not javac:
        raise RuntimeError('A local JDK is required to inspect actual exported spreadsheets')
    built = subprocess.run([javac, '-proc:none', '-encoding', 'UTF-8', '-cp', str(libraries / '*'),
                            '-d', str(directory), str(Path(__file__).with_name('ReadSpreadsheetCells.java'))],
                           capture_output=True, timeout=60)
    if built.returncode:
        raise RuntimeError('Candidate POI spreadsheet reader did not compile')
    command = [str(Path(javac).parent / 'java'), '-Djava.awt.headless=true', '-cp',
               str(directory) + os.pathsep + str(libraries / '*'), 'ReadSpreadsheetCells']

    def read(data):
        source = directory / 'response-spreadsheet'
        source.write_bytes(data)
        parsed = subprocess.run(command + [str(source)], capture_output=True, timeout=30)
        if parsed.returncode:
            return None
        try:
            return [base64.b64decode(line, validate=True).decode('utf-8') for line in parsed.stdout.splitlines()]
        except (ValueError, UnicodeDecodeError):
            return None
    return read


def workbook(kind):
    rows = [['Synthetic import'], [], ['职务编码', '职务名称'] if kind == 'position' else ['用户名', '代理人用户名'],
            [PREFIX + 'import_' + kind, MARKER]]
    cells = ['<row r="' + str(row) + '">' + ''.join('<c r="' + chr(65 + col) + str(row)
             + '" t="inlineStr"><is><t>' + escape(value) + '</t></is></c>' for col, value in enumerate(values))
             + '</row>' for row, values in enumerate(rows, 1)]
    output = io.BytesIO()
    with ZipFile(output, 'w', ZIP_DEFLATED) as archive:
        archive.writestr('[Content_Types].xml', '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>')
        archive.writestr('_rels/.rels', '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        archive.writestr('xl/workbook.xml', '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Fixture" sheetId="1" r:id="rId1"/></sheets></workbook>')
        archive.writestr('xl/_rels/workbook.xml.rels', '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>')
        archive.writestr('xl/styles.xml', '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts><fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills><borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/></cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>')
        archive.writestr('xl/worksheets/sheet1.xml', '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>' + ''.join(cells) + '</sheetData></worksheet>')
    return output.getvalue()


def verify(args):
    if args.output.exists():
        raise RuntimeError('Preserve existing global management evidence')
    cases, error, exports = [], None, []

    def check(name, passed):
        cases.append({'case': name, 'passed': bool(passed)})
        print(('PASS ' if passed else 'FAIL ') + name, flush=True)
        if not passed:
            raise AssertionError(name)

    with FixtureApi(args.runtime.resolve(), args.jar) as api, TemporaryDirectory(prefix='teachingopen-management-export-') as temp:
        read_spreadsheet = excel_reader(args.jar.resolve(), Path(temp), api.runtime)
        def sql(statement):
            result = subprocess.run(mysql_command(api.runtime) + ['teachingopen_dev'], input=statement,
                                    capture_output=True, text=True, timeout=30)
            if result.returncode:
                raise RuntimeError('Synthetic management SQL failed')
            return result.stdout.strip()
        def literal(value):
            return 'NULL' if value is None else "CONVERT(0x" + str(value).encode().hex() + " USING utf8mb4)" if str(value) else "''"
        def insert(table, **values):
            sql('INSERT INTO ' + table + ' (' + ','.join(values) + ') VALUES (' + ','.join(literal(v) for v in values.values()) + ')')
        columns = {table: [row.split('\t')[0] for row in sql('SHOW COLUMNS FROM '+table).splitlines()] for table in TABLES}
        def rows(table):
            return sql('SELECT ' + ','.join("IFNULL(CONCAT('H',HEX(CAST(`"+column+"` AS BINARY))),'NULL')" for column in columns[table])
                       + ' FROM ' + table + ' ORDER BY id')
        def snapshot():
            return {table: hashlib.sha256(rows(table).encode()).hexdigest() for table in TABLES}
        def restore_audit(saved):
            statements = ['DELETE FROM sys_log']
            for row in saved.splitlines():
                values = ['NULL' if cell == 'NULL' else "''" if cell == 'H' else 'CONVERT(0x'+cell[1:]+' USING utf8mb4)' for cell in row.split('\t')]
                statements.append('INSERT INTO sys_log (`'+'`,`'.join(columns['sys_log'])+'`) VALUES ('+','.join(values)+')')
            sql(';\n'.join(statements)+';')
        def raw(method, route, actor, data=None, content_type='application/json'):
            headers = {'Content-Type': content_type, 'User-Agent': 'SyntheticManagementProbe'}
            if actor:
                headers['X-Access-Token'] = api.tokens[actor]
            request = Request('http://127.0.0.1:'+str(api.ports['backend'])+'/api'+route,
                              data=data, method=method, headers=headers)
            try:
                response = urlopen(request, timeout=15)
            except HTTPError as failure:
                response = failure
            with response:
                body = response.read()
                try:
                    payload = json.loads(body)
                except ValueError:
                    payload = None
                return response.status, payload, body, response.headers.get('Content-Type','')
        def request(method, route, actor, body=None):
            if body in ('empty_multipart', 'agent_workbook', 'position_workbook'):
                boundary = 'FixtureGlobalManagementBoundary'
                data = ('--'+boundary+'--\r\n').encode()
                if body != 'empty_multipart':
                    kind = 'position' if body == 'position_workbook' else 'agent'
                    data = ('--'+boundary+'\r\nContent-Disposition: form-data; name="file"; filename="fixture.xlsx"\r\nContent-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet\r\n\r\n').encode()+workbook(kind)+('\r\n--'+boundary+'--\r\n').encode()
                return raw(method,route,actor,data,'multipart/form-data; boundary='+boundary)
            return raw(method,route,actor,None if body is None else json.dumps(body).encode())
        def allowed(name, method, route, actor='admin', body=None):
            status, payload, _, _ = request(method,route,actor,body)
            check(name, status == 200 and payload and payload.get('success') is True)
            return payload
        def denied(name, method, route, actor, body=None, alias=False):
            before = snapshot()
            status, payload, raw_body, _ = request(method,route,actor,body)
            if alias and status == 404:
                check(name+' is an unmapped alias (not an authorization result)', True)
            else:
                expected = (401,403) if actor is None else (403,)
                check(name+' is an authorization refusal', status in expected and payload
                      and payload.get('success') is False and payload.get('code') == status)
            check(name+' returns no private metadata', MARKER.encode() not in raw_body)
            check(name+' leaves management, role, and audit rows unchanged', snapshot() == before)
        def routes():
            result = []
            for base, ident, body, workbook_name in (
                    ('/sys/sysUserAgent', PREFIX+'agent', {'id':PREFIX+'new_agent','userName':PREFIX+'new_agent','agentUserName':MARKER},'agent_workbook'),
                    ('/sys/position', PREFIX+'position', {'id':PREFIX+'new_position','code':PREFIX+'new_position','name':MARKER},'position_workbook')):
                result.extend([('GET',base+'/queryById?id='+ident,None),('GET',base+'/exportXls',None),
                               ('POST',base+'/add',body),('PUT',base+'/edit',dict(body,id=ident)),
                               ('DELETE',base+'/delete?id='+ident,None),('DELETE',base+'/deleteBatch?ids='+ident,None),
                               ('POST',base+'/importExcel',workbook_name)])
            result.extend([('GET','/sys/sysUserAgent/list',None),('GET','/sys/sysUserAgent/queryByUserName?userName='+PREFIX+'owner',None),
                           ('GET','/oss/file/list',None),('GET','/oss/file/queryById?id='+PREFIX+'file',None),
                           ('DELETE','/oss/file/delete?id='+PREFIX+'missing_file',None),
                           ('POST','/oss/file/upload','empty_multipart'),('POST','/sys/upload/uploadMinio','empty_multipart')])
            return result
        def monitor():
            return ['/actuator/redis/'+suffix for suffix in ('info','keysSize','memoryInfo','queryDiskInfo')]

        for table in TABLES:
            if sql("SELECT COUNT(*) FROM "+table+" WHERE id LIKE '"+PREFIX+"%'") != '0':
                raise RuntimeError('Existing management fixtures must not be overwritten')
        for table, column in (('sys_user_agent','user_name'),('sys_position','code')):
            if sql('SELECT COUNT(*) FROM '+table+' WHERE '+column+" LIKE '"+PREFIX+"%'") != '0':
                raise RuntimeError('Existing imported management fixture')
        original, audit = snapshot(), rows('sys_log')
        try:
            for actor in ('admin','student_a','student_b','teacher_a'):
                api.login(actor)
            insert('sys_user_agent',id=PREFIX+'agent',user_name=PREFIX+'owner',agent_user_name=MARKER,status='1')
            insert('sys_position',id=PREFIX+'position',code=PREFIX+'position',name=MARKER)
            insert('oss_file',id=PREFIX+'file',file_name=MARKER,url='http://127.0.0.1:1/synthetic-unused')
            if args.expect_legacy:
                for actor in ('student_a','teacher_a'):
                    for route in ('/sys/sysUserAgent/list','/sys/sysUserAgent/queryById?id='+PREFIX+'agent','/oss/file/list','/oss/file/queryById?id='+PREFIX+'file'):
                        result = allowed(actor+' baseline unrestricted metadata '+route,'GET',route,actor)
                        check(actor+' receives other-user fixture metadata',MARKER in json.dumps(result))
                for base, kind, data in (('/sys/sysUserAgent','agent',{'userName':PREFIX+'legacy_agent','agentUserName':MARKER}),('/sys/position','position',{'code':PREFIX+'legacy_position','name':MARKER})):
                    ident = PREFIX+'legacy_'+kind
                    allowed('baseline student creates global '+kind,'POST',base+'/add','student_a',dict(data,id=ident))
                    check('baseline '+kind+' unauthorized creation persisted',sql('SELECT COUNT(*) FROM '+('sys_user_agent' if kind=='agent' else 'sys_position')+' WHERE id='+literal(ident))=='1')
                    allowed('baseline teacher deletes global '+kind,'DELETE',base+'/delete?id='+ident,'teacher_a')
                status, payload, _, _ = request('GET','/actuator/redis/info','student_a')
                check('baseline ordinary user reads Redis INFO metadata',status==200 and payload and payload.get('success') is True)
            else:
                for actor in (None,'student_a','teacher_a'):
                    for method,route,body in routes():
                        denied(str(actor)+' '+method+' '+route.split('?')[0],method,route,actor,body)
                for actor in (None,'student_a','teacher_a','admin'):
                    for route in monitor():
                        denied(str(actor)+' operational metadata '+route,'GET',route,actor)
                for suffix in ('.js','.json','/',';fixture=1'):
                    for route in ('/sys/sysUserAgent/list','/oss/file/list','/actuator/redis/info'):
                        denied('anonymous alias '+route+suffix,'GET',route+suffix,None,alias=True)
                for actor in ('student_a','teacher_a','admin'):
                    result = allowed(actor+' keeps address-book position list','GET','/sys/position/list?code='+PREFIX+'position',actor)
                    check(actor+' receives the required position option',MARKER in json.dumps(result))
                for route in ('/sys/sysUserAgent/list','/sys/sysUserAgent/queryByUserName?userName='+PREFIX+'owner','/sys/position/queryById?id='+PREFIX+'position','/oss/file/list','/oss/file/queryById?id='+PREFIX+'file'):
                    allowed('administrator management read '+route,'GET',route)
                for base, kind, data in (('/sys/sysUserAgent','agent',{'userName':PREFIX+'new_agent','agentUserName':MARKER}),('/sys/position','position',{'code':PREFIX+'new_position','name':MARKER})):
                    table = 'sys_user_agent' if kind=='agent' else 'sys_position'
                    ident = PREFIX+'new_'+kind
                    allowed('administrator creates '+kind,'POST',base+'/add',body=dict(data,id=ident))
                    check('authorized '+kind+' creation persisted',sql('SELECT COUNT(*) FROM '+table+' WHERE id='+literal(ident))=='1')
                    allowed('administrator edits '+kind,'PUT',base+'/edit',body=dict(data,id=ident))
                    allowed('administrator imports actual XLSX '+kind,'POST',base+'/importExcel',body=kind+'_workbook')
                    column = 'user_name' if kind=='agent' else 'code'
                    check('authorized '+kind+' XLSX insertion persisted',sql('SELECT COUNT(*) FROM '+table+' WHERE '+column+'='+literal(PREFIX+'import_'+kind))=='1')
                    status, _, raw_body, content_type = request('GET',base+'/exportXls','admin')
                    cells = read_spreadsheet(raw_body)
                    title = '用户代理人设置列表数据' if kind == 'agent' else '职务表列表数据'
                    headers = ('用户名','代理人用户名') if kind == 'agent' else ('职务编码','职务名称')
                    exports.append({'kind':kind,'status':status,'content_type':content_type,'bytes':len(raw_body),
                                    'sha256':hashlib.sha256(raw_body).hexdigest(),'parsed_cells':len(cells) if cells is not None else None})
                    check('administrator exports '+kind,status==200 and cells is not None and title in cells
                          and all(header in cells for header in headers) and MARKER in cells)
                    args.output.parent.mkdir(parents=True,exist_ok=True)
                    artifact = args.output.with_name(args.output.stem+'-'+kind+'.xls')
                    if artifact.exists():
                        raise RuntimeError('Preserve existing exported fixture evidence')
                    artifact.write_bytes(raw_body)
                    exports[-1]['artifact'] = artifact.name
                    for invalid_name, invalid in (('JSON error',json.dumps({'success':False,'message':MARKER}).encode()),
                                                  ('HTML error',('<html>'+MARKER+'</html>').encode()),
                                                  ('truncated workbook',raw_body[:512])):
                        check('candidate POI rejects '+kind+' '+invalid_name,read_spreadsheet(invalid) is None)
                    allowed('administrator deletes '+kind,'DELETE',base+'/delete?id='+ident)
                    allowed('administrator batch deletes fixture '+kind,'DELETE',base+'/deleteBatch?ids='+PREFIX+kind)
                dev = sql("SELECT id FROM sys_role WHERE role_code='dev' LIMIT 1")
                if not dev:
                    dev=PREFIX+'dev'; insert('sys_role',id=dev,role_code='dev',role_name='Synthetic management developer',role_level=0)
                insert('sys_user_role',id=PREFIX+'grant',user_id='fixture_student_b',role_id=dev)
                for route in ('/sys/sysUserAgent/list','/sys/position/queryById?id='+PREFIX+'missing','/oss/file/list'):
                    status,payload,_,_=request('GET',route,'student_b')
                    check('same token live developer enters management '+route,status==200 and payload and payload.get('code')!=403)
                for route in monitor():
                    status,payload,_,_=request('GET',route,'student_b')
                    check('same token live developer monitoring '+route,status==200 and payload and payload.get('success',True) is True)
                sql('DELETE FROM sys_user_role WHERE id='+literal(PREFIX+'grant'))
                for method,route,body in routes():
                    denied('same token after developer revocation '+method+' '+route.split('?')[0],method,route,'student_b',body)
                for route in monitor():
                    denied('same token revoked operational metadata '+route,'GET',route,'student_b')
        except Exception as failure:
            error = type(failure).__name__+': '+str(failure)
            cases.append({'case':'probe completed without a runtime or assertion failure','passed':False})
        finally:
            api.close()
            sql('DELETE FROM sys_user_role WHERE id='+literal(PREFIX+'grant'))
            sql('DELETE FROM sys_role WHERE id='+literal(PREFIX+'dev'))
            sql("DELETE FROM sys_user_agent WHERE id LIKE '"+PREFIX+"%' OR user_name LIKE '"+PREFIX+"%'")
            sql("DELETE FROM sys_position WHERE id LIKE '"+PREFIX+"%' OR code LIKE '"+PREFIX+"%'")
            sql("DELETE FROM oss_file WHERE id LIKE '"+PREFIX+"%'")
            restore_audit(audit)
            check('all original management roles and audit records restored',snapshot()==original)
        report={'status':'passed' if error is None and all(c['passed'] for c in cases) else 'failed',
                'cases':cases,'passed':sum(c['passed'] for c in cases),'failed':sum(not c['passed'] for c in cases),'total':len(cases),
                'expected_legacy':bool(args.expect_legacy),'exception':error,'jar_sha256':api.jar_sha256,
                'exports':exports,
                'scope':'Synthetic localhost HTTP/MySQL only; no cloud requests. Real cloud upload/delete success covered only by mocked Java clients.'}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    return report['status']=='passed'


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('runtime','jar','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--expect-legacy',action='store_true')
    raise SystemExit(0 if verify(parser.parse_args()) else 1)
