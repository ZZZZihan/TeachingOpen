"""Loopback-only synthetic HTTP fixture; no real API proxy, auth or persistent work data."""
import argparse, hashlib, json, time, threading
from email.parser import BytesParser
from email.policy import default
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

parser = argparse.ArgumentParser()
parser.add_argument('--port', type=int, required=True)
parser.add_argument('--directory', required=True)
args = parser.parse_args()
state = {'mode': 'normal', 'uploads': [], 'registrations': [], 'submissions': []}
lock = threading.Lock()
class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw): super().__init__(*a, directory=args.directory, **kw)
    def send_json(self, value, status=200):
        body = json.dumps(value, ensure_ascii=False).encode()
        self.send_response(status); self.send_header('Content-Type', 'application/json; charset=utf-8'); self.send_header('Content-Length', str(len(body))); self.end_headers()
        try: self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError): pass
    def do_GET(self):
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
            if mode not in ['normal','upload-error','registration-error','submit-error','slow-upload','slow-submit']:
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
            with lock: state['submissions'].append({**body,'failed':mode=='submit-error'})
            self.send_json({'success':mode!='submit-error','result':{'id':'fixture-work-'+body.get('additionalId','unknown')}}); return
        self.send_json({'success':False},404)
    def do_DELETE(self): self.send_json({'success':True})
ThreadingHTTPServer(('127.0.0.1',args.port),Handler).serve_forever()
