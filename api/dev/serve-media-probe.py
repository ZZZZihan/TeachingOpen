#!/usr/bin/env python3
"""Controlled browser media fixture; binds loopback, relays real backend cookies, cleans up on exit.
This is media compatibility evidence, not the product login or editor workflow.
"""
import argparse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import json
import signal
import subprocess
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from local_http import FixtureApi
from local_runtime import mysql_command

PREFIX='fixture_browser_media_'
FOLDER='browser-media-probe'
PAGE='''<!doctype html><html lang="zh"><meta charset="utf-8"><title>TeachingOpen 媒体访问验证</title>
<style>body{font:16px system-ui;margin:40px;color:#163331}nav{display:flex;gap:24px;margin:24px 0}img,video{width:240px;height:140px;object-fit:contain;border:1px solid #ccc}pre{line-height:1.7}</style>
<h1>TeachingOpen 媒体访问验证</h1><p>隔离合成数据 · 验证图片、视频与文件请求 · 不代表产品页面验收</p>
<nav><a href="/owner">作者凭据</a><a href="/foreign">其他学生凭据</a><a href="/logout">退出作者会话</a></nav><h2>STATE</h2>
<img id="picture" alt="受保护图片" src="/api/sys/common/static/browser-media-probe/probe.png">
<video id="movie" controls muted preload="auto" src="/api/sys/common/static/browser-media-probe/probe.mp4"></video>
<button id="play">播放视频</button><pre id="results">加载中</pre>
<script>
const results={};const out=document.querySelector('#results');const render=()=>out.textContent=JSON.stringify(results,null,2);
const picture=document.querySelector('#picture'),movie=document.querySelector('#movie');
picture.onload=()=>{results.image=picture.naturalWidth+' × '+picture.naturalHeight;render()};picture.onerror=()=>{results.image='denied';render()};
movie.onloadedmetadata=()=>{results.video={duration:movie.duration,width:movie.videoWidth,height:movie.videoHeight};render()};movie.onerror=()=>{results.video='denied';render()};
movie.ontimeupdate=()=>{if(movie.currentTime>0.2){results.playback='advanced';render()}};
document.querySelector('#play').onclick=()=>movie.play().catch(()=>{results.playback='denied';render()});
(async()=>{for(const [name,method,headers] of [['range','GET',{'Range':'bytes=0-4'}],['head','HEAD',{}],['raw','GET',{}]]){
const r=await fetch('/api/sys/common/static/browser-media-probe/probe.txt',{method,headers,cache:'no-store'});results[name]={status:r.status,bytes:(await r.arrayBuffer()).byteLength};render();}})();
</script></html>'''

def main(args):
    runtime=args.runtime.resolve()
    report=[]
    with FixtureApi(runtime,args.jar) as api:
        folder=runtime/'uploads'/FOLDER
        def sql(query): return subprocess.check_output(mysql_command(runtime)+['teachingopen_dev','-e',query],text=True).strip()
        if folder.exists() or sql("SELECT COUNT(*) FROM sys_file WHERE id LIKE '"+PREFIX+"%'")!='0': raise RuntimeError('Existing media fixture')
        folder.mkdir()
        try:
            subprocess.run(['ffmpeg','-nostdin','-loglevel','error','-f','lavfi','-i','color=c=0x2b665e:s=320x180:d=3','-c:v','libx264','-pix_fmt','yuv420p','-movflags','+faststart',str(folder/'probe.mp4')],check=True)
            subprocess.run(['ffmpeg','-nostdin','-loglevel','error','-f','lavfi','-i','color=c=0xb74535:s=320x180','-frames:v','1',str(folder/'probe.png')],check=True)
            (folder/'probe.txt').write_text('SYNTHETIC-MEDIA-CONTENT')
            for suffix in ('png','mp4','txt'):
                sql("INSERT INTO sys_file (id,create_by,file_path,file_name,file_location,file_type) VALUES ('"+PREFIX+suffix+"','fixture_student_a','"+FOLDER+'/probe.'+suffix+"','synthetic probe',1,2)")
            for actor in ('student_a','student_b'): api.login(actor)
            backend='http://127.0.0.1:'+str(api.ports['backend'])
            class Handler(BaseHTTPRequestHandler):
                def log_message(self,*args): pass
                def do_HEAD(self): self.do_GET()
                def do_GET(self):
                    if self.path.startswith('/api/sys/common/static/'+FOLDER+'/'):
                        headers={k:self.headers[k] for k in ('Cookie','Range') if self.headers.get(k)}
                        request=Request(backend+self.path,headers=headers,method=self.command)
                        try: response=urlopen(request,timeout=15)
                        except HTTPError as error: response=error
                        with response:
                            body=response.read();self.send_response(response.status)
                            for k,v in response.headers.items():
                                if k.lower() not in ('transfer-encoding','connection','date','server'):self.send_header(k,v)
                            self.end_headers()
                            if self.command!='HEAD':self.wfile.write(body)
                            report.append({'method':self.command,'asset':self.path.rsplit('/',1)[-1],'status':response.status,'bytes':len(body),'cookie_present':bool(headers.get('Cookie')),'range':headers.get('Range')})
                        return
                    if self.path not in ('/','/owner','/foreign','/logout'): self.send_error(404);return
                    state={'/':'匿名','/owner':'作者','/foreign':'其他学生','/logout':'作者已退出'}[self.path]
                    cookies=[]
                    if self.path!='/':
                        actor='student_b' if self.path=='/foreign' else 'student_a'
                        route='/api/sys/logout' if self.path=='/logout' else '/api/system/sysFile/list'
                        with urlopen(Request(backend+route,headers={'X-Access-Token':api.tokens[actor]}),timeout=15) as r:
                            r.read();cookies=r.headers.get_all('Set-Cookie',[])
                    else: cookies=['teaching_media_'+str(api.ports['backend'])+'=; Path=/api/sys/common/static; Max-Age=0; HttpOnly; SameSite=Strict']
                    body=PAGE.replace('STATE',state).encode()
                    self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(body)))
                    for cookie in cookies: self.send_header('Set-Cookie',cookie)
                    self.end_headers();self.wfile.write(body)
            server=HTTPServer(('127.0.0.1',args.port),Handler)
            server.timeout=1
            def stop(*unused): raise KeyboardInterrupt()
            signal.signal(signal.SIGTERM,stop)
            print('Media fixture ready at http://127.0.0.1:'+str(args.port),flush=True)
            end=time.monotonic()+1200
            try:
                while time.monotonic()<end:server.handle_request()
            except KeyboardInterrupt: pass
            finally:server.server_close()
        finally:
            sql("DELETE FROM sys_file WHERE id LIKE '"+PREFIX+"%'")
            for p in folder.iterdir():p.unlink()
            folder.rmdir()
            result={'observed_utc':datetime.now(timezone.utc).isoformat(),'jar_sha256':api.jar_sha256,'requests':report,'fixture_removed':not folder.exists() and sql("SELECT COUNT(*) FROM sys_file WHERE id LIKE '"+PREFIX+"%'")=='0','scope':'controlled browser media fixture; authentication obtained through actual local APIs outside browser; not product login/editor acceptance'}
            args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
            print('Media probe cleaned up',flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--runtime',type=Path,required=True);p.add_argument('--jar',type=Path);p.add_argument('--port',type=int,default=18113);p.add_argument('--output',type=Path,required=True)
    main(p.parse_args())
