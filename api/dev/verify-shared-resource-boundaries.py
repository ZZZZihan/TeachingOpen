#!/usr/bin/env python3
"""Normal allow/deny regressions for shared resources on an owned synthetic candidate."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import uuid4
from zipfile import ZipFile
from local_http import FixtureApi
from local_runtime import mysql_command


def workbook_writer(jar, directory, runtime):
    libraries = directory / 'lib'
    libraries.mkdir()
    with ZipFile(jar) as archive:
        for name in archive.namelist():
            if name.startswith('BOOT-INF/lib/') and name.endswith('.jar'):
                (libraries / Path(name).name).write_bytes(archive.read(name))
    candidates = sorted((runtime / 'tools').glob('*jdk*/Contents/Home/bin/javac'))
    javac = (str(Path(os.environ['JAVA_HOME']) / 'bin/javac') if os.environ.get('JAVA_HOME')
             else str(candidates[0]) if candidates else shutil.which('javac'))
    if not javac:
        raise RuntimeError('Java compiler required for real Excel import fixture')
    source = directory / 'WriteSharedResourceWorkbook.java'
    source.write_text('''import java.io.*; import java.nio.file.*; import java.util.*;
import org.apache.poi.hssf.usermodel.HSSFWorkbook; import org.apache.poi.ss.usermodel.*;
public class WriteSharedResourceWorkbook {
 public static void main(String[] args) throws Exception {
  Workbook book=new HSSFWorkbook(); Sheet sheet=book.createSheet("fixture");
  sheet.createRow(0).createCell(0).setCellValue("Synthetic resource fixture");
  sheet.createRow(1).createCell(0).setCellValue("Isolated authorization regression");
  int index=2;
  for(String line:Files.readAllLines(Paths.get(args[0]), java.nio.charset.StandardCharsets.UTF_8)) {
   Row row=sheet.createRow(index++); int col=0;
   for(String cell:line.split("\\t",-1)) row.createCell(col++).setCellValue(new String(Base64.getDecoder().decode(cell),"UTF-8"));
  }
  try(OutputStream output=new FileOutputStream(args[1])) { book.write(output); }
 }
}''')
    result = subprocess.run([javac, '-encoding', 'UTF-8', '-cp', str(libraries / '*'), str(source)],
                            capture_output=True, text=True, timeout=60)
    if result.returncode:
        raise RuntimeError('Excel fixture compiler failed: ' + result.stderr[:1500])
    command = [str(Path(javac).parent / 'java'), '-cp', str(directory) + os.pathsep + str(libraries / '*'),
               'WriteSharedResourceWorkbook']

    def write(headers, rows):
        source_rows = directory / 'rows.txt'
        target = directory / 'rows.xls'
        source_rows.write_text('\n'.join('\t'.join(base64.b64encode(str(cell).encode()).decode() for cell in row)
                                         for row in [headers] + rows) + '\n')
        subprocess.run(command + [str(source_rows), str(target)], check=True, capture_output=True, timeout=20)
        return target.read_bytes()
    return write


def multipart(api, path, actor, content):
    boundary = 'resource-' + uuid4().hex
    body = ('--' + boundary + '\r\nContent-Disposition: form-data; name="file"; filename="resources.xls"\r\n'
            'Content-Type: application/vnd.ms-excel\r\n\r\n').encode() + content + ('\r\n--' + boundary + '--\r\n').encode()
    request = Request('http://127.0.0.1:' + str(api.ports['backend']) + '/api' + path, body,
                      {'Content-Type': 'multipart/form-data; boundary=' + boundary,
                       'X-Access-Token': api.tokens[actor]}, method='POST')
    try:
        response = urlopen(request, timeout=20)
    except HTTPError as error:
        response = error
    with response:
        return response.status, json.loads(response.read()), response.headers.get('Content-Type', '')


def verify(args):
    if args.expect_legacy:
        raise RuntimeError('This verifier supports fixed candidate allow/deny regressions only; no legacy requests are run')
    checks = []
    with FixtureApi(args.runtime.resolve(), args.jar) as api, TemporaryDirectory(prefix='shared-resources-') as temporary:
        directory = Path(temporary)
        writer = workbook_writer(args.jar, directory, api.runtime)
        prefix = 'assetprobe_' + uuid4().hex[:12]
        file = api.runtime / 'uploads' / (prefix + '.svg')
        base = '/teaching/teachingScratchAssets'
        tables = ('teaching_scratch_assets', 'sys_file', 'sys_role', 'sys_user_role')

        def sql(statement):
            result = subprocess.run(mysql_command(api.runtime) + ['teachingopen_dev', '-e', statement],
                                    capture_output=True, text=True, timeout=20)
            if result.returncode:
                raise RuntimeError('Shared-resource synthetic SQL failed')
            return result.stdout.strip()

        def quote(value):
            return "CONVERT(X'" + str(value).encode().hex() + "' USING utf8mb4)"

        def check(name, passed):
            checks.append({'case': name, 'passed': bool(passed)})
            print(('PASS ' if passed else 'FAIL ') + name, flush=True)
            if not passed:
                raise AssertionError(name)

        def snapshot():
            return {table: hashlib.sha256(sql('SELECT * FROM ' + table + ' ORDER BY id').encode()).hexdigest() for table in tables}

        def files():
            return {str(path.relative_to(api.runtime / 'uploads')): hashlib.sha256(path.read_bytes()).hexdigest()
                    for path in (api.runtime / 'uploads').rglob('*') if path.is_file()}

        def ok(response):
            return response[0] == 200 and response[1] is not None and response[1].get('success') is True

        def denied(name, call):
            before, before_files = snapshot(), files()
            response = call()
            check(name, response[0] in (200, 403) and response[1] is not None
                  and response[1].get('success') is False and response[1].get('code') in (403, 510))
            check(name + ' preserves database and bytes', snapshot() == before and files() == before_files)

        def value(name=None):
            name = name or prefix
            data = {'name': name, 'tags': [], 'assetId': prefix, 'md5ext': file.name, 'dataFormat': 'svg',
                    'bitmapResolution': 1, 'rotationCenterX': 1, 'rotationCenterY': 1}
            return {'assetType': 1, 'assetName': name, 'assetData': json.dumps(data), 'md5Ext': file.name}

        headers = ['素材类型 1背景 2声音 3造型 4角色', '冗余 素材名', '素材json数据', '冗余 素材md5']
        normal = value()
        excel = writer(headers, [[1, normal['assetName'], normal['assetData'], normal['md5Ext']]])
        original, original_files = snapshot(), files()
        try:
            for actor in ('admin', 'teacher_a', 'student_a'):
                api.login(actor)
            file.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="2" height="2"/>')
            sql("INSERT INTO sys_file(id,file_path,file_name,file_location,create_by,del_flag) VALUES (" + quote(prefix)
                + ',' + quote(file.name) + ',' + quote(file.name) + ",1,'fixture_admin',0)")
            sql('INSERT INTO teaching_scratch_assets(id,asset_type,asset_name,asset_data,md5_ext,del_flag) VALUES ('
                + quote(prefix) + ',1,' + quote(prefix) + ',' + quote(normal['assetData']) + ',' + quote(file.name) + ',0)')
            for actor in ('student_a', 'teacher_a'):
                for method, path, data in [('GET', '/list', None), ('GET', '/queryById?id=' + prefix, None),
                                           ('GET', '/exportXls', None), ('POST', '/add', normal),
                                           ('PUT', '/edit', dict(normal, id=prefix)),
                                           ('DELETE', '/delete?id=' + prefix, None),
                                           ('DELETE', '/deleteBatch?ids=' + prefix, None)]:
                    denied(actor + ' ' + path.split('?')[0], lambda m=method, p=path, d=data, a=actor: api.request(m, base + p, a, d))
                denied(actor + ' Excel import', lambda a=actor: multipart(api, base + '/importExcel', a, excel))
            status, library, _ = api.request('GET', base + '/getScratchAssets?assetType=1', 'student_a')
            check('student can use shared asset data', status == 200 and isinstance(library, list)
                  and any(row.get('name') == prefix for row in library))
            sql('INSERT INTO teaching_scratch_assets(id,asset_type,asset_name,asset_data,del_flag) VALUES ('
                + quote(prefix + '_bad') + ',1,' + quote(prefix + '_bad') + ",'{' ,0)")
            status, library, _ = api.request('GET', base + '/getScratchAssets?assetType=1', 'student_a')
            check('historical malformed row is isolated from valid shared assets', status == 200 and isinstance(library, list)
                  and any(row.get('name') == prefix for row in library) and all(row.get('name') != prefix + '_bad' for row in library))
            check('administrator can list and inspect', ok(api.request('GET', base + '/list', 'admin'))
                  and ok(api.request('GET', base + '/queryById?id=' + prefix, 'admin')))
            check('administrator can add', ok(api.request('POST', base + '/add', 'admin', value(prefix + '_added'))))
            added = sql('SELECT id FROM teaching_scratch_assets WHERE asset_name=' + quote(prefix + '_added'))
            check('administrator can edit', bool(added) and ok(api.request('PUT', base + '/edit', 'admin', dict(value(prefix + '_edited'), id=added))))
            check('administrator can import actual Excel', ok(multipart(api, base + '/importExcel', 'admin', excel)))
            before = snapshot()
            invalid = writer(headers, [[1, normal['assetName'], normal['assetData'], normal['md5Ext']], [1, prefix, '{', file.name]])
            response = multipart(api, base + '/importExcel', 'admin', invalid)
            check('invalid Excel batch is rejected with no partial rows', not ok(response) and snapshot() == before)
            dev = sql("SELECT id FROM sys_role WHERE role_code='dev' ORDER BY id LIMIT 1")
            if not dev:
                dev = prefix + '_dev'
                sql('INSERT INTO sys_role(id,role_code,role_name) VALUES (' + quote(dev) + ",'dev','Synthetic dev')")
            sql('INSERT INTO sys_user_role(id,user_id,role_id) VALUES (' + quote(prefix) + ",'fixture_teacher_a'," + quote(dev) + ')')
            check('new live dev grant permits add with same token', ok(api.request('POST', base + '/add', 'teacher_a', value(prefix + '_dev'))))
            check('live dev can import actual Excel', ok(multipart(api, base + '/importExcel', 'teacher_a', excel)))
            sql('DELETE FROM sys_user_role WHERE id=' + quote(prefix))
            denied('revoked dev same token cannot add', lambda: api.request('POST', base + '/add', 'teacher_a', normal))
            check('administrator can delete one', ok(api.request('DELETE', base + '/delete?id=' + added, 'admin')))
            ids = sql('SELECT id FROM teaching_scratch_assets WHERE asset_name=' + quote(prefix)).splitlines()
            check('administrator can delete batch', bool(ids) and ok(api.request('DELETE', base + '/deleteBatch?' + urlencode({'ids': ','.join(ids)}), 'admin')))
            check('removing shared-library indexes preserves referenced object bytes', file.exists()
                  and sql('SELECT COUNT(*) FROM sys_file WHERE id=' + quote(prefix)) == '1')
        finally:
            sql('DELETE FROM teaching_scratch_assets WHERE asset_name LIKE ' + quote(prefix + '%'))
            sql('DELETE FROM sys_file WHERE id=' + quote(prefix))
            sql('DELETE FROM sys_user_role WHERE id=' + quote(prefix))
            sql('DELETE FROM sys_role WHERE id=' + quote(prefix + '_dev'))
            file.unlink(missing_ok=True)
            check('fixture cleanup restores shared-resource database and upload bytes', snapshot() == original and files() == original_files)
        report = {'scope': 'owned synthetic shared Scratch management authorization and Excel validation',
                  'expected_legacy': False, 'production_connected': False, 'jar_sha256': api.jar_sha256,
                  'verifier_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  'passed': len(checks), 'failed': 0, 'checks': checks}
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--jar', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--expect-legacy', action='store_true')
    verify(parser.parse_args())
