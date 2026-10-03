#!/usr/bin/env python3
"""Teacher UI request contract on isolated synthetic Java/MySQL; not browser authentication."""
import argparse, hashlib, json, sys
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--support-repo',type=Path,required=True);p.add_argument('--runtime',type=Path,required=True);p.add_argument('--jar',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
sys.path.insert(0,str(a.support_repo/'api/dev'))
from local_http import FixtureApi
from local_recovery import database_inventory,file_inventory,sql,private_write
cases=[]
def check(name,value):
 cases.append({'case':name,'passed':bool(value)});print(('PASS ' if value else 'FAIL ')+name,flush=True)
 if not value:raise AssertionError(name)
prefix='fixture_teacher_ui_';ids=[prefix+str(i) for i in range(3)]
with FixtureApi(a.runtime,a.jar) as api:
 before=database_inventory(api.runtime);files=file_inventory(api.runtime/'uploads')
 def query(text):return sql(api.runtime,'USE teachingopen_dev; '+text)
 for table in ('teaching_work','teaching_work_correct','teaching_work_comment'):
  if query("SELECT COUNT(*) FROM "+table+" WHERE id LIKE '"+prefix+"%'")!='0':raise RuntimeError('Existing same-prefix probe must be preserved')
 def req(method,endpoint,actor='teacher_a',body=None):return api.request(method,'/teaching/teachingWork/'+endpoint,actor,body)
 def listq(extra=''):
  code,result,_=req('GET','list?workName='+prefix+'&pageNo=1&pageSize=10&column=createTime&order=desc'+extra)
  check('list accepted '+extra,code==200 and result and result.get('success') and isinstance(result.get('result',{}).get('records'),list))
  return result['result']
 try:
  for actor in ('teacher_a','teacher_b','student_a','admin'):api.login(actor)
  for index,work in enumerate(ids):
   student='fixture_student_b' if index==2 else 'fixture_student_a';depart='fixture_class_b' if index==2 else 'fixture_class_a';status='2' if index==1 else '1';file='fixture_file_b' if index==2 else 'fixture_file_a'
   query("INSERT INTO teaching_work (id,user_id,depart_id,work_name,work_file,work_type,work_status,work_scene,del_flag,create_by,create_time) VALUES ('"+work+"','"+student+"','"+depart+"','"+prefix+str(index)+"','"+file+"','0','"+status+"','create',0,'"+student+"','2026-10-01 10:0"+str(index)+":00')")
  result=listq('&workStatus=1');check('pending filter returns only own-class pending row',result['total']==1 and result['records'][0]['id']==ids[0])
  row=result['records'][0];check('list provides fields consumed by grading and preview',all(row.get(k) for k in ('id','workName','workType','workStatus','realname','username','workFileKey_url')))
  result=listq('&workStatus=2');check('graded filter returns own-class graded row',result['total']==1 and result['records'][0]['id']==ids[1])
  result=listq();check('all states retains class scope and descending order',[r['id'] for r in result['records']]==[ids[1],ids[0]])
  result=listq('&departId=fixture_class_b');check('cross-class explicit filter cannot widen scope',result['total']==0)
  result=listq('&workScene=additional');check('scene filter applies',result['total']==0)
  result=listq('&workType=4');check('type filter applies',result['total']==0)
  code,res,_=req('GET','queryById?id='+ids[0]);check('fresh work read for grading',code==200 and res.get('success') and res['result']['id']==ids[0])
  code,res,_=req('GET','queryTeachingWorkCorrectByMainId?id='+ids[0]);check('initial feedback is genuinely empty',code==200 and res.get('success') and res['result']==[])
  code,res,_=req('POST','saveComment','student_a',{'workId':ids[0],'comment':'discussion after teacher read'});check('student discussion accepted',code==200 and res.get('success'))
  comments=query("SELECT * FROM teaching_work_comment WHERE work_id='"+ids[0]+"' ORDER BY id")
  body={'id':ids[0],'workName':prefix+'renamed','workStatus':'2','teachingWorkCorrectList':[{'score':0,'comment':''}]}
  code,res,_=req('PUT','edit','teacher_a',body);check('minimal grading payload accepted with zero',code==200 and res.get('success'))
  code,res,_=req('GET','queryTeachingWorkCorrectByMainId?id='+ids[0],'student_a');check('student reads saved zero',code==200 and res.get('success') and len(res['result'])==1 and res['result'][0]['score']==0)
  check('discussion rows preserved',query("SELECT * FROM teaching_work_comment WHERE work_id='"+ids[0]+"' ORDER BY id")==comments)
  check('minimal save preserves owner, file and class',query("SELECT CONCAT(user_id,':',depart_id,':',work_file) FROM teaching_work WHERE id='"+ids[0]+"'")=='fixture_student_a:fixture_class_a:fixture_file_a')
  result=listq('&workStatus=1');check('graded row leaves pending queue',result['total']==0)
  score=query("SELECT * FROM teaching_work_correct WHERE work_id='"+ids[0]+"' ORDER BY id")
  code,res,_=req('PUT','edit','teacher_a',{'id':ids[0],'workName':prefix+'metadata','workStatus':'2'});check('unchanged feedback omitted from metadata save',code==200 and res.get('success') and query("SELECT * FROM teaching_work_correct WHERE work_id='"+ids[0]+"' ORDER BY id")==score)
  snapshot=query("SELECT * FROM teaching_work WHERE id='"+ids[0]+"'")
  for actor in ('student_a','teacher_b',None):
   code,res,_=req('PUT','edit',actor,body);check('grading denied '+str(actor),bool(res) and not res.get('success'))
   check('denied save preserves work and feedback '+str(actor),query("SELECT * FROM teaching_work WHERE id='"+ids[0]+"'")==snapshot and query("SELECT * FROM teaching_work_correct WHERE work_id='"+ids[0]+"' ORDER BY id")==score)
 finally:
  for work in ids:query("DELETE FROM teaching_work_correct WHERE work_id='"+work+"'; DELETE FROM teaching_work_comment WHERE work_id='"+work+"'; DELETE FROM teaching_work WHERE id='"+work+"'")
 after=database_inventory(api.runtime);check('all 68 non-audit tables restored',all(before[t]==after[t] for t in before if t!='sys_log'));check('attachment bytes unchanged',files==file_inventory(api.runtime/'uploads'))
 result={'cases':cases,'passed':sum(x['passed'] for x in cases),'total':len(cases),'jar_sha256':api.jar_sha256,'scope':'Actual synthetic CLI authentication, teacher UI endpoint/parameter/payload contract, MySQL readback; not authenticated browser or editor engine acceptance.'}
private_write(a.output,json.dumps(result,indent=2)+'\n')
