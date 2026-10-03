"""Loopback synthetic teacher-component preview; no authentication or production proxy."""
import argparse, json, threading, time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,required=True);parser.add_argument('--directory',required=True);args=parser.parse_args()
lock=threading.Lock();state={'mode':'normal','writes':[],'reads':[],'tags':['需要跟进','表达清晰']}
rows=[]
for index,(title,name,kind,status) in enumerate([
 ('让角色讲一个关于海洋的故事','林晓雨','2','1'),('观察身边的人工智能','陈一诺','0','1'),('用 Python 画出一棵分形树','周予安','4','1'),('我的天气观察日记','许知远','0','2'),('设计一个图书整理助手','苏雨桐','2','3'),('小车如何避开障碍','江书宁','0','0')]):
 rows.append({'id':'preview-'+str(index),'workName':title,'realname':name,'username':'student'+str(index+1),'workType':kind,'workType_dictText':{'0':'文件作品','2':'Scratch','4':'Python'}[kind],'workStatus':status,'workStatus_dictText':{'0':'草稿','1':'待批改','2':'已批改','3':'公开展示'}[status],'workScene':'course' if index%2==0 else 'additional','departId':'class-a','departId_dictText':'创意编程一班','courseId':'course-a','courseId_dictText':'探索人工智能','additionalId_dictText':'课后观察练习' if index%2 else '', 'userId':'student-'+str(index),'workFile':'fixture-file','workFileKey_url':'/report.txt','coverFileKey_url':'/missing-cover.png' if index==0 else '', 'workTag':'需要跟进' if index==1 else '', 'createTime':'2026-10-03 '+str(10-index).zfill(2)+':20:00','viewNum':2+index,'starNum':0})
feedback={rows[3]['id']:[{'id':'grade-one','score':0,'comment':'请补充实验过程的记录，尤其是你观察到的变化。'}]}
comments={r['id']:[{'id':'discussion-'+r['id'],'nickname':r['realname'],'createBy':r['username'],'comment':'老师，我在第二次尝试里调整了步骤，想请您看看。','createTime':'2026-10-03 10:30:00'}] for r in rows}
initial=json.dumps({'rows':rows,'feedback':feedback,'comments':comments,'state':state},ensure_ascii=False)
class Handler(SimpleHTTPRequestHandler):
 def __init__(self,*a,**kw):super().__init__(*a,directory=args.directory,**kw)
 def send_json(self,data,status=200):
  raw=json.dumps(data,ensure_ascii=False).encode();self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(raw)));self.end_headers()
  try:self.wfile.write(raw)
  except (BrokenPipeError,ConnectionResetError):pass
 def do_GET(self):
  parsed=urlparse(self.path);path=parsed.path;q={k:v[0] for k,v in parse_qs(parsed.query,keep_blank_values=True).items()}
  with lock:mode=state['mode'];current=json.loads(json.dumps(rows));state['reads'].append({'path':path,'query':q})
  if path=='/__state':self.send_json(state);return
  if path=='/report.txt':raw='合成作业：观察记录\n我的想法与尝试。'.encode();self.send_response(200);self.send_header('Content-Type','text/plain; charset=utf-8');self.end_headers();self.wfile.write(raw);return
  if path.startswith(('/scratch3/','/scratchjr/','/python/','/blockly/')):
   raw=b'<!doctype html><html><body><p>Isolated preview frame fixture (not an editor engine).</p></body></html>';self.send_response(200);self.send_header('Content-Type','text/html');self.end_headers();self.wfile.write(raw);return
  if path.endswith('/getWorkTags'):self.send_json({'success':True,'result':state['tags']});return
  if path.endswith('/list'):
   if mode=='list-error':self.send_json({'success':False},503);return
   if mode=='empty':current=[]
   if mode=='many':current=[{**current[0],'workStatus':'1','workStatus_dictText':'待批改','id':'many-'+str(i),'workName':'观察练习 '+str(i+1)} for i in range(23)]
   for key in ['workStatus','workScene','workType','workTag','username','departId','userId','courseId']:
    if q.get(key):current=[r for r in current if str(r.get(key,''))==q[key]]
   for key in ['workName','realname']:
    if q.get(key):current=[r for r in current if q[key] in r.get(key,'')]
   column=q.get('column','createTime');current.sort(key=lambda r:str(r.get(column,'')),reverse=q.get('order')!='asc');total=len(current);page=int(q.get('pageNo',1));size=int(q.get('pageSize',10));self.send_json({'success':True,'result':{'records':current[(page-1)*size:page*size],'total':total}});return
  if path.endswith('/queryById'):self.send_json({'success':True,'result':next((r for r in current if r['id']==q.get('id')),None)});return
  if path.endswith('/queryTeachingWorkCorrectByMainId'):
   if mode=='grade-error':self.send_json({'success':False},503)
   else:self.send_json({'success':True,'result':feedback.get(q.get('id'),[])})
   return
  if path.endswith('/queryTeachingWorkCommentByMainId'):
   if mode=='comments-error':self.send_json({'success':False},503)
   else:self.send_json({'success':True,'result':comments.get(q.get('id'),[])})
   return
  if path.endswith('/setWorkTag'):
   for r in rows:
    if r['id']==q.get('workId'):r['workTag']=q.get('workTag','')
   if q.get('workTag') and q['workTag'] not in state['tags']:state['tags'].append(q['workTag'])
   state['writes'].append({'path':path,'body':q});self.send_json({'success':True});return
  if path.endswith('/exportXls'):self.send_json({'success':False,'message':'Export is not simulated as a real workbook.'});return
  super().do_GET()
 def do_POST(self):self.mutate()
 def do_PUT(self):self.mutate()
 def mutate(self):
  body=json.loads(self.rfile.read(int(self.headers.get('Content-Length','0'))) or b'{}');path=urlparse(self.path).path
  if path=='/__reset':
   original=json.loads(initial)
   with lock:
    rows[:]=original['rows'];feedback.clear();feedback.update(original['feedback']);comments.clear();comments.update(original['comments']);state.clear();state.update(original['state'])
   self.send_json({'success':True});return
  if path=='/__mode':
   if body.get('mode') not in ['normal','empty','list-error','grade-error','comments-error','save-error','slow-save','many']:self.send_json({'success':False},400);return
   state['mode']=body['mode'];self.send_json({'success':True});return
  mode=state['mode'];state['writes'].append({'path':path,'body':body,'mode':mode})
  if path.endswith('/edit'):
   if mode=='slow-save':time.sleep(3)
   if mode=='save-error':self.send_json({'success':False},503);return
   for r in rows:
    if r['id']==body.get('id'):r.update({k:body[k] for k in ['workName','workStatus'] if k in body});r['workStatus_dictText']={'0':'草稿','1':'待批改','2':'已批改','3':'公开展示','4':'精选'}[r['workStatus']]
   if 'teachingWorkCorrectList' in body:feedback[body['id']]=body['teachingWorkCorrectList']
   self.send_json({'success':True});return
  if path.endswith('/sendWork'):self.send_json({'success':True});return
  self.send_json({'success':False},404)
 def do_DELETE(self):
  q={k:v[0] for k,v in parse_qs(urlparse(self.path).query).items()};state['writes'].append({'path':urlparse(self.path).path,'body':q})
  if self.path.startswith('/teaching/teachingWork/delWorkTag'):state['tags'][:]=[t for t in state['tags'] if t!=q.get('tag')]
  else:rows[:]=[r for r in rows if r['id'] not in q.get('ids',q.get('id','')).split(',')]
  self.send_json({'success':True})
ThreadingHTTPServer(('127.0.0.1',args.port),Handler).serve_forever()
