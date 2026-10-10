#!/usr/bin/env python3
"""Actual editor-persistence/API contract on a disposable five-user local fixture.

No browser authentication or editor-engine rendering is claimed. The JS probe
uses the real persistence modules, course entry, HTTP uploads, API and MySQL.
"""
import argparse
import base64
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import zipfile
from uuid import uuid4
from local_http import FixtureApi
from local_runtime import load_ports, mysql_command
from local_recovery import database_inventory

PORTS = {'mysql': 13370, 'redis': 16443, 'backend': 18173, 'frontend': 18174}


def literal(value):
    return "''" if str(value) == '' else 'CONVERT(0x' + str(value).encode().hex() + ' USING utf8mb4)'


def files(root):
    return sorted((str(p.relative_to(root)), 'symlink' if p.is_symlink() else 'dir' if p.is_dir() else hashlib.sha256(p.read_bytes()).hexdigest()) for p in root.rglob('*'))


def verify(args):
    runtime = args.runtime.absolute()
    if runtime != runtime.resolve() or runtime.name != 'course-resume-1003' or runtime.parent.name != '.devspace' or load_ports(runtime) != PORTS:
        raise ValueError('Only the owned course-resume-1003 runtime is supported')
    if args.output.exists():
        raise ValueError('Preserve existing evidence; choose a new output')
    prefix = 'fixture_cr_' + uuid4().hex[:10]
    lock = runtime / 'course-resume-probe.lock'
    os.close(os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600))
    report, before, prior_files = {}, None, None
    upload_dir = runtime / 'uploads' / prefix
    try:
        with FixtureApi(runtime, args.jar) as client:
            def sql(statement):
                reply = subprocess.run(mysql_command(runtime) + ['--default-character-set=utf8mb4', 'teachingopen_dev', '-e', statement], capture_output=True, text=True, timeout=25)
                if reply.returncode:
                    raise RuntimeError('Owned synthetic SQL operation failed')
                return reply.stdout.rstrip('\n')

            before = database_inventory(runtime)
            prior_files = files(runtime / 'uploads')
            columns = [r.split('\t')[0] for r in sql('SHOW COLUMNS FROM sys_user').splitlines()]
            expression = ','.join("IFNULL(HEX(CAST(`" + c + "` AS BINARY)),'~')" for c in columns)
            users = [r.split('\t')[1:] for r in sql("SELECT 'ROW'," + expression + ' FROM sys_user ORDER BY id').splitlines()]
            if len(users) != 5 or sql('SELECT COUNT(*) FROM teaching_depart_day_log') != '0' or upload_dir.exists():
                raise ValueError('Expected unused synthetic daily logs, five users and fresh namespace')
            cache_key = 'departLog:courseWorkSubmit:fixture_class_a'
            old_cache = client.cache('SMEMBERS', cache_key).splitlines()
            if old_cache:
                raise ValueError('Expected unused synthetic course submission cache')
            fixtures = []
            try:
                client.login('student_a')
                upload_dir.mkdir()
                asset_root = args.assets.resolve()
                for kind, work_type, extension in [('Scratch', 2, 'sb3'), ('ScratchJr', 3, 'sjr'), ('Python', 4, 'py')]:
                    if extension == 'py':
                        template = b'print("teacher template")\n'
                        student = 'print("学生继续完成的程序 & 100%")\n'.encode()
                    else:
                        template = (asset_root / ('starter.' + extension)).read_bytes()
                        output = io.BytesIO()
                        with zipfile.ZipFile(io.BytesIO(template)) as old, zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as new:
                            for entry in old.infolist():
                                data = old.read(entry.filename)
                                if entry.filename.endswith('.json'):
                                    doc = json.loads(data)
                                    if extension == 'sb3':
                                        doc['targets'][0]['variables']['resume-marker'] = ['学生修改', 42]
                                    else:
                                        doc['name'] = '学生继续完成的 ScratchJr 作品'
                                    data = json.dumps(doc, ensure_ascii=False).encode()
                                new.writestr(entry, data)
                        student = output.getvalue()
                    name = 'template.' + extension
                    (upload_dir / name).write_bytes(template)
                    unit_id = prefix + '_' + extension
                    values = [unit_id, 'fixture_course_a', kind + ' 课程恢复测试', str(work_type), prefix + '/' + name]
                    sql('INSERT INTO teaching_course_unit (id,course_id,unit_name,course_work_type,course_work) VALUES (' + ','.join(map(literal, values)) + ')')
                    fixtures.append(dict(kind=kind, type=work_type, extension=extension, unitId=unit_id, template=base64.b64encode(template).decode(), student=base64.b64encode(student).decode()))
                config = dict(origin='http://127.0.0.1:18173', tokens=client.tokens, prefix=prefix, fixtures=fixtures,
                              cover='iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aVb8AAAAASUVORK5CYII=')
                probe = Path(__file__).resolve().parents[2] / 'web/tests/course-draft-resume-live.cjs'
                run = subprocess.run(['node', str(probe), str(args.source.resolve())], input=json.dumps(config), capture_output=True, text=True, timeout=180)
                report = json.loads(run.stdout)
                report.update(exit_code=run.returncode, jar_sha256=client.jar_sha256,
                              source_head=subprocess.check_output(['git', '-C', str(args.source), 'rev-parse', 'HEAD'], text=True).strip(),
                              scope='actual persistence modules and course URLs with real HTTP/DB; editor rendering and browser login excluded')
                for fixture in fixtures:
                    count = int(sql('SELECT COUNT(*) FROM teaching_work WHERE course_id=' + literal(fixture['unitId']) + " AND user_id='fixture_student_a'"))
                    report['cases'].append(dict(case=fixture['kind'] + ': exactly one student work row remains after reopen and save', passed=count == 1))
            finally:
                ids = sql('SELECT id FROM teaching_work WHERE course_id LIKE ' + literal(prefix + '%')).splitlines()
                for ident in ids:
                    sql('DELETE FROM sys_data_log WHERE data_id=' + literal(ident))
                    sql('DELETE FROM teaching_work WHERE id=' + literal(ident))
                sql('DELETE FROM teaching_course_unit WHERE id LIKE ' + literal(prefix + '%'))
                sql('DELETE FROM sys_file WHERE file_path LIKE ' + literal(prefix + '/%'))
                sql("DELETE FROM teaching_depart_day_log WHERE depart_id='fixture_class_a'")
                client.cache('DEL', cache_key)
                for row in users:
                    assignments = []
                    for column, value in zip(columns, row):
                        if column == 'id':
                            continue
                        expression = 'NULL' if value == '~' else "''" if value == '' else 'CONVERT(0x' + value + ' USING utf8mb4)'
                        assignments.append('`' + column + '`=' + expression)
                    sql('UPDATE sys_user SET ' + ','.join(assignments) + ' WHERE id=CONVERT(0x' + row[columns.index('id')] + ' USING utf8mb4)')
                if upload_dir.exists():
                    shutil.rmtree(upload_dir)
            after = database_inventory(runtime)
            report['restoration'] = dict(table_count=len(before), same_table_set=before.keys() == after.keys(),
                changed_schemas=[t for t in before if before[t]['schema_sha256'] != after.get(t, {}).get('schema_sha256')],
                changed_non_audit_tables=[t for t in before if t != 'sys_log' and before[t] != after.get(t)],
                all_attachment_entries_equal=prior_files == files(runtime / 'uploads'), cache_restored=client.cache('SMEMBERS', cache_key).splitlines() == old_cache)
            restored = report['restoration']
            report['cases'].append(dict(case='complete database schemas non-audit rows attachments and submission cache restored', passed=restored['same_table_set'] and not restored['changed_schemas'] and not restored['changed_non_audit_tables'] and restored['all_attachment_entries_equal'] and restored['cache_restored']))
            report['total'] = len(report['cases'])
            report['passed'] = sum(c['passed'] for c in report['cases'])
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
            print(json.dumps({k: report[k] for k in ['passed', 'total', 'exit_code', 'restoration']}))
            return 0 if report['passed'] == report['total'] and report['exit_code'] == 0 else 1
    finally:
        lock.unlink()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('runtime', 'jar', 'source', 'assets', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    raise SystemExit(verify(parser.parse_args()))
