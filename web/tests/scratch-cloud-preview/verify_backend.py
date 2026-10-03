"""Exercise the shipped cloud provider on an explicitly guarded synthetic backend."""
import argparse,json,subprocess,sys
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__)
for name in ('runtime','jar','backend-dev','output'):p.add_argument('--'+name,type=Path,required=True)
a=p.parse_args();sys.path.insert(0,str(a.backend_dev.resolve()))
from local_http import FixtureApi
from local_recovery import database_inventory,file_inventory,private_write,sql
prefix='fixture_cloud_client_'
with FixtureApi(a.runtime,a.jar) as api:
    before,files=database_inventory(api.runtime),file_inventory(api.runtime/'uploads')
    if sql(api.runtime,"SELECT COUNT(*) FROM teachingopen_dev.teaching_work WHERE id LIKE 'fixture_cloud_client_%'")!='0' or api.cache('KEYS','scratch:cloud:'+prefix+'*'):raise RuntimeError('Preserve existing probe records')
    try:
        for suffix,status,value in [('public','3','41'),('private','0','99'),('seed','0','0')]:
            ident=prefix+suffix
            sql(api.runtime,"INSERT INTO teachingopen_dev.teaching_work (id,create_by,create_time,work_file,user_id,depart_id,work_name,work_type,work_status,del_flag,work_scene) VALUES ('"+ident+"','fixture_admin','2026-10-03 09:00:00','fixture_file_a','fixture_student_a','fixture_class_a','合成客户端云变量','2','"+status+"',0,'create')")
            api.cache('HSET','scratch:cloud:'+ident,'score',json.dumps(value))
        api.login('student_a');api.login('student_b')
        script=Path(__file__).resolve().parents[1]/'scratch-cloud-live.cjs'
        process=subprocess.run(['node',str(script)],input=json.dumps({'origin':'http://127.0.0.1:'+str(api.ports['frontend']),'ownerToken':api.tokens['student_a'],'otherToken':api.tokens['student_b'],'publicId':prefix+'public','privateId':prefix+'private','seedId':prefix+'seed'}),text=True,capture_output=True,timeout=35)
        if process.returncode:
            private_write(a.output.with_suffix('.failure.txt'),process.stdout+'\n'+process.stderr)
            raise RuntimeError('Live client failed; private diagnostic retained')
        result=json.loads(process.stdout)
        result['cases'].append({'case':'real Redis seed and final public/private values match expected writes','passed':api.cache('HGET','scratch:cloud:'+prefix+'seed','created')==json.dumps('7') and api.cache('HGET','scratch:cloud:'+prefix+'public','score')==json.dumps('45') and api.cache('HGET','scratch:cloud:'+prefix+'private','score')==json.dumps('99')})
    finally:
        for key in api.cache('KEYS','scratch:cloud:'+prefix+'*').splitlines():api.cache('DEL',key)
        sql(api.runtime,"DELETE FROM teachingopen_dev.teaching_work WHERE id LIKE 'fixture_cloud_client_%'")
    after=database_inventory(api.runtime)
    result['changed_database_tables']=[t for t in before if before[t]!=after[t]]
    result['cases'].append({'case':'all non-audit database tables restored','passed':all(before[t]==after[t] for t in before if t!='sys_log')})
    result['cases'].append({'case':'all attachment bytes unchanged','passed':files==file_inventory(api.runtime/'uploads')})
    result.update(jar_sha256=api.jar_sha256,total=len(result['cases']),passed=sum(c['passed'] for c in result['cases']))
    private_write(a.output,json.dumps(result,indent=2)+'\n');print(str(result['passed'])+'/'+str(result['total']))
    if result['passed']!=result['total']:raise SystemExit(1)
