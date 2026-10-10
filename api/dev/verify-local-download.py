#!/usr/bin/env python3
"""Real HTTP file access checks on the task-owned synthetic runtime."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from local_http import FixtureApi
from local_runtime import mysql_command

PREFIX = 'fixture_dprobe_'
DIR = 'download-access-probe'


def verify(args):
    cases = []
    with FixtureApi(args.runtime.resolve(), args.jar) as api:
        root = api.runtime / 'uploads'
        sandbox = root / DIR
        outside = api.runtime / 'download-probe-outside.txt'
        tables = ('sys_file', 'teaching_work', 'teaching_course', 'teaching_course_unit', 'sys_config', 'teaching_news', 'sys_data_log', 'teaching_additional_work')
        def sql(query):
            return subprocess.check_output(mysql_command(api.runtime) + ['teachingopen_dev','-e',query],text=True).strip()
        def snapshot():
            return {t: hashlib.sha256(sql('SELECT * FROM '+t+' ORDER BY id').encode()).hexdigest() for t in tables}
        def check(name, passed):
            cases.append({'case':name,'passed':bool(passed)})
            print(('PASS ' if passed else 'FAIL ')+name,flush=True)
        def get(key='private.txt', actor=None, method='GET', headers=None, raw_path=None):
            h = dict(headers or {})
            if actor: h['X-Access-Token'] = api.tokens[actor]
            req = Request('http://127.0.0.1:'+str(api.ports['backend'])+'/api'+(raw_path or '/sys/common/static/'+DIR+'/'+key),headers=h,method=method)
            try: response=urlopen(req,timeout=15)
            except HTTPError as error: response=error
            with response: return response.status,response.read(),response.headers
        def record(suffix, key, owner='student_a'):
            sql("INSERT INTO sys_file (id,create_by,file_path,file_name,file_location,file_type) VALUES ('"+PREFIX+suffix+"','fixture_"+owner+"','"+DIR+'/'+key+"','probe',1,2)")
        original = snapshot()
        if sandbox.exists() or outside.exists() or any(sql("SELECT COUNT(*) FROM "+t+" WHERE id LIKE '"+PREFIX+"%'")!='0' for t in tables): raise RuntimeError('Existing download probes')
        sandbox.mkdir()
        payload=b'SYNTHETIC-PRIVATE-DOWNLOAD-0123456789'
        (sandbox/'private.txt').write_bytes(payload)
        outside.write_bytes(b'SYNTHETIC-OUTSIDE-UPLOAD-ROOT')
        (sandbox/'link.txt').symlink_to(outside)
        try:
            for actor in ('admin','student_a','student_b','teacher_a','teacher_b'):
                api.login(actor)
                if not args.expect_legacy:
                    check('login issues media cookie '+actor,any(c.startswith('teaching_media') and 'HttpOnly' in c and 'SameSite=Strict' in c for c in api.last_response_headers.get_all('Set-Cookie',[])))
            record('private','private.txt')
            sql("INSERT INTO teaching_work (id,user_id,depart_id,work_name,work_file,work_type,work_status,create_by,create_time) VALUES ('"+PREFIX+"work','fixture_student_a','fixture_class_a','probe','"+PREFIX+"private','1',0,'fixture_student_a','2026-10-03 00:00:00')")
            if args.expect_legacy:
                for actor in (None,'student_b','teacher_b'):
                    s,b,h=get(actor=actor);check('legacy private download allowed '+str(actor),s==200 and b==payload)
                s,b,h=get(method='HEAD');check('legacy anonymous HEAD exposes size',s==200 and h.get('Content-Length')==str(len(payload)))
                s,b,h=get(headers={'Range':'bytes=0-4'});check('legacy anonymous range exposes bytes',s==206 and b==payload[:5])
                s,b,h=get('link.txt');check('legacy follows external symlink',s==200 and b==outside.read_bytes())
            else:
                def allow(name,key='private.txt',actor='student_a',expected=payload,headers=None):
                    s,b,h=get(key,actor,headers=headers);check(name,s==200 and b==expected and h.get('Cache-Control')=='no-store')
                def deny(name,key='private.txt',actor=None,method='GET',headers=None):
                    s,b,h=get(key,actor,method,headers);check(name,s in (401,403,404) and payload not in b and 'Content-Range' not in h)
                for actor in (None,'student_b','teacher_b'):
                    for method in ('GET','HEAD'):
                        deny('private '+method+' denied '+str(actor),actor=actor,method=method)
                    deny('private range denied '+str(actor),actor=actor,headers={'Range':'bytes=0-4'})
                for actor in ('student_a','teacher_a','admin'): allow('private permitted '+actor,actor=actor)
                deny('case-insensitive database lookup cannot alias a key','PRIVATE.TXT','student_a')
                for actor in (None,'admin'): deny('external symlink denied '+str(actor),'link.txt',actor)
                (sandbox/'inner-link.txt').symlink_to(sandbox/'private.txt')
                deny('internal symlink denied','inner-link.txt','admin')
                (sandbox/'orphan.txt').write_bytes(b'orphan')
                deny('unregistered orphan denied','orphan.txt','student_a')
                allow('admin may recover legacy orphan','orphan.txt','admin',b'orphan')
                s,b,h=get(actor='student_a')
                cookie=next((c for c in h.get_all('Set-Cookie',[]) if c.startswith('teaching_media')), '');cookie_pair=cookie.split(';')[0]
                check('media cookie is HttpOnly same-site host-only path-scoped', 'HttpOnly' in cookie and 'SameSite=Strict' in cookie and 'Path=/api/sys/common/static' in cookie and 'Domain=' not in cookie)
                allow('cookie-only image-style request permitted',actor=None,headers={'Cookie':cookie_pair})
                deny('foreign header overrides owner cookie',actor='student_b',headers={'Cookie':cookie_pair})
                deny('invalid header does not fall back to cookie',headers={'Cookie':cookie_pair,'X-Access-Token':'invalid-probe'})
                s,b,h=get(raw_path='/system/sysFile/list',headers={'Cookie':cookie_pair});check('media cookie cannot authorize normal API',s==401)
                for value,start,end in [('bytes=0-4',0,4),('bytes=5-',5,len(payload)-1),('bytes=-6',len(payload)-6,len(payload)-1),('bytes=2-999',2,len(payload)-1),('bytes=-999',0,len(payload)-1),('bytes=-99999999999999999999999',0,len(payload)-1),('bytes=2-99999999999999999999999',2,len(payload)-1)]:
                    s,b,h=get(actor='student_a',headers={'Range':value});check('range '+value,s==206 and b==payload[start:end+1] and h.get('Content-Range')=='bytes '+str(start)+'-'+str(end)+'/'+str(len(payload)) and h.get('Content-Length')==str(end-start+1))
                for value in ('bytes=999-', 'bytes=-0', 'bytes=9-2', 'bytes=bad', 'bytes=9999999999999999999999999999-'):
                    s,b,h=get(actor='student_a',headers={'Range':value});check('invalid/unsatisfiable '+value,s==416 and h.get('Content-Range')=='bytes */'+str(len(payload)) and b==b'')
                for hdr in ({'Range':'items=0-4'},{'Range':'bytes=0-1,3-4'},{'Range':'bytes=0-4','If-Range':'"old-version"'}):
                    s,b,h=get(actor='student_a',headers=hdr);check('unsupported/conditional range sends full entity '+str(hdr),s==200 and b==payload)
                s,b,h=get(actor='student_a',method='HEAD',headers={'Range':'bytes=0-4'});check('HEAD ignores range and sends no body',s==200 and b==b'' and h.get('Content-Length')==str(len(payload)) and 'Content-Range' not in h)
                (sandbox/'empty.txt').write_bytes(b'');record('empty','empty.txt')
                allow('empty file downloads','empty.txt',expected=b'')
                s,b,h=get('empty.txt','student_a',headers={'Range':'bytes=0-'});check('empty range is unsatisfiable',s==416 and h.get('Content-Range')=='bytes */0')
                for extension,mime,disposition in [('png','image/png','inline'),('mp4','video/mp4','inline'),('pdf','application/pdf','inline'),('svg','application/octet-stream','attachment'),('html','application/octet-stream','attachment'),('js','application/octet-stream','attachment')]:
                    name='mime.'+extension;(sandbox/name).write_bytes(b'fixture');record(extension,name)
                    s,b,h=get(name,'student_a');check('safe delivery '+extension,s==200 and h.get('Content-Type')==mime and h.get('Content-Disposition','').startswith(disposition+';') and h.get('X-Content-Type-Options')=='nosniff')
                sql("UPDATE teaching_work SET work_status=3 WHERE id='"+PREFIX+"work'")
                allow('published work anonymous bytes',actor=None)
                sql("UPDATE teaching_work SET work_status=0 WHERE id='"+PREFIX+"work'")
                deny('unpublish immediately denies anonymous range',headers={'Range':'bytes=0-4'})
                # Exact trusted resource references, never substring grants.
                resource=DIR+'/orphan.txt'
                sql("INSERT INTO teaching_course (id,course_name,show_home,course_cover,is_shared) VALUES ('"+PREFIX+"course','probe',1,'"+resource+"',0)")
                allow('home course cover remains public','orphan.txt',None,b'orphan')
                sql("UPDATE teaching_course SET course_cover='x"+resource+"' WHERE id='"+PREFIX+"course'")
                deny('substring course reference is not permission','orphan.txt')
                sql("UPDATE teaching_course SET course_cover='https://other.invalid/api/sys/common/static/"+resource+"' WHERE id='"+PREFIX+"course'")
                deny('external URL is not local permission','orphan.txt')
                sql("UPDATE teaching_course SET del_flag=1,course_cover='"+resource+"' WHERE id='"+PREFIX+"course'")
                deny('deleted home course cannot grant public access','orphan.txt')
                sql("UPDATE teaching_course SET del_flag=0,show_home=0,is_shared=0 WHERE id='"+PREFIX+"course'")
                deny('non-shared unauthorized course is denied','orphan.txt','student_a')
                sql("UPDATE teaching_course SET course_cover='',show_home=0 WHERE id='"+PREFIX+"course'")
                sql("INSERT INTO teaching_course_unit (id,unit_name,course_id,course_video,show_course_video) VALUES ('"+PREFIX+"unit','probe','fixture_course_a','"+resource+"',1)")
                allow('enrolled student reads visible unit video','orphan.txt','student_a',b'orphan')
                deny('foreign student denied unit video','orphan.txt','student_b')
                deny('anonymous denied unit video','orphan.txt')
                sql("UPDATE teaching_course_unit SET del_flag=1 WHERE id='"+PREFIX+"unit'")
                deny('deleted unit cannot grant media access','orphan.txt','student_a')
                sql("UPDATE teaching_course_unit SET del_flag=0 WHERE id='"+PREFIX+"unit'")
                sql("UPDATE teaching_course_unit SET show_course_video=0 WHERE id='"+PREFIX+"unit'")
                deny('hidden unit video denied student','orphan.txt','student_a')
                sql("UPDATE teaching_course_unit SET show_course_video=NULL WHERE id='"+PREFIX+"unit'")
                deny('null visibility remains hidden','orphan.txt','student_a')
                sql("UPDATE teaching_course_unit SET course_video='',media_content='<img src=\"/api/sys/common/static/"+resource+"\">' WHERE id='"+PREFIX+"unit'")
                allow('authorized unit rich-text media','orphan.txt','student_a',b'orphan')
                deny('private rich-text media denied foreign student','orphan.txt','student_b')
                sql("DELETE FROM teaching_course_unit WHERE id='"+PREFIX+"unit'")
                sql("INSERT INTO sys_config (id,config_key,config_value,config_enabled) VALUES ('"+PREFIX+"config','probe','<img src=\"/api/sys/common/static/"+resource+"\">',1)")
                allow('enabled configuration image public','orphan.txt',None,b'orphan')
                sql("UPDATE sys_config SET config_enabled=0 WHERE id='"+PREFIX+"config'")
                deny('disabled configuration does not expose file','orphan.txt')
                sql("INSERT INTO teaching_news (id,news_title,news_content,news_status) VALUES ('"+PREFIX+"news','probe','<img src=\"/api/sys/common/static/"+resource+"\">',1)")
                allow('published news media public','orphan.txt',None,b'orphan')
                sql("UPDATE teaching_news SET news_status=0 WHERE id='"+PREFIX+"news'")
                deny('draft news media denied','orphan.txt')
                sql("INSERT INTO teaching_additional_work (id,work_name,work_dept,work_url,status) VALUES ('"+PREFIX+"additional','probe','fixture_class_a','"+resource+"',1)")
                allow('assigned additional-work starter readable','orphan.txt','student_a',b'orphan')
                deny('unassigned student denied starter','orphan.txt','student_b')
                sql("UPDATE teaching_additional_work SET status=0 WHERE id='"+PREFIX+"additional'")
                deny('closed additional-work starter denied','orphan.txt','student_a')
                sql("DELETE FROM teaching_additional_work WHERE id='"+PREFIX+"additional'")
                # History grants only the actual old attachment fields to current work owners/teachers.
                (sandbox/'old.txt').write_bytes(b'old');record('old','old.txt','student_b')
                sql("INSERT INTO sys_data_log (id,data_table,data_id,data_content,data_version) VALUES ('"+PREFIX+"history','teaching_work','"+PREFIX+"work','{\"workFile\":\""+PREFIX+"old\"}',1)")
                allow('owner can reopen historical attachment','old.txt','student_a',b'old')
                allow('class teacher can read historical attachment','old.txt','teacher_a',b'old')
                deny('foreign teacher denied history','old.txt','teacher_b')
                sql("UPDATE teaching_work SET work_status=3 WHERE id='"+PREFIX+"work'")
                deny('publishing current work does not publish history','old.txt')
                sql("UPDATE sys_data_log SET data_content='{\"workName\":\""+PREFIX+"old\"}' WHERE id='"+PREFIX+"history'")
                deny('history name mentioning file is not authority','old.txt','student_a')
                for key in ('../download-probe-outside.txt','%2e%2e/download-probe-outside.txt','%5cprivate.txt','missing.txt','private.txt,'):
                    s,b,h=get(key,'admin');check('invalid/missing path refuses bytes '+key,s in (400,401,403,404) and payload not in b and outside.read_bytes() not in b)
                # A revoked cookie remains denied even for the owner; the current work is private again.
                sql("UPDATE teaching_work SET work_status=0 WHERE id='"+PREFIX+"work'")
                # Logout actually revokes a previously copied cookie.
                s,b,h=get(actor='student_a',raw_path='/sys/logout')
                check('logout expires media cookie','Max-Age=0' in h.get('Set-Cookie',''))
                deny('revoked cookie rejected',headers={'Cookie':cookie_pair})
            jar_hash=api.jar_sha256
        finally:
            for t in tables: sql("DELETE FROM "+t+" WHERE id LIKE '"+PREFIX+"%'")
            for p in sandbox.iterdir(): p.unlink()
            sandbox.rmdir();outside.unlink()
        check('fixture rows restored',snapshot()==original)
        check('probe files and links removed',not sandbox.exists() and not outside.exists())
    report={'observed_utc':datetime.now(timezone.utc).isoformat(),'jar_sha256':jar_hash,'expected_legacy':args.expect_legacy,'passed':sum(c['passed'] for c in cases),'total':len(cases),'cases':cases}
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(str(report['passed'])+'/'+str(report['total'])+' checks passed')
    return report['passed']==report['total']

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime',type=Path,required=True);parser.add_argument('--jar',type=Path)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--expect-legacy',action='store_true')
    raise SystemExit(0 if verify(parser.parse_args()) else 1)
