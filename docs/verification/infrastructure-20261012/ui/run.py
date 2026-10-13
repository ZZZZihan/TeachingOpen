#!/usr/bin/env python3
"""Build exact refs, run a fresh isolated Playwright CLI session, save before/after UI evidence."""
import argparse, hashlib, json, os, socket, struct, subprocess, time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen
from uuid import uuid4

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--repo',type=Path,required=True)
parser.add_argument('--before',default='a3f4e10c')
parser.add_argument('--after',default='HEAD')
parser.add_argument('--node-modules',type=Path,required=True)
parser.add_argument('--cli',type=Path,required=True,help='Cached @playwright/cli/playwright-cli.js; no install or network download.')
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args()
base=Path(__file__).resolve().parent
repo,modules,out=args.repo.resolve(),args.node_modules.resolve(),args.output.resolve()
out.mkdir(parents=True,exist_ok=True)
env=dict(os.environ,TEACHING_NODE_MODULES=str(modules))
session='h01-ui-'+uuid4().hex[:10]
cli=['node',str(args.cli.resolve()),'-s='+session]
servers=[];streams=[]

def run(command,log):
    result=subprocess.run(command,cwd=out,env=env,capture_output=True,text=True,timeout=180)
    (out/log).write_text(result.stdout+result.stderr)
    if result.returncode: raise RuntimeError(str(command[:3])+' failed; see '+str(out/log))
    return result.stdout

def port():
    with socket.socket() as s:
        s.bind(('127.0.0.1',0))
        return s.getsockname()[1]

try:
    origins={}
    for name,ref in [('before',args.before),('after',args.after)]:
        run(['node',str(base/'build.cjs'),str(repo),ref,str(out/name)],'build-'+name+'.log')
        stream=(out/('server-'+name+'.log')).open('w');streams.append(stream)
        server_port=port()
        servers.append(subprocess.Popen(['python3',str(base/'server.py'),'--directory',str(out/name),'--port',str(server_port),'--requests',str(out/(name+'-requests.json'))],stdout=stream,stderr=stream))
        origins[name]='http://127.0.0.1:'+str(server_port)
        for attempt in range(100):
            try:
                with urlopen(origins[name]+'/__state',timeout=1) as response:
                    if response.status==200: break
            except OSError: time.sleep(.1)
        else: raise RuntimeError('Synthetic server did not become ready')
    run(cli+['open','about:blank','--browser','chrome'],'browser-open.log')
    scenario=(base/'verify-browser.js').read_text()
    lines=scenario.splitlines()
    lines=[('  const out='+json.dumps(str(out))) if line.startswith('  const out=') else ('  const origins='+json.dumps(origins)) if line.startswith('  const origins=') else line for line in lines]
    generated=out/'browser-scenario.generated.js'
    generated.write_text('\n'.join(lines)+'\n')
    raw=run(cli+['run-code','--filename',str(generated)],'browser-run.log')
    result=json.loads(raw.split('### Result\n',1)[1].split('\n',1)[0])
    result['observed_utc']=datetime.now(timezone.utc).isoformat()
    result['before_manifest']=json.loads((out/'before/source-manifest.json').read_text())
    result['after_manifest']=json.loads((out/'after/source-manifest.json').read_text())
    result['runner_files']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [base/'run.py',base/'build.cjs',base/'entry.js',base/'api.js',base/'dict-api.js',base/'util.js',base/'server.py',base/'verify-browser.js']}
    for shot in result.get('screenshots',[]):
        png=(out/shot['file']).read_bytes()
        shot['actual_png_width'],shot['actual_png_height']=struct.unpack('>II',png[16:24])
        shot['sha256']=hashlib.sha256(png).hexdigest()
    (out/'browser-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:result.get(k) for k in ('status','passed','failed','total','observed_utc')},ensure_ascii=False))
    if result.get('status')!='passed': raise RuntimeError('Browser scenario failed; see browser-result.json')
finally:
    try: run(cli+['close'],'browser-close.log')
    except Exception as error: print('Browser close:',error)
    for server in servers:
        server.terminate()
        try: server.wait(timeout=5)
        except subprocess.TimeoutExpired: server.kill();server.wait()
    for stream in streams: stream.close()
