"""Loopback-only synthetic HTTP for the real recovery SFCs; never proxies an API.
All account/phone inputs are fixtures. Password and SMS code are omitted from logs.
"""
import argparse, base64, json, time
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlsplit
from threading import Lock

parser=argparse.ArgumentParser()
parser.add_argument('--directory',type=Path,required=True)
parser.add_argument('--port',type=int,required=True)
args=parser.parse_args()
state={'mode':'success','sms_attempts':0,'requests':[]}
lock=Lock()
image='data:image/svg+xml;base64,'+base64.b64encode(b'<svg xmlns="http://www.w3.org/2000/svg" width="126" height="44"><rect width="126" height="44" fill="#f2eef2"/><text x="14" y="28" fill="#74256a" font-size="14">SYNTHETIC</text></svg>').decode()
class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def reply(self,data,status=200,mime='application/json; charset=utf-8'):
        raw=data if isinstance(data,bytes) else json.dumps(data,ensure_ascii=False).encode()
        self.send_response(status); self.send_header('Content-Type',mime); self.send_header('Cache-Control','no-store'); self.send_header('Content-Length',str(len(raw))); self.end_headers(); self.wfile.write(raw)
    def do_GET(self):
        path=urlsplit(self.path).path
        if path=='/__state':
            with lock: data=json.loads(json.dumps(state))
            return self.reply(data)
        if path.startswith('/__recovery/'):
            return self.api(path.removeprefix('/__recovery'),{})
        local=(args.directory/path.lstrip('/')).resolve()
        if not local.is_relative_to(args.directory.resolve()): return self.reply({'success':False},404)
        if not local.is_file(): local=args.directory/'index.html'
        mime='text/javascript; charset=utf-8' if local.suffix=='.js' else 'image/png' if local.suffix=='.png' else 'text/html; charset=utf-8'
        return self.reply(local.read_bytes(),mime=mime)
    def do_POST(self):
        try: body=json.loads(self.rfile.read(int(self.headers.get('Content-Length','0'))))
        except Exception: return self.reply({'success':False},400)
        path=urlsplit(self.path).path
        if path=='/__mode':
            if body.get('mode') not in ['success','sms-once-fail','sms-active','verify-fail','reset-unknown','reset-committed','http-fail','slow','captcha-fail','captcha-reject']: return self.reply({'success':False},400)
            with lock: state.update(mode=body['mode'],sms_attempts=0,requests=[])
            return self.reply({'success':True})
        if path.startswith('/__recovery/'): return self.api(path.removeprefix('/__recovery'),body)
        self.reply({'success':False},404)
    def api(self,path,body):
        with lock:
            mode=state['mode']; state['requests'].append({'method':self.command,'path':path,'body':{key:'[redacted]' if key in ['password','smscode','captcha'] else value for key,value in body.items()}})
            if path=='/sys/sms': state['sms_attempts']+=1
            attempt=state['sms_attempts']
        if mode=='slow': time.sleep(5)
        if mode=='http-fail': return self.reply({'success':False},503)
        if path.startswith('/sys/randomImage/'):
            return self.reply({'success':mode!='captcha-fail','result':image if mode!='captcha-fail' else None})
        if path=='/sys/checkCaptcha': return self.reply({'success':mode!='captcha-reject'})
        if path=='/sys/user/querySysUser': return self.reply({'success':True,'result':{'username':'demo-student','phone':'138****0000'}})
        if path not in ['/sys/sms','/sys/user/phoneVerification','/sys/user/passwordChange'] or self.command!='POST': return self.reply({'success':False},404)
        if body.get('username')!='demo-student' or body.get('mobile',body.get('phone'))!='13800000000': return self.reply({'success':False,'code':400})
        if path=='/sys/sms':
            if mode=='sms-once-fail' and attempt==1: return self.reply({'success':False,'code':400})
            if mode=='sms-active': return self.reply({'success':False,'code':400,'recoveryState':'code_active'})
            return self.reply({'success':True,'result':None})
        if path=='/sys/user/phoneVerification': return self.reply({'success':mode!='verify-fail','result':None})
        if mode in ['reset-unknown','reset-committed']: return self.reply({'success':False,'code':500,'recoveryState':mode.replace('-','_')})
        return self.reply({'success':True,'result':None})
print(f'Synthetic recovery SFC preview: http://127.0.0.1:{args.port}/user/alteration',flush=True)
ThreadingHTTPServer(('127.0.0.1',args.port),Handler).serve_forever()
