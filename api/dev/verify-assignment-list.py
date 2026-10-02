#!/usr/bin/env python3
"""Verify authenticated assignment list scope and attachment URLs on local fixtures."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from local_http import FixtureApi
from local_runtime import mysql_command

PREFIX = 'fixture_aprobe_'
BASE = '/teaching/teachingWork/mineAdditionalWork'
TABLES = ('teaching_additional_work', 'teaching_work', 'teaching_work_correct', 'sys_file', 'sys_user_depart', 'sys_depart')
FAULT_TABLE = 'fixture_assignment_list_hold'


def verify(args):
    cases, observed = [], {}
    with FixtureApi(args.runtime.resolve(), args.jar) as api:
        def sql(query):
            return subprocess.check_output(mysql_command(api.runtime) + ['teachingopen_dev', '-e', query], text=True).strip()

        def check(name, result):
            cases.append({'case': name, 'passed': bool(result)})
            print(('PASS ' if result else 'FAIL ') + name, flush=True)

        def snapshot():
            return {table: hashlib.sha256(sql('SELECT * FROM ' + table + ' ORDER BY id').encode()).hexdigest() for table in TABLES}

        def file_snapshot():
            return {str(p.relative_to(api.runtime / 'uploads')): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in (api.runtime / 'uploads').rglob('*') if p.is_file()}

        def read(actor='student_a', **params):
            status, body, _ = api.request('GET', BASE + ('?' + urlencode(params) if params else ''), actor)
            check((actor or 'anonymous') + ' list ' + str(params), status == 200 and body and body.get('success') is True)
            return [r for r in ((body or {}).get('result') or []) if r['additionalWorkId'].startswith(PREFIX)]

        def ids(rows):
            return {r['additionalWorkId'][len(PREFIX):] for r in rows}

        def quoted(value):
            return 'NULL' if value is None else "'" + str(value).replace('\\', '\\\\').replace("'", "''") + "'"

        def insert(table, **values):
            sql('INSERT INTO ' + table + ' (' + ','.join(values) + ') VALUES (' + ','.join(quoted(v) for v in values.values()) + ')')

        before, before_files = snapshot(), file_snapshot()
        categories = {side: sql("SELECT org_category FROM sys_depart WHERE id='fixture_class_"+side+"'") for side in ('a','b')}
        if any(value not in ('2','3') for value in categories.values()):
            raise RuntimeError('Unexpected fixture class categories')
        if sql("SELECT COUNT(*) FROM sys_depart WHERE id IN ('fixture_class_a','fixture_class_b') AND del_flag='0'")!='2':
            raise RuntimeError('Unexpected fixture class deletion state')
        for table in TABLES:
            if sql("SELECT COUNT(*) FROM " + table + " WHERE id LIKE '" + PREFIX + "%'") != '0':
                raise RuntimeError('Existing assignment probe rows; refusing overwrite')
        if sql("SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='" + FAULT_TABLE + "'") != '0':
            raise RuntimeError('Existing assignment probe fault table')
        file_path = api.runtime / 'uploads' / 'assignment-probe # report.txt'
        if file_path.exists():
            raise RuntimeError('Existing assignment probe file')
        fault = False
        try:
            # Existing general-purpose fixture uses category 2 (department).
            # This endpoint explicitly queries category 3 (class); restore afterwards.
            sql("UPDATE sys_depart SET org_category='3' WHERE id IN ('fixture_class_a','fixture_class_b')")
            for actor in ('student_a', 'student_b', 'teacher_a', 'admin'):
                api.login(actor)
            file_path.write_bytes(b'authored assignment list attachment\n')
            insert('sys_file', id=PREFIX+'file', file_name=file_path.name, file_path=file_path.name, file_location=1, create_by='fixture_student_a')
            specs = [('pending', 'fixture_class_a', 1), ('draft', 'fixture_class_a', 1),
                     ('submitted', 'fixture_class_a', 1), ('graded', 'fixture_class_a', 1),
                     ('foreign', 'fixture_class_b', 1), ('withdrawn', 'fixture_class_a', 0),
                     ('ended', 'fixture_class_a', 2), ('substring', 'fixture_class_a_extra', 1),
                     ('shared', ' fixture_class_b , fixture_class_a ', 1), ('deleted', 'fixture_class_a', 1),
                     ('empty', '', 1), ('missingfile', 'fixture_class_a', 1)]
            for suffix, departments, state in specs:
                insert('teaching_additional_work', id=PREFIX+suffix, work_name='assignment-probe-'+suffix,
                       work_dept=departments, status=state, code_type=0, create_time='2026-10-03 00:00:00')
            for suffix, status, depart, deleted in [('draft', 0, 'fixture_class_a', 0), ('submitted', 1, 'fixture_class_a', 0),
                    ('graded', 2, 'fixture_class_a', 0), ('foreign', 0, 'fixture_class_b', 0),
                    ('withdrawn', 0, 'fixture_class_a', 0), ('ended', 0, 'fixture_class_a', 0),
                    ('shared', 1, 'fixture_class_a', 0), ('deleted', 1, 'fixture_class_a', 1),
                    ('missingfile', 1, 'fixture_class_a', 0)]:
                insert('teaching_work', id=PREFIX+'w_'+suffix, user_id='fixture_student_a', additional_id=PREFIX+suffix,
                       depart_id=depart, work_name='assignment-probe-work-'+suffix, work_type=0, work_status=status,
                       create_by='fixture_student_a', create_time='2026-10-03 00:00:00',
                       work_file=PREFIX+('missing' if suffix=='missingfile' else 'file'), work_cover=PREFIX+'file', del_flag=deleted)
            insert('teaching_work', id=PREFIX+'other', user_id='fixture_student_b', additional_id=PREFIX+'pending',
                   depart_id='fixture_class_a', work_name='other-owner', work_type=0, work_status=2, del_flag=0,
                   work_file='', create_by='fixture_student_b', create_time='2026-10-03 00:00:00')
            insert('teaching_work_correct', id=PREFIX+'feedback', work_id=PREFIX+'w_graded', score=0, comment='zero score feedback')
            rows = read(submit='false'); observed['unsubmitted_ids'] = sorted(ids(rows))
            all_rows = read(); observed['all_ids'] = sorted(ids(all_rows))
            filtered = read(departId='fixture_class_b'); observed['foreign_filter_ids'] = sorted(ids(filtered))
            print(json.dumps(observed, sort_keys=True), flush=True)
            submitted = next(r for r in all_rows if r['additionalWorkId']==PREFIX+'submitted')
            observed['local_file_response'] = {k:v for k,v in submitted.items() if k.startswith('mineWork')}
            if args.expect_legacy:
                check('legacy draft OR bypasses assignment state and class', {'foreign','withdrawn','ended'} <= ids(rows))
                check('legacy substring class leaks task', 'substring' in ids(all_rows))
                check('legacy foreign department filter ignored', bool(ids(filtered) & {'pending','draft','graded'}))
                check('legacy deleted work treated as submitted', any(r.get('mineWorkId')==PREFIX+'w_deleted' for r in all_rows))
                check('legacy local file gets cloud URL', str(submitted['mineWorkUrl']).startswith('http://127.0.0.1:9/'))
                check('legacy decorated URL double prefixes', 'http://127.0.0.1:9/' in str(submitted.get('mineWorkUrl_url')) and str(submitted.get('mineWorkUrl_url')).startswith('/api/sys/common/static/'))
            else:
                check('only visible assigned pending or draft tasks', ids(rows)=={'pending','draft','deleted'})
                check('all task list excludes foreign withdrawn ended substring empty', ids(all_rows)=={'pending','draft','submitted','graded','shared','deleted','missingfile'})
                check('foreign department filter returns empty', not filtered)
                check('owned department filter matches visible tasks', ids(read(departId='fixture_class_a'))==ids(all_rows))
                check('supplied user ID cannot select another identity', ids(read(userId='fixture_student_b'))==ids(all_rows))
                check('unknown department does not expand scope', not read(departId="fixture_class_a' OR 1=1"))
                check('submission filter includes submitted and graded', ids(read(submit='true'))=={'submitted','graded','shared','missingfile'})
                check('specific submitted status', ids(read(submit='true',status=1))=={'submitted','shared','missingfile'})
                graded = read(submit='true',status=2)
                check('zero score and private feedback retained', ids(graded)=={'graded'} and graded[0]['score']==0 and graded[0]['comment']=='zero score feedback')
                pending = next(r for r in all_rows if r['additionalWorkId']==PREFIX+'pending')
                check('other owner work and feedback not joined', pending.get('mineWorkId') is None and pending.get('comment') is None)
                deleted = next(r for r in all_rows if r['additionalWorkId']==PREFIX+'deleted')
                check('deleted submission becomes unsubmitted task without stale file', deleted.get('mineWorkId') is None and not deleted.get('mineWorkUrl'))
                check('no class membership returns empty', not read('admin'))
                check('other student sees own class task without A submission', ids(read('student_b'))=={'foreign','shared'} and all(not r.get('mineWorkId') for r in read('student_b')))
                for actor, token, expected in [(None,None,401),(None,'invalid-fixture-token',401)]:
                    status, body, _ = api.request('GET',BASE,actor,token=token)
                    check('anonymous or invalid credential rejected',status==expected and body and body.get('success') is False)
                check('list responses not cached', api.request('GET',BASE,'student_a')[0]==200 and api.last_response_headers.get('Cache-Control')=='no-store')
                url = submitted['mineWorkUrl']; check('local raw and decorated URL agree',url==submitted['mineWorkUrl_url'] and url.startswith('/api/sys/common/static/') and '%23' in url and '%20' in url)
                for actor, expected in [('student_a',200),('student_b',403)]:
                    request=Request('http://127.0.0.1:'+str(api.ports['backend'])+url,headers={'X-Access-Token':api.tokens[actor]})
                    try: response=urlopen(request,timeout=10)
                    except HTTPError as error: response=error
                    with response:
                        body=response.read(); check(actor+' returned local URL access',response.status==expected and (body==file_path.read_bytes() if expected==200 else body!=file_path.read_bytes()))
                missing=next(r for r in all_rows if r['additionalWorkId']==PREFIX+'missingfile')
                check('missing file has no fabricated download URL',not missing.get('mineWorkUrl') and not missing.get('mineWorkUrl_url'))
                # Add an authorized second class. Existing shared work retains class A.
                insert('sys_user_depart',id=PREFIX+'membership',user_id='fixture_student_a',dep_id='fixture_class_b')
                multi=read(); shared=next(r for r in multi if r['additionalWorkId']==PREFIX+'shared')
                check('existing shared task retains saved work class',shared['departId']=='fixture_class_a' and shared['mineWorkDepartId']=='fixture_class_a')
                only_b=read(departId='fixture_class_b')
                check('filter B contains only B work and eligible tasks',ids(only_b)=={'foreign'} and all(r['departId']=='fixture_class_b' for r in only_b))
                sql("DELETE FROM sys_user_depart WHERE id='"+PREFIX+"membership'")
                # Reference is synthetic, no network request is made to cloud storage.
                sql("UPDATE sys_file SET file_location=2 WHERE id='"+PREFIX+"file'")
                cloud=next(r for r in read() if r['additionalWorkId']==PREFIX+'submitted')
                check('stored location chooses cloud URL without local prefix',cloud['mineWorkUrl']==cloud['mineWorkUrl_url'] and cloud['mineWorkUrl'].startswith('http://127.0.0.1:9/'))
                sql("UPDATE sys_file SET file_location=9 WHERE id='"+PREFIX+"file'")
                unknown=next(r for r in read() if r['additionalWorkId']==PREFIX+'submitted')
                check('unknown storage has no guessed URL',not unknown['mineWorkUrl'])
                sql("UPDATE sys_file SET file_location=1 WHERE id='"+PREFIX+"file'")
                sql('RENAME TABLE teaching_additional_work TO '+FAULT_TABLE); fault=True
                status,body,_=api.request('GET',BASE,'student_a')
                check('query failure is retryable generic 503',status==503 and body and not body['success'] and body['code']==503 and not body.get('result') and body['message']=='作业列表暂时不可用，请稍后重试。')
                sql('RENAME TABLE '+FAULT_TABLE+' TO teaching_additional_work'); fault=False
                check('same session reads after database recovery',ids(read())==ids(all_rows))
                sql("UPDATE sys_depart SET del_flag='1' WHERE id='fixture_class_a'")
                check('deleted class no longer contributes assignments',not read())
                sql("UPDATE sys_depart SET del_flag='0' WHERE id='fixture_class_a'")
        finally:
            if fault: sql('RENAME TABLE '+FAULT_TABLE+' TO teaching_additional_work')
            for table in ('teaching_work_correct','teaching_work','teaching_additional_work','sys_file','sys_user_depart'):
                sql("DELETE FROM "+table+" WHERE id LIKE '"+PREFIX+"%'")
            file_path.unlink(missing_ok=True)
            for side, category in categories.items():
                sql("UPDATE sys_depart SET org_category='"+category+"',del_flag='0' WHERE id='fixture_class_"+side+"'")
        check('original rows restored', snapshot()==before)
        check('original files restored',file_snapshot()==before_files)
        check('fault table removed',sql("SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='"+FAULT_TABLE+"'")=='0')
        jar_hash=api.jar_sha256
    report={'observed_utc':datetime.now(timezone.utc).isoformat(),'jar_sha256':jar_hash,'expected_legacy':args.expect_legacy,
            'passed':sum(c['passed'] for c in cases),'total':len(cases),'cases':cases,'observed':observed,
            'scope':'Actual local synthetic authenticated HTTP, SQL, file bytes; cloud URL formatting only, no browser or real Qiniu upload acceptance.'}
    args.output.parent.mkdir(parents=True,exist_ok=True); args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(str(report['passed'])+'/'+str(report['total'])+' checks passed')
    return report['passed']==report['total']


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime',required=True,type=Path); parser.add_argument('--jar',type=Path)
    parser.add_argument('--output',required=True,type=Path); parser.add_argument('--expect-legacy',action='store_true')
    raise SystemExit(0 if verify(parser.parse_args()) else 1)
