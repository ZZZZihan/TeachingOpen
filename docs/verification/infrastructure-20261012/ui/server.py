#!/usr/bin/env python3
"""Loopback-only synthetic API recorder and static bundle server; never proxies."""
import argparse, json
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

parser=argparse.ArgumentParser()
parser.add_argument('--directory',required=True)
parser.add_argument('--port',type=int,required=True)
parser.add_argument('--requests',required=True)
args=parser.parse_args()
requests=[]
out=Path(args.requests)

class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*a,**kw): super().__init__(*a,directory=args.directory,**kw)
    def payload(self,value):
        body=json.dumps(value,ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Content-Length',str(len(body)))
        self.send_header('Cache-Control','no-store')
        self.end_headers();self.wfile.write(body)
    def do_GET(self):
        if self.path=='/__state': return self.payload(requests)
        return super().do_GET()
    def do_POST(self): self.record()
    def do_PUT(self): self.record()
    def record(self):
        body=self.rfile.read(int(self.headers.get('Content-Length','0')))
        if self.path=='/__reset':
            requests.clear();out.write_text('[]');return self.payload({'success':True})
        allowed={'/sys/dataSource/add','/sys/dataSource/edit','/sys/quartzJob/add','/sys/quartzJob/edit','/online/cgreport/api/testConnection'}
        if self.path not in allowed: return self.send_error(404)
        requests.append({'method':self.command,'path':self.path,'body':json.loads(body or '{}')})
        out.write_text(json.dumps(requests,ensure_ascii=False,indent=2))
        self.payload({'success':True,'message':'合成记录已保存'})

server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
print(json.dumps({'origin':'http://127.0.0.1:'+str(args.port),'directory':args.directory}),flush=True)
server.serve_forever()
