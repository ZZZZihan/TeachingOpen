#!/usr/bin/env python3
"""Separate real local API/DB checks; not a browser login or end-to-end acceptance."""
import argparse,json,sys
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--support-repo',type=Path,required=True);p.add_argument('--runtime',type=Path,required=True);p.add_argument('--jar',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
if a.output.exists():raise RuntimeError('Evidence output already exists')
sys.path.insert(0,str(a.support_repo/'api/dev'))
from local_http import FixtureApi
from local_recovery import database_inventory,file_inventory,sql,private_write
cases=[];observations=[];prefix='fixture_form_'
def check(name,ok):
 cases.append({'case':name,'passed':bool(ok)});print(('PASS ' if ok else 'FAIL ')+name,flush=True)
 if not ok:raise AssertionError(name)
with FixtureApi(a.runtime,a.jar) as api:
 before=database_inventory(api.runtime);files=file_inventory(api.runtime/'uploads')
 def query(s):return sql(api.runtime,'USE teachingopen_dev; '+s)
 for t in ['teaching_course','teaching_course_unit']:
  if query("SELECT COUNT(*) FROM "+t+" WHERE id LIKE '"+prefix+"%'")!='0':raise RuntimeError('Preserve existing probe data')
 try:
  for actor in ['admin','teacher_a','student_a']:api.login(actor)
  for kind,table,ctrl,field in [('course','teaching_course','teachingCourse','courseName'),('unit','teaching_course_unit','teachingCourseUnit','unitName')]:
   rid=prefix+kind
   base={'id':rid,field:'合成课程表单','orderNum':0}
   fields={'courseDesc':'<p>保留课程介绍</p>','isShared':False,'showHome':False,'showType':2} if kind=='course' else {'courseId':prefix+'course','unitIntro':'保留单元简介','courseVideoSource':2,'courseVideo':'https://example.invalid/lesson.mp4','showCourseVideo':False,'showCourseCase':True,'showCoursePpt':False,'showCoursePlan':False,'courseWorkType':'2','mediaContent':'<p>保留课程内容</p>'}
   body={**base,**fields};endpoint='/teaching/'+ctrl+'/'
   code,res,_=api.request('POST',endpoint+'add','admin',body);check(kind+' admin creation accepted',code==200 and res and res.get('success') is True)
   code,res,_=api.request('GET',endpoint+'queryById?id='+rid,'admin');check(kind+' created fields persist including false and zero',res and res.get('success') and all(res['result'].get(k)==(int(v) if k=='courseWorkType' else v) for k,v in body.items()))
   body[field]='修改后的合成记录'
   code,res,_=api.request('PUT',endpoint+'edit','admin',body);check(kind+' edit accepted',code==200 and res and res.get('success') is True)
   code,res,_=api.request('GET',endpoint+'queryById?id='+rid,'admin');check(kind+' edited content can reopen',res and res.get('success') and all(res['result'].get(k)==(int(v) if k=='courseWorkType' else v) for k,v in body.items()))
   snapshot=query("SELECT * FROM "+table+" WHERE id='"+rid+"'")
   for actor in ['teacher_a','student_a',None]:
    code,res,_=api.request('PUT',endpoint+'edit',actor,{**body,field:'拒绝修改'})
    check(kind+' edit denied '+str(actor),bool(res) and res.get('success') is False and code==(200 if actor else 401))
    check(kind+' denied edit preserves row '+str(actor),snapshot==query("SELECT * FROM "+table+" WHERE id='"+rid+"'"))
   # Observe a distinct pre-existing API issue, without treating it as this UI fix passing.
   code,res,_=api.request('PUT',endpoint+'edit','admin',{**body,'id':rid+'_missing'})
   observations.append({'case':kind+' edit of nonexistent ID','http':code,'success':res.get('success') if res else None,'row_count':query("SELECT COUNT(*) FROM "+table+" WHERE id='"+rid+"_missing'")})
  for kind,table,ctrl in [('unit','teaching_course_unit','teachingCourseUnit'),('course','teaching_course','teachingCourse')]:
   code,res,_=api.request('DELETE','/teaching/'+ctrl+'/delete?id='+prefix+kind,'admin');check(kind+' normal deletion works',code==200 and res and res.get('success') is True and query("SELECT COUNT(*) FROM "+table+" WHERE id='"+prefix+kind+"'")=='0')
 finally:
  for table in ['teaching_course_unit','teaching_course']:query("DELETE FROM "+table+" WHERE id LIKE '"+prefix+"%'")
  after=database_inventory(api.runtime);check('68 non-audit tables restored',all(before[t]==after[t] for t in before if t!='sys_log'));check('attachments unchanged',files==file_inventory(api.runtime/'uploads'))
 result={'cases':cases,'passed':sum(c['passed'] for c in cases),'total':len(cases),'observations_not_fixed':observations,'jar_sha256':api.jar_sha256,'scope':'Real isolated HTTP and MySQL with synthetic CLI authentication; separate from component browser checks.'}
private_write(a.output,json.dumps(result,ensure_ascii=False,indent=2)+'\n')
