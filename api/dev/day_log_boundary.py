"""Day-statistic manual-write regression, used by the account HTTP acceptance."""
import hashlib
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4
from zipfile import ZipFile
import json


BASE = '/teaching/teachingDepartDayLog'
REFUSAL = '班级每日教学记录由教学事件自动生成，不支持人工修改'


def excel_payload(runtime, jar, department, name):
    """Build and reopen a real XLS with the verified candidate's POI library."""
    with TemporaryDirectory(prefix='teaching-day-log-xls-') as temporary:
        directory = Path(temporary)
        libraries = []
        with ZipFile(jar) as archive:
            for entry in archive.namelist():
                if entry.startswith('BOOT-INF/lib/') and entry.endswith('.jar') and entry.count('/') == 2:
                    target = directory / Path(entry).name
                    target.write_bytes(archive.read(entry))
                    libraries.append(str(target))
        javac_candidates = sorted((runtime / 'tools').glob('*jdk*/Contents/Home/bin/javac'))
        javac = str(javac_candidates[0]) if javac_candidates else shutil.which('javac')
        if not libraries or not javac:
            raise RuntimeError('Candidate runtime libraries and a Java compiler are required for real XLS acceptance')
        source = directory / 'DayLogExcel.java'
        source.write_text('''import java.io.*;
import org.apache.poi.hssf.usermodel.HSSFWorkbook;
import org.apache.poi.ss.usermodel.*;
public class DayLogExcel {
    public static void main(String[] args) throws Exception {
        byte[] payload;
        {
            HSSFWorkbook workbook = new HSSFWorkbook();
            ByteArrayOutputStream out = new ByteArrayOutputStream();
            Sheet sheet = workbook.createSheet("日统计");
            sheet.createRow(0).createCell(0).setCellValue("班级每日教学记录");
            sheet.createRow(1).createCell(0).setCellValue("合成人工导入验收");
            String[] headers = {"班级ID", "班级名", "开课次数", "课程作业布置次数", "附加作业布置次数",
                                "课程作业批改次数", "附加作业批改次数", "课程作业提交次数", "附加作业提交次数"};
            Row header = sheet.createRow(2), row = sheet.createRow(3);
            for (int i = 0; i < headers.length; i++) header.createCell(i).setCellValue(headers[i]);
            row.createCell(0).setCellValue(args[1]); row.createCell(1).setCellValue(args[2]);
            for (int i = 2; i < headers.length; i++) row.createCell(i).setCellValue(999);
            workbook.write(out); payload = out.toByteArray();
        }
        {
            HSSFWorkbook reopened = new HSSFWorkbook(new ByteArrayInputStream(payload));
            if (reopened.getSheetAt(0).getLastRowNum() != 3 ||
                    !args[1].equals(reopened.getSheetAt(0).getRow(3).getCell(0).getStringCellValue()))
                throw new IllegalStateException("Synthetic XLS round trip failed");
        }
        try (FileOutputStream out = new FileOutputStream(args[0])) { out.write(payload); }
    }
}
''')
        classpath = ':'.join(libraries)
        compiled = subprocess.run([javac, '-proc:none', '-encoding', 'UTF-8', '-cp', classpath, str(source)],
                                  capture_output=True, timeout=30)
        if compiled.returncode:
            raise RuntimeError('Synthetic day-log XLS compilation failed: ' + compiled.stderr.decode(errors='replace'))
        output = directory / 'manual-day.xls'
        generated = subprocess.run([str(Path(javac).parent / 'java'), '-cp', str(directory) + ':' + classpath,
                                    'DayLogExcel', str(output), department, name], capture_output=True, timeout=20)
        if generated.returncode:
            raise RuntimeError('Synthetic day-log XLS generation or round trip failed')
        return output.read_bytes()


