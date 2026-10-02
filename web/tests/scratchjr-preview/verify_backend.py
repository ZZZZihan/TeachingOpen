"""Focused real-API ScratchJr persistence probe against an explicitly verified localtest JAR.
Requires the candidate's api/dev FixtureApi helpers (PR24). Never uses a browser session.
"""
import argparse, hashlib, json, subprocess, sys
from http.cookies import SimpleCookie
from pathlib import Path
from urllib.parse import quote, urlparse, urljoin
from urllib.request import Request, urlopen

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--runtime', type=Path, required=True)
p.add_argument('--jar', type=Path, required=True)
p.add_argument('--backend-dev', type=Path, required=True)
p.add_argument('--output', type=Path, required=True)
p.add_argument('--fixtures', type=Path, required=True, help='Browser-generated version1/2.sjr and matching PNG covers')
a = p.parse_args()
sys.path.insert(0, str(a.backend_dev.resolve()))
from local_http import FixtureApi
from local_runtime import mysql_command

prefix = 'scratchjr-pr28-probe'
cases = []
def check(name, passed):
    cases.append({'case': name, 'passed': bool(passed)})
    print(('PASS ' if passed else 'FAIL ') + name, flush=True)
    if not passed: raise AssertionError(name)

with FixtureApi(a.runtime, a.jar) as api:
    def sql(q): return subprocess.check_output(mysql_command(api.runtime)+['teachingopen_dev','-e',q], text=True).strip()
    def rows(): return {t: hashlib.sha256(sql('SELECT * FROM '+t+' ORDER BY id').encode()).hexdigest() for t in ['teaching_work','sys_file','sys_data_log']}
    def files(): return {str(p.relative_to(api.runtime/'uploads')): hashlib.sha256(p.read_bytes()).hexdigest() for p in (api.runtime/'uploads').rglob('*') if p.is_file()}
    assert not (api.runtime/'uploads'/prefix).exists()
    assert sql("SELECT COUNT(*) FROM teaching_work WHERE work_name LIKE '"+prefix+"%'") == '0'
    before_rows, before_files = rows(), files()
    base = 'http://127.0.0.1:'+str(api.ports['backend'])
    owned_ids = []
    def transfer(code, name):
        boundary='scratchjr-probe-boundary'
        body=('--'+boundary+'\r\nContent-Disposition: form-data; name="bizPath"\r\n\r\n'+prefix+'\r\n--'+boundary+'\r\nContent-Disposition: form-data; name="file"; filename="'+name+'"\r\nContent-Type: application/octet-stream\r\n\r\n').encode()+code+('\r\n--'+boundary+'--\r\n').encode()
        req=Request(base+'/api/sys/common/upload',body,{'Content-Type':'multipart/form-data; boundary='+boundary,'X-Access-Token':api.tokens['student_a']})
        with urlopen(req,timeout=15) as r: uploaded=json.loads(r.read())
        check('upload exact ScratchJr bytes '+name,uploaded.get('success') and uploaded['message'].startswith(prefix+'/') and (api.runtime/'uploads'/uploaded['message']).read_bytes()==code)
        _,record,_=api.request('POST','/system/sysFile/add','student_a',{'fileType':2,'fileName':name,'filePath':uploaded['message'],'fileLocation':1,'fileTag':'学生作业-scratchjr'})
        check('register matching owned ScratchJr file '+name, record.get('success') and record['result']['filePath']==uploaded['message'])
        return record['result']['id']
    try:
        api.login('student_a')
        cookies=SimpleCookie();cookies.load(api.last_response_headers.get('Set-Cookie',''))
        cookie='; '.join(k+'='+v.value for k,v in cookies.items())
        check('actual login supplies media cookie', bool(cookie))
        api.login('student_b')
        status,body,_=api.request('POST','/teaching/teachingWork/submit',data={'workName':prefix,'workType':3,'workStatus':1,'workFile':'missing'})
        check('anonymous editor submission rejected',status==401 and not body.get('success'))
        first_id=None
        for n in [1,2]:
            code=(a.fixtures/('version'+str(n)+'.sjr')).read_bytes()
            cover=(a.fixtures/('version'+str(n)+'.png')).read_bytes()
            assert code.startswith(b'PK') and cover.startswith(bytes.fromhex('89504e470d0a1a0a'))
            fid=transfer(code,'version'+str(n)+'.sjr')
            cid=transfer(cover,'version'+str(n)+'.png')
            payload={'id':first_id or '', 'workName':prefix+'-renamed-'+str(n),'workType':3,'workStatus':n-1,'workFile':fid,'workCover':cid,'workScene':'create','courseId':'','additionalId':'','departId':'','hasCloudData':False}
            status,result,_=api.request('POST','/teaching/teachingWork/submit','student_a',payload)
            check('real backend saves version '+str(n),status==200 and result.get('success') and result.get('result',{}).get('id'))
            wid=result['result']['id'];assert wid.isalnum()
            if first_id is None: first_id=wid;owned_ids.append(wid)
            check('same work ID after version '+str(n),wid==first_id)
            _,info,_=api.request('GET','/teaching/teachingWork/studentWorkInfo?workId='+wid,'student_a')
            check('reopen metadata retains name type and file '+str(n),info.get('success') and info['result']['workName']==payload['workName'] and str(info['result']['workType'])=='3' and info['result']['workFile']==fid and info['result']['workCover']==cid and int(info['result']['workStatus'])==n-1)
            for label,field,expected in [('project','workFileKey_url',code),('cover','coverFileKey_url',cover)]:
                file_url=urljoin(base,info['result'].get(field,''));url=urlparse(file_url)
                assert url.scheme=='http' and url.hostname=='127.0.0.1' and url.port==api.ports['backend']
                with urlopen(Request(file_url,headers={'Cookie':cookie}),timeout=15) as r: downloaded=r.read();status=r.status
                check('media-cookie-only '+label+' download equals browser bytes '+str(n),status==200 and downloaded==expected)
        check('rename did not create duplicate work',sql("SELECT COUNT(*) FROM teaching_work WHERE work_name LIKE '"+prefix+"%'")=='1')
        status,denied,_=api.request('GET','/teaching/teachingWork/studentWorkInfo?workId='+first_id,'student_b')
        check('other student cannot reopen private submission',not denied.get('success'))
    finally:
        for wid in owned_ids:
            sql("DELETE FROM sys_data_log WHERE data_table='teaching_work' AND data_id='"+wid+"'")
            sql("DELETE FROM teaching_work WHERE id='"+wid+"' AND create_by='fixture_student_a'")
        sql("DELETE FROM sys_file WHERE file_path LIKE '"+prefix+"/%' AND create_by='fixture_student_a'")
        directory=api.runtime/'uploads'/prefix
        if directory.exists():
            for item in directory.iterdir():
                assert item.is_file() and not item.is_symlink();item.unlink()
            directory.rmdir()
        check('work file and history rows restored',rows()==before_rows)
        check('original upload bytes restored',files()==before_files)
        a.output.write_text(json.dumps({'jar_sha256':api.jar_sha256,'cases':cases,'passed':sum(c['passed'] for c in cases),'total':len(cases),'scope':'Real Java API and file HTTP; no authenticated browser acceptance.','before_rows':before_rows,'after_rows':rows(),'files_restored':files()==before_files},ensure_ascii=False,indent=2)+'\n')
