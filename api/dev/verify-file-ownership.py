#!/usr/bin/env python3
"""Verify file ownership through actual APIs on the isolated synthetic runtime."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import secrets
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen
from local_http import FixtureApi
from local_runtime import mysql_command

PREFIX = 'fixture_fprobe_'
NAME = 'file-owner-probe-'
BASE = '/system/sysFile/'


def verify(args):
    cases = []
    with FixtureApi(args.runtime.resolve(), args.jar) as api:
        uploads = api.runtime / 'uploads'
        owned = []
        added_ids = []
        owned_dirs = []
        optional_media_created = False

        def sql(query):
            return subprocess.check_output(mysql_command(api.runtime) + ['teachingopen_dev', '-e', query], text=True).strip()

        def snapshot():
            return {t: hashlib.sha256(sql('SELECT * FROM ' + t + ' ORDER BY id').encode()).hexdigest()
                    for t in ('sys_file', 'teaching_work', 'sys_config', 'sys_data_log', 'teaching_course', 'teaching_course_unit', 'teaching_additional_work', 'teaching_news', 'teaching_scratch_assets')}

        def files():
            return {str(p.relative_to(uploads)): hashlib.sha256(p.read_bytes()).hexdigest() for p in uploads.rglob('*') if p.is_file()}

        def check(name, passed):
            cases.append({'case': name, 'passed': bool(passed)})
            print(('PASS ' if passed else 'FAIL ') + name, flush=True)

        def call(path, actor='student_a', method='GET', data=None):
            return api.request(method, BASE + path, actor, data)[:2]

        def ok(response):
            return response[0] == 200 and response[1] and response[1].get('success') is True

        def fixture(suffix, actor='student_b'):
            ident = PREFIX + suffix
            path = uploads / (NAME + suffix + '.txt')
            path.write_bytes(('synthetic ' + suffix).encode()); owned.append(path)
            sql("INSERT INTO sys_file (id,create_by,create_time,file_path,file_name,file_location,file_type) VALUES ('" + ident + "','fixture_" + actor + "','2026-10-03 00:00:00','" + path.name + "','" + path.name + "',1,2)")
            return ident, path

        def denied(name, path, actor='student_a', method='GET', data=None, code=510):
            before, before_files = snapshot(), files()
            status, body = call(path, actor, method, data)
            check(name, status == (401 if code == 401 else 200) and body and body.get('success') is False
                  and body.get('code') == code and not body.get('result') and snapshot() == before and files() == before_files)

        def upload(filename):
            boundary='fixture-'+secrets.token_hex(12)
            payload=('--'+boundary+'\r\nContent-Disposition: form-data; name="file"; filename="'+filename+'"\r\nContent-Type: application/octet-stream\r\n\r\nprint("synthetic")\r\n--'+boundary+'--\r\n').encode()
            req=Request('http://127.0.0.1:'+str(api.ports['backend'])+'/api/sys/common/upload',payload,{'Content-Type':'multipart/form-data; boundary='+boundary,'X-Access-Token':api.tokens['student_a']},method='POST')
            try: response=urlopen(req,timeout=15)
            except HTTPError as error: response=error
            with response:
                body=json.loads(response.read())
                if body.get('success'):
                    key=body['message'];path=uploads/key
                    if path.parent!=uploads: raise RuntimeError('Unexpected probe upload path')
                    owned.append(path)
                    added_ids.extend(sql("SELECT id FROM sys_file WHERE file_path='"+key+"'").splitlines())
                return response.status,body

        original, original_files = snapshot(), files()
        if list(uploads.glob(NAME + '*')) or any(sql("SELECT COUNT(*) FROM " + t + " WHERE id LIKE '" + PREFIX + "%'") != '0' for t in ('sys_file','teaching_work')):
            raise RuntimeError('Existing file ownership probes')
        try:
            for actor in ('admin','teacher_a','teacher_b','student_a','student_b'): api.login(actor)
            a, pa = fixture('a','student_a'); b, pb = fixture('b')
            if args.expect_legacy:
                status, body = call('list?pageSize=100')
                check('legacy student list exposes other uploader record', ok((status,body)) and b in {r['id'] for r in body['result']['records']})
                check('legacy student reads other file path', ok(call('queryById?id=' + b)))
                status, body = call('add', method='POST', data={'filePath':pb.name,'fileName':NAME+'forged','fileLocation':1,'createBy':'fixture_student_a'})
                check('legacy student claims foreign physical path', ok((status,body)) and body['result']['createBy']=='fixture_student_a')
                if ok((status,body)): added_ids.append(body['result']['id'])
                status, body = call('add', method='POST', data={'filePath':pa.name,'fileName':NAME+'spoof','fileLocation':1,'createBy':'fixture_admin','delFlag':1})
                check('legacy student forges creator and deletion state', ok((status,body)) and body['result']['createBy']=='fixture_admin' and body['result']['delFlag']==1)
                if ok((status,body)): added_ids.append(body['result']['id'])
                check('legacy student edits another file metadata', ok(call('edit', method='PUT', data={'id':b,'fileName':NAME+'changed','createBy':'fixture_student_a'})) and sql("SELECT create_by FROM sys_file WHERE id='"+b+"'")=='fixture_student_a')
                target, path = fixture('delete_id')
                check('legacy student deletes foreign bytes by ID', ok(call('delete?id='+target,method='DELETE')) and not path.exists())
                target, path = fixture('delete_path')
                check('legacy student deletes foreign bytes by path', ok(call('deleteByPath?filePath='+quote(path.name),method='DELETE')) and not path.exists())
                target, path = fixture('delete_batch'); mine, mine_path = fixture('batch_mine','student_a')
                check('legacy mixed batch deletes other owner too', ok(call('deleteBatch?ids='+mine+','+target,method='DELETE')) and not path.exists() and not mine_path.exists())
            else:
                for actor in ('student_a','student_b','teacher_a','teacher_b','admin'):
                    _, body = call('list?pageSize=100&createBy=fixture_student_b&column=create_by&order=asc', actor)
                    rows = (body.get('result') or {}).get('records', [])
                    check(actor+' list respects server ownership', body.get('success') and (actor=='admin' or all(r['createBy']=='fixture_'+actor for r in rows)))
                check('owner reads own file', ok(call('queryById?id='+a)))
                check('administrator reads foreign file', ok(call('queryById?id='+b,'admin')))
                for actor in ('student_a','teacher_a','teacher_b'):
                    denied(actor+' cannot read unrelated upload','queryById?id='+b,actor)
                    denied(actor+' cannot rename unrelated upload','edit',actor,'PUT',{'id':b,'createBy':'fixture_'+actor,'fileName':'forged'})
                    for route in ('delete?id='+b,'deleteByPath?filePath='+quote(pb.name),'deleteBatch?ids='+b):
                        denied(actor+' denied '+route.split('?')[0],route,actor,'DELETE')
                    denied(actor+' cannot export all files','exportXls',actor)
                    denied(actor+' cannot import metadata','importExcel',actor,'POST')
                for path, location in [(pb.name,1),('../escape',1),('nonexistent.sb3',1),('foreign/cloud.sb3',2)]:
                    denied('untrusted path cannot become owned '+path,'add',method='POST',data={'filePath':path,'fileLocation':location,'fileName':'forged','createBy':'fixture_student_a'})
                denied('mixed-owner batch changes neither file','deleteBatch?ids='+a+','+b,method='DELETE')
                denied('missing item in batch changes no bytes','deleteBatch?ids='+a+',missing-file',method='DELETE')
                denied('empty batch is rejected','deleteBatch?ids=',method='DELETE',code=500)
                request=Request('http://127.0.0.1:'+str(api.ports['backend'])+'/api'+BASE+'exportXls',headers={'X-Access-Token':api.tokens['admin']})
                with urlopen(request,timeout=15) as exported:
                    check('administrator receives real binary XLS export',exported.status==200 and exported.read(8)==bytes.fromhex('d0cf11e0a1b11ae1'))
                before_path = sql("SELECT CONCAT_WS('|',create_by,file_path,file_location,del_flag) FROM sys_file WHERE id='"+a+"'")
                forged={'id':b,'filePath':pa.name,'fileLocation':1,'fileName':'Renamed project','createBy':'fixture_admin','delFlag':1,'fileTag':'python','fileType':2,'sysOrgCode':'spoof'}
                _, body=call('add',method='POST',data=forged)
                check('repeat registration keeps server identity and only updates display', body.get('success') and body['result']['id']==a and body['result']['createBy']=='fixture_student_a' and body['result']['delFlag']==0 and body['result']['fileName']=='Renamed project' and sql("SELECT CONCAT_WS('|',create_by,file_path,file_location,del_flag) FROM sys_file WHERE id='"+a+"'")==before_path)
                forged.update(id=a,filePath=pb.name,fileLocation=2,createBy='fixture_student_b',fileName='Edited name')
                check('edit cannot rewrite path location creator or deletion state', ok(call('edit',method='PUT',data=forged)) and sql("SELECT CONCAT_WS('|',create_by,file_path,file_location,del_flag) FROM sys_file WHERE id='"+a+"'")==before_path)
                for file_type in (4,5):
                    check('upstream file category '+str(file_type)+' remains editable',ok(call('edit',method='PUT',data={'id':a,'fileType':file_type})))
                for values in ({'fileName':''},{'fileName':'x'*129},{'fileTag':'x'*33},{'fileType':99}):
                    denied('invalid display is atomic '+next(iter(values)), 'edit',method='PUT',data=dict(id=a,**values),code=500)
                # Exercise rich-resource references in the current schema and its optional media module.
                rid=PREFIX+'resource'
                resources=[
                    ("teaching_course", "id,course_name,course_cover", "'"+rid+"','probe','"+pa.name+"'"),
                    ("teaching_course_unit", "id,unit_name,course_id,media_content", "'"+rid+"','probe','fixture_course_a','"+pa.name+"'"),
                    ("teaching_additional_work", "id,work_dept,work_document_url", "'"+rid+"','','"+pa.name+"'"),
                    ("teaching_news", "id,news_content", "'"+rid+"','<img src="+pa.name+">'"),
                    ("teaching_scratch_assets", "id,asset_type,md5_ext", "'"+rid+"',1,'"+pa.name+"'")]
                for table,cols,values in resources:
                    sql('INSERT INTO '+table+' ('+cols+') VALUES ('+values+')')
                    denied(table+' resource preserves referenced file','delete?id='+a,method='DELETE',code=500)
                    sql("DELETE FROM "+table+" WHERE id='"+rid+"'")
                if sql("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name='teaching_course_media'")!='0':
                    raise RuntimeError('Expected baseline without optional media table; refusing to alter existing schema')
                sql('CREATE TABLE teaching_course_media (id VARCHAR(36) PRIMARY KEY, media_path VARCHAR(256))')
                optional_media_created=True
                sql("INSERT INTO teaching_course_media VALUES ('"+rid+"','"+pa.name+"')")
                denied('optional media module protects its referenced file','delete?id='+a,method='DELETE',code=500)
                sql('DROP TABLE teaching_course_media');optional_media_created=False
                # A legitimate shared work permits reads, but never transfers mutation rights.
                wid=PREFIX+'shared'
                sql("INSERT INTO teaching_work (id,user_id,depart_id,work_name,work_type,work_file,work_status,create_by,create_time) VALUES ('"+wid+"','fixture_student_a','fixture_class_a','"+NAME+"shared','1','"+b+"',0,'fixture_student_a','2026-10-03 00:00:00')")
                check('recipient reads shared attachment',ok(call('queryById?id='+b)))
                check('class teacher reads shared attachment',ok(call('queryById?id='+b,'teacher_a')))
                denied('other teacher cannot read private shared attachment','queryById?id='+b,'teacher_b')
                denied('uploader cannot delete still-referenced file','delete?id='+b,'student_b','DELETE',code=500)
                denied('administrator cannot delete still-referenced file','delete?id='+b,'admin','DELETE',code=500)
                sql("UPDATE teaching_work SET work_status=3 WHERE id='"+wid+"'")
                check('signed-in viewer can resolve published attachment',ok(call('queryById?id='+b,'teacher_b')))
                hid=PREFIX+'history'
                sql("INSERT INTO sys_data_log (id,data_table,data_id,data_content,data_version) VALUES ('"+hid+"','teaching_work','"+wid+"','{\"workFile\":\""+a+"\"}',1)")
                denied('existing work history protects previous attachment','delete?id='+a,method='DELETE',code=500)
                sql("DELETE FROM sys_data_log WHERE id='"+hid+"'")
                sql("DELETE FROM teaching_work WHERE id='"+wid+"'")
                # Preserve course, rich-text, history and alias references before reclaiming bytes.
                cid=PREFIX+'config'
                sql("INSERT INTO sys_config (id,config_key,config_value) VALUES ('"+cid+"','"+cid+"','<img src=\"/api/sys/common/static/"+pa.name+"\">')")
                denied('configuration HTML reference protects bytes','delete?id='+a,method='DELETE',code=500)
                sql("DELETE FROM sys_config WHERE id='"+cid+"'")
                alias=PREFIX+'alias';sql("INSERT INTO sys_file (id,file_path,file_location,create_by) VALUES ('"+alias+"','"+pa.name+"',1,'fixture_student_b')")
                denied('physical alias prevents reclamation','delete?id='+a,method='DELETE',code=500)
                denied('ambiguous path cannot select an arbitrary record','deleteByPath?filePath='+quote(pa.name),method='DELETE',code=500)
                sql("DELETE FROM sys_file WHERE id='"+alias+"'")
                # The actual multipart request must establish ownership before returning success.
                status, body=upload('owned.py')
                key=body['message']; ident=sql("SELECT id FROM sys_file WHERE file_path='"+key+"'")
                check('real upload creates server-owned live record', status==200 and body.get('success') and len(ident)==32 and sql("SELECT CONCAT_WS('|',create_by,del_flag,file_location) FROM sys_file WHERE id='"+ident+"'")=='fixture_student_a|0|1')
                _,registered=call('add',method='POST',data={'filePath':key,'fileLocation':1,'fileName':'Project.py','createBy':'fixture_student_b'})
                check('editor registration reuses uploaded record',registered.get('success') and registered['result']['id']==ident and registered['result']['createBy']=='fixture_student_a')
                denied('other student cannot claim freshly uploaded bytes','add','student_b','POST',{'filePath':key,'fileLocation':1,'createBy':'fixture_student_b'})
                check('owner removes unused uploaded object',ok(call('delete?id='+ident,method='DELETE')) and not (uploads/key).exists())
                # Fail the database write after streaming succeeds; no object may be left behind.
                sql("CREATE TRIGGER "+PREFIX+"reject BEFORE INSERT ON sys_file FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='synthetic upload registration failure'")
                before,before_files=snapshot(),files()
                _,body=upload('db-fail.py')
                check('metadata write failure removes new bytes and reports failure',body.get('success') is False and snapshot()==before and files()==before_files and 'synthetic' not in body.get('message',''))
                sql('DROP TRIGGER '+PREFIX+'reject')
                # A filesystem error must not be reported as success or discard the metadata.
                directory=uploads/(NAME+'directory');directory.mkdir(); owned_dirs.append(directory)
                target=PREFIX+'directory';sql("INSERT INTO sys_file (id,file_path,file_location,create_by) VALUES ('"+target+"','"+directory.name+"',1,'fixture_student_a')")
                denied('unreclaimable directory preserves metadata','delete?id='+target,method='DELETE',code=500)
                link=uploads/(NAME+'link');link.symlink_to(pa);owned.append(link)
                target=PREFIX+'link';sql("INSERT INTO sys_file (id,file_path,file_location,create_by) VALUES ('"+target+"','"+link.name+"',1,'fixture_student_a')")
                denied('legacy symlink metadata cannot delete another physical object','delete?id='+target,method='DELETE',code=500)
                check('owner deletes unreferenced own bytes by path' ,ok(call('deleteByPath?filePath='+quote(pa.name),method='DELETE')) and not pa.exists())
                check('administrator deletes unreferenced foreign bytes',ok(call('delete?id='+b,'admin','DELETE')) and not pb.exists())
                c,pc=fixture('batch1','student_a');d,pd=fixture('batch2','student_a')
                check('authorized batch deletes both exact objects',ok(call('deleteBatch?ids='+c+','+d,method='DELETE')) and not pc.exists() and not pd.exists())
                for endpoint in ('getToken','getTokenByKey?key=foreign/file'):
                    status,body,_=api.request('GET','/common/qiniu/'+endpoint,'student_a')
                    check('local runtime does not issue cloud credentials '+endpoint.split('?')[0],status==200 and not body.get('success') and not body.get('result'))
                for route in ('list','queryById?id='+a):
                    denied('anonymous '+route.split('?')[0]+' requires login',route,actor=None,code=401)
            jar_hash = api.jar_sha256
        finally:
            sql('DROP TRIGGER IF EXISTS '+PREFIX+'reject')
            if optional_media_created: sql('DROP TABLE teaching_course_media')
            for table in ('teaching_course','teaching_course_unit','teaching_additional_work','teaching_news','teaching_scratch_assets'):
                sql("DELETE FROM "+table+" WHERE id LIKE '"+PREFIX+"%'")
            sql("DELETE FROM sys_config WHERE id LIKE '"+PREFIX+"%'; DELETE FROM sys_data_log WHERE id LIKE '"+PREFIX+"%'")
            for ident in added_ids: sql("DELETE FROM sys_file WHERE id='"+ident+"'")
            sql("DELETE FROM teaching_work WHERE id LIKE '"+PREFIX+"%'; DELETE FROM sys_file WHERE id LIKE '"+PREFIX+"%'")
            for path in owned: path.unlink(missing_ok=True)
            for path in owned_dirs: path.rmdir()
        check('original file and work rows restored', snapshot()==original)
        check('original upload bytes restored', files()==original_files)
    report={'observed_utc':datetime.now(timezone.utc).isoformat(),'jar_sha256':jar_hash,'expected_legacy':args.expect_legacy,
            'passed':sum(c['passed'] for c in cases),'total':len(cases),'cases':cases}
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(str(report['passed'])+'/'+str(report['total'])+' checks passed')
    return report['passed']==report['total']


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime',required=True,type=Path);parser.add_argument('--jar',type=Path)
    parser.add_argument('--output',required=True,type=Path);parser.add_argument('--expect-legacy',action='store_true')
    raise SystemExit(0 if verify(parser.parse_args()) else 1)