def verify_manual_writes(api, jar, sql, check, account_snapshot):
    """Assert explicit refusals and unchanged real tables for all five actors."""
    def literal(value):
        return 'CONVERT(0x' + str(value).encode().hex() + ' USING utf8mb4)'

    def state():
        snapshot = account_snapshot()
        for table in ('teaching_depart_day_log', 'teaching_additional_work'):
            snapshot[table] = hashlib.sha256(sql('SELECT * FROM ' + table + ' ORDER BY id').encode()).hexdigest()
        for event in ('unitView', 'addiWorkAssign'):
            for suffix in ('a', 'b'):
                key = 'departLog:' + event + ':fixture_class_' + suffix
                snapshot[key] = hashlib.sha256('\n'.join(sorted(api.cache('SMEMBERS', key).splitlines())).encode()).hexdigest()
        return snapshot

    def import_request(actor, payload):
        boundary = 'day-log-' + uuid4().hex
        body = ('--' + boundary + '\r\nContent-Disposition: form-data; name="file"; filename="manual-day.xls"\r\n'
                'Content-Type: application/vnd.ms-excel\r\n\r\n').encode() + payload + ('\r\n--' + boundary + '--\r\n').encode()
        request = Request('http://127.0.0.1:' + str(api.ports['backend']) + '/api' + BASE + '/importExcel', body,
                          {'Content-Type': 'multipart/form-data; boundary=' + boundary,
                           'X-Access-Token': api.tokens[actor]}, method='POST')
        try:
            response = urlopen(request, timeout=20)
        except HTTPError as error:
            response = error
        with response:
            return response.status, json.loads(response.read()), response.headers.get('Content-Type', '')

    prefix = 'day_manual_' + uuid4().hex[:12]
    today = sql('SELECT CURRENT_DATE')
    department = 'fixture_class_a'
    original = state()
    predicate = 'depart_id=' + literal(department) + ' AND create_time=' + literal(today)
    ids = sql('SELECT id FROM teaching_depart_day_log WHERE ' + predicate + ' ORDER BY id').splitlines()
    if len(ids) > 1:
        raise RuntimeError('Owned class already has duplicate current-day statistics; refusing to alter them')
    columns = [line.split('\t')[0] for line in sql('SHOW COLUMNS FROM teaching_depart_day_log').splitlines()]
    if any(not column.replace('_', '').isalnum() for column in columns):
        raise RuntimeError('Unexpected day-log column name')
    saved_query = 'SELECT ' + ','.join("IFNULL(HEX(CAST(`" + column + "` AS BINARY)),'NULL')" for column in columns)
    saved = sql(saved_query + ' FROM teaching_depart_day_log WHERE ' + predicate + ' ORDER BY id').splitlines()
    target = ids[0] if ids else prefix + '_existing'
    manual = prefix + '_forged'
    payload = excel_payload(api.runtime, jar, department, prefix)
    check('manual day-log import fixture is a real round-tripped XLS', payload.startswith(b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'))
    try:
        if not ids:
            sql('INSERT INTO teaching_depart_day_log (id,depart_id,depart_name,create_time,unit_open_count,'
                'course_work_assign_count,additional_work_assign_count,course_work_correct_count,'
                'additional_work_correct_count,course_work_submit_count,additional_work_submit_count) VALUES ('
                + literal(target) + ',' + literal(department) + ',' + literal(prefix) + ',' + literal(today) + ',1,2,3,4,5,6,7)')
        for actor in ('student_a', 'student_b', 'teacher_a', 'teacher_b', 'admin'):
            for method, route, body in (
                ('POST', '/add', {'id': manual, 'departId': department, 'departName': prefix, 'createTime': today,
                                  'unitOpenCount': 999, 'additionalWorkAssignCount': 999}),
                ('PUT', '/edit', {'id': target, 'departId': 'fixture_class_b', 'unitOpenCount': 999,
                                  'additionalWorkAssignCount': 999}),
                ('DELETE', '/delete?id=' + target, None),
                ('DELETE', '/deleteBatch?ids=' + target + ',' + manual, None),
                ('POST', '/importExcel', None)):
                before = state()
                status, result, _ = (import_request(actor, payload) if route == '/importExcel'
                                     else api.request(method, BASE + route, actor, body))
                name = actor + ' manual day-log ' + route.split('?')[0] + ' is closed'
                check(name, status == 403 and result is not None and result.get('success') is False
                      and result.get('code') == 403 and result.get('message') == REFUSAL)
                check(name + ' preserves accounts tasks counters and Redis', state() == before)
                check(name + ' preserves one class/day row', sql('SELECT COUNT(*) FROM teaching_depart_day_log WHERE ' + predicate) == '1')
    finally:
        # Restore only the owned probe and its exact pre-existing target if a
        # candidate regression allowed a destructive request before failing.
        sql('DELETE FROM teaching_depart_day_log WHERE id IN (' + literal(manual) + ',' + literal(prefix + '_existing')
            + ') OR depart_name=' + literal(prefix))
        if saved and sql(saved_query + ' FROM teaching_depart_day_log WHERE id=' + literal(target)).splitlines() != saved:
            for row in saved:
                values = ['NULL' if value == 'NULL' else "CONVERT(X'" + value + "' USING utf8mb4)" for value in row.split('\t')]
                sql('REPLACE INTO teaching_depart_day_log (' + ','.join('`' + column + '`' for column in columns)
                    + ') VALUES (' + ','.join(values) + ')')
    check('manual day-log acceptance restores its original table state', state() == original)
