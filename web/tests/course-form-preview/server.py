#!/usr/bin/env python3
"""Loopback-only synthetic component API. Never proxies a real login or database."""
import argparse,json,time
from functools import partial
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
p=argparse.ArgumentParser();p.add_argument('--directory',required=True);p.add_argument('--port',type=int,required=True);args=p.parse_args()
state={'mode':'normal','writes':[]}
class Handler(SimpleHTTPRequestHandler):
 def reply(self,status,body):
  data=json.dumps(body).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
 def do_GET(self):
  if self.path=='/__state':return self.reply(200,state)
  if self.path.startswith('/teaching/teachingCourse/list'):return self.reply(200,{'success':True,'result':{'records':[{'id':'course-fixture','courseName':'合成课程'}]}})
  return super().do_GET()
 def do_POST(self):
  body=json.loads(self.rfile.read(int(self.headers.get('Content-Length',0))) or '{}')
  if self.path=='/__mode':
   state['mode']=body['mode'];return self.reply(200,{'success':True})
  if self.path=='/__reset':state['writes']=[];return self.reply(200,{'success':True})
  if self.path in ['/teaching/teachingCourse/edit','/teaching/teachingCourse/add','/teaching/teachingCourseUnit/edit','/teaching/teachingCourseUnit/add']:
   state['writes'].append({'path':self.path,'body':body});mode=state['mode']
   if mode=='slow':time.sleep(2)
   if mode=='network-error':return self.reply(503,{'success':False})
   return self.reply(200,{'success':mode!='business-error','message':'合成结果'})
  return self.reply(404,{'success':False})
 do_PUT=do_POST
ThreadingHTTPServer(('127.0.0.1',args.port),partial(Handler,directory=args.directory)).serve_forever()
