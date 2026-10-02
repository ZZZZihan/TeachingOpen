from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
import json, urllib.parse, argparse, tempfile, re
parser = argparse.ArgumentParser(description='Local synthetic TeachingOpen browser fixture; no real backend.')
parser.add_argument('--state', type=Path, required=True)
parser.add_argument('--port', type=int, default=18080)
args = parser.parse_args()
dist = Path(__file__).resolve().parents[1] / 'dist'
state = args.state
if not state.exists(): state.write_text('{}')
log = Path(tempfile.gettempdir()) / 'teachingopen-fixture-requests.jsonl'
class Handler(SimpleHTTPRequestHandler):
 def __init__(self,*args,**kw): super().__init__(*args,directory=str(dist),**kw)
 def log_message(self,*args): pass
 def do_GET(self):
  path=urllib.parse.urlparse(self.path).path
  if path.startswith('/api/'):
   settings=json.loads(state.read_text())
   code=200
   if path.endswith('/getCurrentConfig'):
    code=503 if settings.get('configFail') else 200
    value={'brandName':'TeachingOpen 本地验证','uploadType':'local','staticDomain':'/api/sys/common/static','footer':'本地合成接口验证'}
   elif path.endswith('/getUserMenu'):
    code=503 if settings.get('menuFail') else 200
    value=[{'id':'course','title':'课程','url':'/courseList','route':True,'needLogin':0}]
   elif path.endswith('/getHomeCourse'):
    code=503 if settings.get('courseFail') else 200
    query=urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
    category=query.get('courseCategory',[''])[0]
    value={'records':[{'id':'fixture-'+(category or 'all'),'courseName':('初中课程' if category=='2' else '人工智能入门'),'courseCover_url':'/logo.png','courseDesc':'<p>本地合成课程说明</p>'}],'total':1}
   elif '/getDictItems/' in path:
    value=[{'text':'小学','value':'1'},{'text':'初中','value':'2'}] if path.endswith('course_category') else [{'text':'必修','value':'1'}]
   else: value=[]
   with log.open('a') as f: f.write(json.dumps({'path':self.path,'status':code},ensure_ascii=False)+'\n')
   data=json.dumps({'success':code==200,'code':code,'result':value if code==200 else None,'message':'fixture'},ensure_ascii=False).encode()
   self.send_response(code); self.send_header('Content-Type','application/json'); self.send_header('Content-Length',str(len(data))); self.end_headers(); self.wfile.write(data); return
  if path in ['/', '/index','/courseList','/user/login']:
   html=(dist/'index.html').read_text()
   html=re.sub(r'<script\b[^>]*//api\.paas\.plus/js/errlog\.js[^>]*>\s*</script>', '', html)
   data=html.encode()
   self.send_response(200); self.send_header('Content-Type','text/html'); self.send_header('Content-Length',str(len(data))); self.end_headers(); self.wfile.write(data); return
  super().do_GET()
print(f'Local synthetic fixture at http://127.0.0.1:{args.port}',flush=True)
ThreadingHTTPServer(('127.0.0.1',args.port),Handler).serve_forever()
