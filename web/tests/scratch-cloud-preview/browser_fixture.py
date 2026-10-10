"""Own synthetic public Scratch fixture; no browser credentials or authentication bypass."""
import argparse,importlib.util,json,sys,zipfile
from pathlib import Path
p=argparse.ArgumentParser()
p.add_argument('action',choices=['setup','send','private','public','inspect','cleanup'])
for name in ['backend-dev','runtime','jar','state']:p.add_argument('--'+name,type=Path,required=True)
p.add_argument('--value',default='53');a=p.parse_args();sys.path.insert(0,str(a.backend_dev.resolve()))
from local_http import FixtureApi
from local_recovery import database_inventory,file_inventory,private_write,sql
ident='fixture_cloud_browser_public';fid='fixture_cloud_browser_file';relative='fixture-cloud-browser/sample.sb3';key='scratch:cloud:'+ident;name='☁ 分数'
with FixtureApi(a.runtime,a.jar) as api:
    target=api.runtime/'uploads'/relative
    if a.action=='setup':
        if a.state.exists() or target.parent.exists() or sql(api.runtime,"SELECT COUNT(*) FROM teachingopen_dev.teaching_work WHERE id='"+ident+"'")!='0' or sql(api.runtime,"SELECT COUNT(*) FROM teachingopen_dev.sys_file WHERE id='"+fid+"'")!='0' or api.cache('EXISTS',key)!='0':raise RuntimeError('Preserve existing data')
        private_write(a.state,json.dumps({'database':database_inventory(api.runtime),'files':file_inventory(api.runtime/'uploads')}))
        target.parent.mkdir()
        seed=Path(__file__).resolve().parents[1]/'scratch-preview/sample.sb3'
        with zipfile.ZipFile(seed) as source,zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as out:
            data=json.loads(source.read('project.json'));stage=data['targets'][0];stage['variables']={'cloud-score':[name,0,True]}
            stage['blocks']={'flag':{'opcode':'event_whenflagclicked','next':'set','parent':None,'inputs':{},'fields':{},'shadow':False,'topLevel':True,'x':30,'y':30},'set':{'opcode':'data_setvariableto','next':None,'parent':'flag','inputs':{'VALUE':[1,[4,'7']]},'fields':{'VARIABLE':[name,'cloud-score']},'shadow':False,'topLevel':False}}
            data['monitors']=[{'id':'cloud-score','mode':'default','opcode':'data_variable','params':{'VARIABLE':name},'spriteName':None,'value':0,'width':0,'height':0,'x':12,'y':55,'visible':True,'sliderMin':0,'sliderMax':100,'isDiscrete':True}]
            for n in source.namelist():out.writestr(n,json.dumps(data,ensure_ascii=False) if n=='project.json' else source.read(n))
        sql(api.runtime,"INSERT INTO teachingopen_dev.sys_file (id,create_by,file_name,file_type,file_path,file_location,del_flag) VALUES ('"+fid+"','fixture_student_a','cloud sample.sb3',2,'"+relative+"',1,0)")
        sql(api.runtime,"INSERT INTO teachingopen_dev.teaching_work (id,create_by,create_time,user_id,depart_id,work_name,work_file,work_type,work_status,del_flag,work_scene) VALUES ('"+ident+"','fixture_student_a','2026-10-03 09:00:00','fixture_student_a','fixture_class_a','云变量匿名浏览实测','"+fid+"','2','3',0,'create')")
        api.cache('HSET',key,name,json.dumps('41'));print('Public fixture ready: '+ident)
    else:
        if not a.state.exists() or not target.is_file():raise RuntimeError('Expected own fixture is absent')
        if a.action in ['private','public']:sql(api.runtime,"UPDATE teachingopen_dev.teaching_work SET work_status='"+('0' if a.action=='private' else '3')+"' WHERE id='"+ident+"'")
        if a.action=='send':
            spec=importlib.util.spec_from_file_location('probe',a.backend_dev/'verify-scratch-cloud.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
            api.login('student_a');ws=m.CloudSocket(api.ports['frontend'],ident,api.tokens['student_a'])
            try:
                ws.command('handshake');ws.drain();ws.command('set',name=name,value=a.value);result=ws.drain()
                if not any(x.get('reply')=='OK' for x in result):raise RuntimeError('Write rejected')
            finally:ws.close()
        if a.action=='cleanup':
            api.cache('DEL',key);sql(api.runtime,"DELETE FROM teachingopen_dev.teaching_work WHERE id='"+ident+"'");sql(api.runtime,"DELETE FROM teachingopen_dev.sys_file WHERE id='"+fid+"'");target.unlink();target.parent.rmdir()
            before=json.loads(a.state.read_text());after=database_inventory(api.runtime);result={'non_audit_database_equal':all(before['database'][t]==after[t] for t in before['database'] if t!='sys_log'),'attachments_equal':before['files']==file_inventory(api.runtime/'uploads'),'audit_before':before['database']['sys_log']['rows'],'audit_after':after['sys_log']['rows'],'cloud_fixture_removed':api.cache('EXISTS',key)=='0'}
            private_write(a.state.with_suffix('.cleanup.json'),json.dumps(result,indent=2)+'\n');print(result);assert result['non_audit_database_equal'] and result['attachments_equal'] and result['cloud_fixture_removed']
        else:print('Cloud fixture value:',api.cache('HGET',key,name))
