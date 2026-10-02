"""Loopback-only synthetic HTTP fixture; no real API proxy, auth or persistent work data."""
import argparse, hashlib, json, time, threading
from email.parser import BytesParser
from email.policy import default
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

parser = argparse.ArgumentParser()
parser.add_argument('--port', type=int, required=True)
parser.add_argument('--directory', required=True)
args = parser.parse_args()
state = {'mode': 'normal', 'uploads': [], 'registrations': [], 'submissions': [], 'list_reads': []}
lock = threading.Lock()
rows = [
 {'additionalWorkId':'task-a','workName':'观察身边的人工智能','workDesc':'选择一个你每天会用到的智能应用，记录它帮助你解决了什么问题。\n用文字和图片整理观察过程，并说明你希望改进的一点。','codeType':0,'workDocumentUrl':'/fixtures/observation-report.txt'},
 {'additionalWorkId':'task-draft','workName':'让角色讲一个关于海洋的故事','workDesc':'围绕海洋保护创作一个互动故事。设计至少两个角色，用对话和事件推动情节。','codeType':2,'mineWorkId':'draft-a','mineWorkStatus':0,'workCover_url':'/missing-cover.png'},
 {'additionalWorkId':'task-graded','workName':'第一次实验：让小车避开障碍','workDesc':'记录实验目标、操作步骤和观察结果。','codeType':0,'mineWorkId':'graded-a','mineWorkStatus':2,'score':0,'comment':'这次提交还没有包含实验记录，因此暂记 0 分。请补充你观察到的现象，尤其是小车在接近障碍物时的变化。\n可以先画一张路线图，再说明每一步判断的依据。期待在下一次作业里看到你的思考过程。','mineWorkUrl':'/fixtures/observation-report.txt'},
 {'additionalWorkId':'task-submitted','workName':'设计一个帮助图书馆整理图书的方案','workDesc':'用流程图表达从识别书名到放回书架的步骤，考虑识别失败时如何处理。','codeType':0,'mineWorkId':'submitted-a','mineWorkStatus':1,'mineWorkName':'我的图书整理方案','mineWorkUrl':'/fixtures/second-report.txt'},
 {'additionalWorkId':'task-featured','workName':'我的天气观察日记','workDesc':'比较一周内的天气变化。','codeType':0,'mineWorkId':'featured-a','mineWorkStatus':4,'score':4,'comment':'记录完整，图表表达清晰。下一步可以试着解释温度变化的原因。','mineWorkUrl':'/fixtures/observation-report.txt'}]
for row in rows: row.update(departId='class-fixture',departName='创意编程一班',createBy_dictText='林老师')

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw): super().__init__(*a, directory=args.directory, **kw)
    def send_json(self, value, status=200):
        body = json.dumps(value, ensure_ascii=False).encode()
        self.send_response(status); self.send_header('Content-Type', 'application/json; charset=utf-8'); self.send_header('Content-Length', str(len(body))); self.end_headers()
        try: self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError): pass
    def do_GET(self):
        if urlparse(self.path).path == '/teaching/teachingWork/mineAdditionalWork':
            submit = parse_qs(urlparse(self.path).query, keep_blank_values=True).get('submit',[''])[0]
            with lock:
                mode = state['mode']; current = json.loads(json.dumps(rows)); state['list_reads'].append({'submit':submit,'mode':mode})
            if mode == 'slow-list': time.sleep(3)
            if mode == 'list-error': self.send_json({'success':False},503); return
            if mode == 'empty': current = []
            if mode == 'many': current = [{**current[0], 'additionalWorkId':'many-'+str(i),'workName':'观察练习 '+str(i+1)} for i in range(10)]
            current = [r for r in current if submit == '' or (int(r.get('mineWorkStatus') or 0) >= 1) == (submit == 'true')]
            self.send_json({'success':True,'result':current}); return
        if urlparse(self.path).path == '/__state':
            with lock: result = json.loads(json.dumps(state))
            self.send_json(result)
        else: super().do_GET()
    def do_POST(self):
        size = int(self.headers.get('Content-Length', 0))
        if size > 11 * 1024 * 1024: self.send_json({'success': False}, 413); return
        raw = self.rfile.read(size); path = urlparse(self.path).path
        with lock: mode = state['mode']
        if path == '/__mode':
            mode = json.loads(raw)['mode']
            if mode not in ['normal','upload-error','registration-error','submit-error','slow-upload','slow-submit','empty','list-error','slow-list','many']:
                self.send_json({'success':False},400); return
            with lock: state['mode'] = mode
            self.send_json({'success':True}); return
        if path == '/sys/common/upload':
            if mode == 'slow-upload': time.sleep(5)
            message = BytesParser(policy=default).parsebytes(('Content-Type: '+self.headers['Content-Type']+'\r\nMIME-Version: 1.0\r\n\r\n').encode()+raw)
            files = [part for part in message.iter_parts() if part.get_param('name',header='content-disposition') == 'file']
            if len(files) != 1: self.send_json({'success':False},400); return
            data = files[0].get_payload(decode=True)
            with lock:
                name = files[0].get_filename(); key = 'fixture/'+str(len(state['uploads'])+1)+'/'+name
                state['uploads'].append({'path':key,'name':name,'size':len(data),'sha256':hashlib.sha256(data).hexdigest(),'failed':mode=='upload-error'})
            self.send_json({'success': mode != 'upload-error','message':key}); return
        body = json.loads(raw)
        if path == '/system/sysFile/add':
            with lock:
                record = {**body, 'id':'fixture-file-'+str(len(state['registrations'])+1)}
                state['registrations'].append({**record,'failed':mode=='registration-error'})
            self.send_json({'success':mode!='registration-error','result':record}); return
        if path == '/teaching/teachingWork/submit':
            if mode == 'slow-submit': time.sleep(5)
            with lock:
                state['submissions'].append({**body,'failed':mode=='submit-error'})
                if mode != 'submit-error':
                    for row in rows:
                        if row['additionalWorkId'] == body.get('additionalId'):
                            row.update(mineWorkId='fixture-work-'+row['additionalWorkId'],mineWorkStatus=1,mineWorkName=body['workName'],mineWorkUrl='/fixtures/observation-report.txt')
            self.send_json({'success':mode!='submit-error','result':{'id':'fixture-work-'+body.get('additionalId','unknown')}}); return
        self.send_json({'success':False},404)
    def do_DELETE(self): self.send_json({'success':True})
ThreadingHTTPServer(('127.0.0.1',args.port),Handler).serve_forever()
