#!/usr/bin/env python3
"""Dictionary management allow/deny checks in an owned synthetic local candidate."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4
from zipfile import ZipFile

from local_http import FixtureApi
from local_runtime import mysql_command


def workbook_with_second_item(runtime, jar, workbook, code, item_value):
    """Edit an actual exported HSSF workbook with POI from the tested candidate JAR."""
    source = r'''
import java.io.*;
import java.nio.file.*;
import org.apache.poi.hssf.usermodel.*;
public class DictionaryWorkbook {
    public static void main(String[] args) throws Exception {
        HSSFWorkbook book = new HSSFWorkbook(new ByteArrayInputStream(Files.readAllBytes(Paths.get(args[0]))));
        HSSFSheet sheet = book.getSheetAt(0);
        int code = -1, name = -1, text = -1, value = -1;
        for (int r = 0; r < 4; r++) {
            HSSFRow row = sheet.getRow(r);
            if (row == null) continue;
            for (int c = 0; c < row.getLastCellNum(); c++) {
                HSSFCell cell = row.getCell(c);
                if (cell == null || cell.getCellType() != HSSFCell.CELL_TYPE_STRING) continue;
                String title = cell.getStringCellValue();
                if ("字典编码".equals(title)) code = c;
                if ("字典名称".equals(title)) name = c;
                if ("字典项文本".equals(title)) text = c;
                if ("字典项值".equals(title)) value = c;
            }
        }
        if (code < 0 || name < 0 || text < 0 || value < 0 || sheet.getRow(4) == null)
            throw new IllegalStateException("Actual dictionary workbook headers or first data row missing");
        HSSFRow first = sheet.getRow(4);
        first.getCell(code).setCellValue(args[2]);
        first.getCell(name).setCellValue("合成事务回滚字典");
        HSSFRow second = sheet.createRow(5);
        second.createCell(text).setCellValue("合成第二子项");
        second.createCell(value).setCellValue(args[3]);
        try (OutputStream output = Files.newOutputStream(Paths.get(args[1]))) { book.write(output); }
    }
}
'''
    with TemporaryDirectory(prefix='dictionary-workbook-') as scratch:
        directory = Path(scratch)
        with ZipFile(jar) as candidate:
            poi_names = [name for name in candidate.namelist()
                         if name.startswith('BOOT-INF/lib/poi-') and name.endswith('.jar')
                         and 'ooxml' not in name and 'scratchpad' not in name]
            if len(poi_names) != 1:
                raise RuntimeError('Candidate must supply exactly one core POI library')
            poi = directory / 'candidate-poi.jar'
            poi.write_bytes(candidate.read(poi_names[0]))
        (directory / 'DictionaryWorkbook.java').write_text(source)
        original, edited = directory / 'exported.xls', directory / 'edited.xls'
        original.write_bytes(workbook)
        java_home = (Path(os.environ['JAVA_HOME']) if os.environ.get('JAVA_HOME') else
                     runtime / 'tools/zulu8.96.0.205-ca-jdk8.0.504-macosx_aarch64/Contents/Home')
        subprocess.run([str(java_home / 'bin/javac'), '-encoding', 'UTF-8', '-cp', str(poi),
                        str(directory / 'DictionaryWorkbook.java')], check=True, capture_output=True, timeout=30)
        subprocess.run([str(java_home / 'bin/java'), '-cp', str(directory) + ':' + str(poi),
                        'DictionaryWorkbook', str(original), str(edited), code, item_value],
                       check=True, capture_output=True, timeout=30)
        return edited.read_bytes()


def verify(args):
    output = args.output.resolve()
    if output.exists():
        raise RuntimeError('Preserve existing dictionary management evidence')
    checks = []
    report = {'scope': 'owned synthetic Spring/Shiro HTTP, MySQL and Redis',
              'production_connected': False, 'checks': checks,
              'verifier_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    try:
        with FixtureApi(args.runtime.resolve(), args.jar) as api:
            report['jar_sha256'] = api.jar_sha256

            def sql(statement):
                result = subprocess.run(mysql_command(api.runtime) + ['teachingopen_dev'],
                                        input=statement, capture_output=True, text=True, timeout=20)
                if result.returncode:
                    raise RuntimeError('Synthetic dictionary SQL failed')
                return result.stdout.strip()

            def literal(value):
                return 'CONVERT(0x' + str(value).encode().hex() + ' USING utf8mb4)'

            def check(name, passed):
                checks.append({'case': name, 'passed': bool(passed)})
                print(('PASS ' if passed else 'FAIL ') + name, flush=True)
                if not passed:
                    raise AssertionError(name)

            def snapshot():
                return hashlib.sha256(sql('SELECT * FROM sys_dict ORDER BY id;'
                                          'SELECT * FROM sys_dict_item ORDER BY id;').encode()).hexdigest()

            prefix = 'dm_' + uuid4().hex[:8]
            tables = ('sys_user', 'sys_role', 'sys_user_role', 'sys_dict', 'sys_dict_item')
            saved = {}
            for table in tables:
                columns = [row.split('\t')[0] for row in sql('SHOW COLUMNS FROM ' + table).splitlines()]
                rows = sql('SELECT ' + ','.join("IFNULL(HEX(CAST(`" + column + "` AS BINARY)),'NULL')"
                                              for column in columns) + ' FROM ' + table + ' ORDER BY id').splitlines()
                saved[table] = columns, rows

            def fixture_snapshot():
                return hashlib.sha256(sql(';'.join('SELECT * FROM ' + table + ' ORDER BY id' for table in tables) + ';').encode()).hexdigest()

            fixture_before = fixture_snapshot()
            report['baseline_fixture_sha256'] = fixture_before
            before = snapshot()
            report['baseline_dictionary_sha256'] = before
            upload_roots = (api.runtime / 'uploads', api.runtime / 'webapp/upload')
            existing_uploads = {path.resolve(): hashlib.sha256(path.read_bytes()).hexdigest()
                                for root in upload_roots for path in root.rglob('*') if path.is_file()}
            owned_error_files = set()
            sentinels = [name + '::' + prefix for name in
                         ('sys:cache:dict', 'sys:cache:dictTable', 'sys:cache:depart:alldata', 'sys:cache:depart:allids')]

            def operations():
                return [('POST', '/sys/dict/add', {'id': prefix, 'dictCode': prefix, 'dictName': '合成字典'}),
                        ('PUT', '/sys/dict/edit', {'id': prefix, 'dictName': '合成修改'}),
                        ('DELETE', '/sys/dict/delete?id=' + prefix, None),
                        ('DELETE', '/sys/dict/deleteBatch?ids=' + prefix + ',missing', None),
                        ('POST', '/sys/dict/importExcel', None),
                        ('DELETE', '/sys/dict/deletePhysic/' + prefix, None),
                        ('PUT', '/sys/dict/back/' + prefix, None),
                        ('GET', '/sys/dict/refleshCache', None),
                        ('POST', '/sys/dictItem/add', {'id': prefix + '_item', 'dictId': prefix, 'itemValue': 'one'}),
                        ('PUT', '/sys/dictItem/edit', {'id': prefix + '_item', 'itemValue': 'changed'}),
                        ('DELETE', '/sys/dictItem/delete?id=' + prefix + '_item', None),
                        ('DELETE', '/sys/dictItem/deleteBatch?ids=' + prefix + '_item,missing', None)]

            def deny_all(actor, label, authentication_rejection=False):
                for key in sentinels:
                    api.cache('SET', key, 'retained')
                for method, path, data in operations():
                    baseline = snapshot()
                    status, body, _ = api.request(method, path, actor, data)
                    name = label + ' ' + method + ' ' + path.split('?')[0]
                    denied = (status == 401 and (not body or body.get('success') is not True)) if authentication_rejection else (status == 200 and body and body.get('success') is False and body.get('code') == 403)
                    check(name + ' rejects', denied)
                    check(name + ' leaves database unchanged', snapshot() == baseline)
                    check(name + ' preserves all four cache sentinels', all(api.cache('GET', key) == 'retained' for key in sentinels))

            def allowed(actor, method, path, data=None):
                status, body, _ = api.request(method, path, actor, data)
                check(actor + ' ' + method + ' ' + path.split('?')[0], status == 200 and body and body.get('success') is True)

            def raw(actor, method, path, data=None, content_type=None):
                headers = {'X-Access-Token': api.tokens[actor]}
                if content_type:
                    headers['Content-Type'] = content_type
                request = Request('http://127.0.0.1:' + str(api.ports['backend']) + '/api' + path,
                                  data=data, headers=headers, method=method)
                try:
                    response = urlopen(request, timeout=20)
                except HTTPError as error:
                    response = error
                with response:
                    return response.status, response.read()

            def import_workbook(actor, workbook):
                boundary = '----synthetic' + uuid4().hex
                body = ('--' + boundary + '\r\nContent-Disposition: form-data; name="file"; filename="synthetic.xls"\r\n'
                        'Content-Type: application/vnd.ms-excel\r\n\r\n').encode() + workbook + ('\r\n--' + boundary + '--\r\n').encode()
                status, payload = raw(actor, 'POST', '/sys/dict/importExcel', body, 'multipart/form-data; boundary=' + boundary)
                result = json.loads(payload)
                file_url = (result.get('result') or {}).get('fileUrl') if isinstance(result.get('result'), dict) else None
                if file_url and file_url.startswith('/sys/common/static/'):
                    relative = file_url[len('/sys/common/static/'):]
                    path = (api.runtime / 'uploads' / relative).resolve()
                    if path.is_relative_to((api.runtime / 'uploads').resolve()) and path not in existing_uploads:
                        owned_error_files.add(path)
                return status, result

            def dictionary_cache_snapshot():
                return api.cache('EVAL', "local keys={}; for _,prefix in ipairs(ARGV) do "
                                 "for _,key in ipairs(redis.call('KEYS',prefix..'*')) do table.insert(keys,key) end end; "
                                 "table.sort(keys); local values={}; for _,key in ipairs(keys) do "
                                 "table.insert(values,key..':'..redis.sha1hex(redis.call('DUMP',key))) end; "
                                 "return redis.sha1hex(table.concat(values,'|'))", '0',
                                 'sys:cache:dict', 'sys:cache:dictTable', 'sys:cache:depart:alldata', 'sys:cache:depart:allids')

            try:
                sql('INSERT INTO sys_role(id,role_code,role_name,role_level) VALUES (' + literal(prefix + '_dev') + ",'dev','合成开发者',10);"
                    + 'INSERT INTO sys_user_role(id,user_id,role_id) VALUES (' + literal(prefix + '_grant')
                    + ",'fixture_teacher_b'," + literal(prefix + '_dev') + ');')
                for actor in ('admin', 'teacher_a', 'teacher_b', 'student_a'):
                    api.login(actor)
                status, body, _ = api.request(*operations()[0][:2], data=operations()[0][2])
                check('anonymous add is rejected by authentication', status == 401 and (not body or body.get('success') is not True))
                deny_all('student_a', 'student')
                deny_all('teacher_a', 'teacher')
                for actor in ('admin', 'teacher_b'):
                    did, iid = prefix + '_' + actor, prefix + '_' + actor + '_item'
                    allowed(actor, 'POST', '/sys/dict/add', {'id': did, 'dictCode': did, 'dictName': '合成字典'})
                    check(actor + ' create persists one dictionary', sql('SELECT COUNT(*) FROM sys_dict WHERE id=' + literal(did)) == '1')
                    allowed(actor, 'PUT', '/sys/dict/edit', {'id': did, 'dictName': '合成编辑'})
                    check(actor + ' edit persists', sql('SELECT dict_name FROM sys_dict WHERE id=' + literal(did)) == '合成编辑')
                    allowed(actor, 'POST', '/sys/dictItem/add', {'id': iid, 'dictId': did, 'itemValue': 'one', 'itemText': '合成项', 'status': 1})
                    allowed(actor, 'PUT', '/sys/dictItem/edit', {'id': iid, 'itemText': '合成修改'})
                    check(actor + ' item edit persists', sql('SELECT item_text FROM sys_dict_item WHERE id=' + literal(iid)) == '合成修改')
                    status, workbook = raw(actor, 'GET', '/sys/dict/exportXls?dictCode=' + did)
                    check(actor + ' export creates an actual workbook', status == 200 and workbook[:4] in (b'\xd0\xcf\x11\xe0', b'PK\x03\x04'))
                    if actor == 'admin':
                        rollback_code = did + '_rollback'
                        candidate_jar = args.jar or Path(__file__).resolve().parents[1] / 'jeecg-boot-module-system/target/teaching-open-2.8.0.jar'
                        invalid = workbook_with_second_item(api.runtime, candidate_jar, workbook, rollback_code, 'x' * 101)
                        for key in sentinels:
                            api.cache('SET', key, 'rollback-retained')
                        row_baseline, cache_baseline = snapshot(), dictionary_cache_snapshot()
                        status, failed_import = import_workbook(actor, invalid)
                        stats = failed_import.get('result') or {}
                        check('valid Excel parent plus invalid second child reports one failed parent transaction',
                              status == 200 and failed_import.get('code') == 201 and stats.get('errorCount') == 1
                              and stats.get('successCount') == 0 and stats.get('totalCount') == 1)
                        check('failed child import rolls back the new parent and preceding valid child',
                              sql('SELECT COUNT(*) FROM sys_dict WHERE dict_code=' + literal(rollback_code)) == '0'
                              and snapshot() == row_baseline)
                        check('failed import preserves complete dictionary cache contents', dictionary_cache_snapshot() == cache_baseline)
                        check('failed import preserves all four cache sentinels',
                              all(api.cache('GET', key) == 'rollback-retained' for key in sentinels))
                        report['import_rollback'] = {'http_status': status, 'business_code': failed_import.get('code'),
                                                     'error_count': stats.get('errorCount'), 'success_count': stats.get('successCount'),
                                                     'dictionary_sha256_before': row_baseline, 'dictionary_sha256_after': snapshot(),
                                                     'cache_sha1_before': cache_baseline, 'cache_sha1_after': dictionary_cache_snapshot(),
                                                     'input': 'actual exported Excel; new valid parent, valid first child, 101-character second child'}
                        valid = workbook_with_second_item(api.runtime, candidate_jar, workbook, rollback_code, 'two')
                        status, valid_import = import_workbook(actor, valid)
                        check('same workbook with corrected second child imports successfully', status == 200 and valid_import.get('success') is True and valid_import.get('code') == 200)
                        check('corrected workbook persists exactly one parent and two children',
                              sql('SELECT COUNT(*) FROM sys_dict WHERE dict_code=' + literal(rollback_code)) == '1'
                              and sql('SELECT COUNT(*) FROM sys_dict_item WHERE dict_id IN (SELECT id FROM sys_dict WHERE dict_code=' + literal(rollback_code) + ')') == '2')
                        rollback_id = sql('SELECT id FROM sys_dict WHERE dict_code=' + literal(rollback_code))
                        allowed(actor, 'DELETE', '/sys/dict/deletePhysic/' + rollback_id)
                    allowed(actor, 'DELETE', '/sys/dict/delete?id=' + did)
                    check(actor + ' soft delete persists', sql('SELECT del_flag FROM sys_dict WHERE id=' + literal(did)) == '1')
                    allowed(actor, 'PUT', '/sys/dict/back/' + did)
                    check(actor + ' restore persists', sql('SELECT del_flag FROM sys_dict WHERE id=' + literal(did)) == '0')
                    allowed(actor, 'DELETE', '/sys/dictItem/delete?id=' + iid)
                    allowed(actor, 'POST', '/sys/dictItem/add', {'id': iid, 'dictId': did, 'itemValue': 'one', 'itemText': '合成项'})
                    allowed(actor, 'DELETE', '/sys/dictItem/deleteBatch?ids=' + iid)
                    allowed(actor, 'DELETE', '/sys/dict/deleteBatch?ids=' + did)
                    allowed(actor, 'DELETE', '/sys/dict/deletePhysic/' + did)
                    check(actor + ' permanent delete removes dictionary and children', sql('SELECT COUNT(*) FROM sys_dict WHERE id=' + literal(did)) == '0'
                          and sql('SELECT COUNT(*) FROM sys_dict_item WHERE dict_id=' + literal(did)) == '0')
                    status, imported = import_workbook(actor, workbook)
                    check(actor + ' exported workbook reimports successfully', status == 200 and imported.get('success') is True)
                    check(actor + ' import persists parent and child', sql('SELECT COUNT(*) FROM sys_dict WHERE dict_code=' + literal(did)) == '1'
                          and sql('SELECT COUNT(*) FROM sys_dict_item WHERE dict_id IN (SELECT id FROM sys_dict WHERE dict_code=' + literal(did) + ')') == '1')
                    # Legacy refresh returns success=false by default; preserve that response shape, test the actual effect.
                    for key in sentinels:
                        api.cache('SET', key, 'stale')
                    status, _, _ = api.request('GET', '/sys/dict/refleshCache', actor)
                    check(actor + ' refresh clears all four cache families', status == 200 and all(api.cache('EXISTS', key) == '0' for key in sentinels))
                # Same login token, no cache deletion at the role transition.
                sql('DELETE FROM sys_user_role WHERE id=' + literal(prefix + '_grant'))
                deny_all('teacher_b', 'revoked developer same session')
                sql("UPDATE sys_user SET status=2 WHERE id='fixture_admin'")
                deny_all('admin', 'frozen administrator same session', authentication_rejection=True)
                sql("UPDATE sys_user SET status=1,del_flag=1 WHERE id='fixture_admin'")
                deny_all('admin', 'deleted administrator same session', authentication_rejection=True)
            finally:
                for table in reversed(tables):
                    sql('DELETE FROM ' + table)
                for table, (columns, rows) in saved.items():
                    for row in rows:
                        values = ['NULL' if value == 'NULL' else ("''" if value == '' else 'CONVERT(0x' + value + ' USING utf8mb4)') for value in row.split('\t')]
                        sql('INSERT INTO ' + table + '(' + ','.join('`' + column + '`' for column in columns) + ') VALUES (' + ','.join(values) + ')')
                for key in sentinels:
                    api.cache('DEL', key)
                for actor in ('admin', 'teacher_a', 'teacher_b', 'student_a'):
                    api.cache('DEL', 'sys:cache:user::fixture_' + actor)
                    api.cache('DEL', 'shiro:cache:org.jeecg.modules.shiro.authc.ShiroRealm.authorizationCache:fixture_' + actor)
                report['restored_dictionary_sha256'] = snapshot()
                report['restored_fixture_sha256'] = fixture_snapshot()
                removed = []
                unknown = []
                for root in upload_roots:
                    for path in root.rglob('*'):
                        if not path.is_file() or path.resolve() in existing_uploads:
                            continue
                        content = path.read_bytes()
                        if path.resolve() in owned_error_files or (path.suffix.lower() in ('.xls', '.xlsx')
                                and (prefix.encode() in content or prefix.encode('utf-16le') in content)):
                            path.unlink()
                            removed.append(str(path.relative_to(api.runtime)))
                        else:
                            unknown.append(str(path.relative_to(api.runtime)))
                report['upload_cleanup'] = {'owned_files_removed': removed, 'unknown_files_preserved': unknown,
                                            'preexisting_files_verified': len(existing_uploads)}
                check('dictionary business rows restored', report['restored_dictionary_sha256'] == before)
                check('all five synthetic business tables restored', report['restored_fixture_sha256'] == fixture_before)
                check('only owned import files removed; unknown files preserved', not unknown)
                check('preexisting upload files preserved byte for byte', all(path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == digest
                                                                              for path, digest in existing_uploads.items()))
                report['fixture_restored'] = True
    finally:
        report['passed'] = sum(check['passed'] for check in checks)
        report['failed'] = sum(not check['passed'] for check in checks)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--jar', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    verify(parser.parse_args())
