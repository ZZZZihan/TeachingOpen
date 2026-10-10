"""Loopback-only Scratch editor HTTP fixture. No real API, user session or database.
Run: python3 web/tests/scratch-preview/server.py --port 18121 --directory web/public
"""
import argparse, hashlib, json, threading, time, io, zipfile
from pathlib import Path
from email.parser import BytesParser
from email.policy import default
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

parser = argparse.ArgumentParser()
parser.add_argument('--port', type=int, required=True)
parser.add_argument('--directory', required=True)
args = parser.parse_args()
lock = threading.Lock()
seed = Path(__file__).with_name('sample.sb3').read_bytes()
state = {'mode': 'normal', 'reads': [], 'uploads': [], 'registrations': [], 'submissions': [], 'works': {
    'seed-work': {'id': 'seed-work', 'workName': '我的 Scratch 练习 & 100%', 'workType': '2', 'workFileKey_url': '/fixtures/sample.sb3?revision=1&label=a+b', 'additionalId': 'task-scratch', 'departId': 'class-fixture'}}}
files = {'/fixtures/sample.sb3': seed}

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw): super().__init__(*a, directory=args.directory, **kw)
    def end_headers(self):
        self.send_header('Content-Security-Policy', "script-src 'self' 'unsafe-inline' 'unsafe-eval' blob:; connect-src 'self' blob: data:; img-src 'self' data: blob:;")
        super().end_headers()
    def respond(self, data, status=200, mime='application/json; charset=utf-8'):
        body = json.dumps(data, ensure_ascii=False).encode() if not isinstance(data, bytes) else data
        self.send_response(status); self.send_header('Content-Type', mime); self.send_header('Content-Length', str(len(body))); self.send_header('Cache-Control', 'no-store'); self.end_headers()
        try: self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError): pass
    def do_GET(self):
        path = urlparse(self.path).path
        with lock: mode = state['mode']
        if path == '/api/teaching/teachingCourseUnit/getUnitWorkInfo':
            self.respond({'success': True, 'result': {'unitName': '课程 Scratch 练习', 'courseWork_url': '/fixtures/sample.sb3'}}); return
        if path == '/__state':
            with lock: data = json.loads(json.dumps(state))
            self.respond(data); return
        if path == '/api/sys/config/getCurrentConfig':
            self.respond({'code': 0, 'success': True, 'result': {'uploadType': 'local', 'staticDomain': '', 'logo': '/logo.png'}}); return
        if path == '/api/teaching/teachingWork/studentWorkInfo':
            wid = parse_qs(urlparse(self.path).query).get('workId', [''])[0]
            with lock: state['reads'].append({'workId': wid, 'mode': mode}); work = state['works'].get(wid)
            if mode == 'slow-load': time.sleep(4)
            if mode == 'load-error': self.respond({'success': False}, 503); return
            self.respond({'code': 0, 'success': bool(work), 'result': work}); return
        with lock: data = files.get(path)
        if data is not None:
            if mode == 'file-error': self.respond({'success': False}, 503); return
            self.respond(data, mime='application/octet-stream'); return
        super().do_GET()
    def do_POST(self):
        size = int(self.headers.get('Content-Length', 0))
        if size > 11 * 1024 * 1024: self.respond({'success': False}, 413); return
        raw = self.rfile.read(size); path = urlparse(self.path).path
        with lock: mode = state['mode']
        if path == '/__mode':
            next_mode = json.loads(raw)['mode']
            if next_mode not in ['normal', 'load-error', 'file-error', 'slow-load', 'upload-error', 'registration-error', 'submit-error', 'slow-submit', 'unauthorized', 'cover-error', 'project-error', 'slow-cover', 'slow-project']:
                self.respond({'success': False}, 400); return
            with lock: state['mode'] = next_mode
            self.respond({'success': True}); return
        if mode == 'unauthorized': self.respond({'success': False}, 401); return
        if path == '/api/sys/common/upload':
            message = BytesParser(policy=default).parsebytes(('Content-Type: '+self.headers['Content-Type']+'\r\nMIME-Version: 1.0\r\n\r\n').encode()+raw)
            parts = [p for p in message.iter_parts() if p.get_param('name', header='content-disposition') == 'file']
            if len(parts) != 1: self.respond({'success': False}, 400); return
            data = parts[0].get_payload(decode=True)
            name = parts[0].get_filename()
            cover = name.endswith(('.jpg', '.png'))
            failed = mode == 'upload-error' or mode == ('cover-error' if cover else 'project-error')
            if mode == ('slow-cover' if cover else 'slow-project'): time.sleep(4)
            detail = {}
            if name.endswith('.sb3'):
                with zipfile.ZipFile(io.BytesIO(data)) as archive:
                    detail['targets'] = [{k:t.get(k) for k in ['name','isStage','x','y']} for t in json.loads(archive.read('project.json'))['targets']]
            else: detail['header_hex'] = data[:8].hex()
            with lock:
                key = 'fixture/'+str(len(state['uploads'])+1)+Path(name).suffix
                state['uploads'].append({'path': key, 'name': parts[0].get_filename(), 'sha256': hashlib.sha256(data).hexdigest(), 'failed': failed, **detail})
                if not failed: files['/'+key] = data
            self.respond({'success': not failed, 'message': key}); return
        body = json.loads(raw)
        if path == '/api/system/sysFile/add':
            with lock:
                record = {**body, 'id': 'file-'+str(len(state['registrations'])+1)}
                state['registrations'].append({**record, 'failed': mode == 'registration-error'})
            self.respond({'success': mode != 'registration-error', 'result': record}); return
        if path == '/api/teaching/teachingWork/submit':
            if mode == 'slow-submit': time.sleep(4)
            with lock:
                state['submissions'].append({**body, 'failed': mode == 'submit-error'})
                wid = body.get('id') or 'saved-'+str(len(state['works'])+1)
                registered = next((r for r in state['registrations'] if r['id'] == body.get('workFile')), None)
                if mode != 'submit-error' and registered:
                    state['works'][wid] = {**body, 'id': wid, 'workFileKey_url': '/'+registered['filePath']}
            self.respond({'code': 200 if mode != 'submit-error' else 500, 'success': mode != 'submit-error', 'result': {'id': wid}}); return
        self.respond({'success': False}, 404)

ThreadingHTTPServer(('127.0.0.1', args.port), Handler).serve_forever()
