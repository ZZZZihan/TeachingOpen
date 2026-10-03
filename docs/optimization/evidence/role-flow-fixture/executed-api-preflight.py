from pathlib import Path
import json,sys,http.client,hashlib
root=Path('/Users/xuzihan/Documents/Projects/TeachingOpen')
repo=root/'.devspace/worktrees/role-flow-fixture'
sys.path.insert(0,str(repo/'api/dev'))
from local_http import FixtureApi
from local_recovery import database_inventory,file_inventory,private_write
from role_flow_fixture import ROUTES
runtime=root/'.devspace/role-flow-1003'
jar=root/'.devspace/worktrees/course-update-outcome/api/jeecg-boot-module-system/target/teaching-open-2.8.0.jar'
cases=[]
def check(name,ok):
 cases.append({'case':name,'passed':bool(ok)})
 print(('PASS ' if ok else 'FAIL ')+name,flush=True)
 if not ok: raise AssertionError(name)
def walk(items):
 for item in items:
  yield item
  yield from walk(item.get('children',[]))
def request_ok(api,path,actor):
 status,data,_=api.request('GET',path,actor)
 assert status==200 and data and data.get('success') is True
 return data['result']
def raw(api,path,actor,byte_range=None):
 conn=http.client.HTTPConnection('127.0.0.1',api.ports['backend'],timeout=15)
 headers={'X-Access-Token':api.tokens[actor]}
 if byte_range:headers['Range']=byte_range
 try:
  conn.request('GET','/api/sys/common/static/'+path,headers=headers)
  response=conn.getresponse();data=response.read()
  return response.status,data,response.getheader('Content-Range')
 finally:conn.close()
phase='initial';error=None
try:
 before=database_inventory(runtime);files=file_inventory(runtime/'uploads')
 stable={k:v for k,v in before.items() if k.startswith('teaching_') or k in {'sys_permission','sys_role_permission','sys_depart','sys_fill_rule','sys_dict','sys_dict_item','sys_file'}}
 with FixtureApi(runtime,jar) as api:
  phase='menus'
  for actor,role in [('admin','admin'),('teacher_a','teacher'),('teacher_b','teacher'),('student_a','student'),('student_b','student')]:
   api.login(actor)
   menu=request_ok(api,'/sys/permission/getUserPermissionByToken',actor)
   expected={url:component for _,_,url,component,roles,_ in ROUTES if role in roles}
   actual={row.get('path'):row.get('component') for row in walk(menu['menu'])}
   check(actor+' receives exact registered role routes',actual==expected)
   granted={row.get('action') for row in menu['auth']}
   check(actor+' button permissions stay within role',granted==({'user:edit','user:status'} if role=='admin' else set()))
  phase='course-scope'
  a=request_ok(api,'/teaching/teachingCourse/mineCourse','student_a')
  b=request_ok(api,'/teaching/teachingCourse/mineCourse','student_b')
  check('student A assigned course set', {row['id'] for row in a}=={'fixture_course_a','fixture_ui_course'})
  check('student B excludes class A course', {row['id'] for row in b}=={'fixture_course_b'})
  units=request_ok(api,'/teaching/teachingCourseUnit/mineUnit?courseId=fixture_ui_course&pageSize=50','student_a')['records']
  check('three real editor unit types and hidden teacher plan',len(units)==3 and {row['courseWorkType'] for row in units}=={2,3,4} and all(not row.get('coursePlan') for row in units))
  status,result,_=api.request('GET','/teaching/teachingCourseUnit/mineUnit?courseId=fixture_ui_course','student_b')
  check('cross class unit read rejected',status==200 and result and result.get('success') is False and result.get('code')==510)
  phase='media'
  for name in ('lesson.mp4','starter.sb3','starter.sjr','starter.py','learning-notes.txt'):
   status,data,_=raw(api,'role-flow/'+name,'student_a')
   check('authorized resource byte match '+name,status==200 and data==(runtime/'uploads/role-flow'/name).read_bytes())
  status,data,content_range=raw(api,'role-flow/lesson.mp4','student_a','bytes=0-63')
  check('authorized video range bytes',status==206 and data==(runtime/'uploads/role-flow/lesson.mp4').read_bytes()[:64] and content_range.startswith('bytes 0-63/'))
  status,_,_=raw(api,'role-flow/lesson.mp4','student_b')
  check('cross class media read rejected',status==403)
  phase='data-after'
  after=database_inventory(runtime)
  check('read preflight preserves teaching configuration and assets',all(after[k]==v for k,v in stable.items()) and file_inventory(runtime/'uploads')==files)
 phase='complete'
except Exception as e:
 error=type(e).__name__
report={'scope':'Synthetic actual API login/menu/unit/protected resource preflight; no browser login or editor/media playback acceptance','phase':phase,'completed':phase=='complete','error_type':error,'passed':sum(x['passed'] for x in cases),'total':len(cases),'cases':cases,'jar_sha256':hashlib.sha256(jar.read_bytes()).hexdigest()}
private_write(runtime/'api-preflight.json',json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k!='cases'}))
raise SystemExit(0 if phase=='complete' else 1)
