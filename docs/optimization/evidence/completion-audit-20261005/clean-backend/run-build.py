from pathlib import Path
import datetime, hashlib, json, os, shlex, subprocess, time
base=Path(__file__).resolve().parent
root=Path('/Users/xuzihan/Documents/Projects/TeachingOpen')
java=root/'.devspace/backend-runtime/tools/zulu8.96.0.205-ca-jdk8.0.504-macosx_aarch64/Contents/Home'
maven=root/'.devspace/backend-runtime/tools/apache-maven-3.9.16/bin/mvn'
assert (base/'cache').is_dir()
assert not any((base/'cache').iterdir()), 'Cache must remain empty before first build'
env=os.environ.copy()
for name in ('MAVEN_OPTS','MAVEN_ARGS','JAVA_TOOL_OPTIONS','JDK_JAVA_OPTIONS','_JAVA_OPTIONS','MAVEN_PROJECTBASEDIR'):
    env.pop(name,None)
env['JAVA_HOME']=str(java)
env['MAVEN_SKIP_RC']='true'
versions={}
for name,cmd in [('java',[str(java/'bin/java'),'-version']),('maven',[str(maven),'-version'])]:
    proc=subprocess.run(cmd,env=env,cwd=base/'api',text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    versions[name]={'command':cmd,'exit_code':proc.returncode,'output':proc.stdout}
    assert proc.returncode==0
(base/'tool-versions.json').write_text(json.dumps(versions,indent=2)+'\n')
command=[str(maven),'-B','-s','dev/maven-settings.xml','-gs',str(base/'empty-global-settings.xml'),'-Dmaven.repo.local='+str(base/'cache'),'clean','package']
started=datetime.datetime.now(datetime.timezone.utc).isoformat()
record={'command':command,'command_shell':shlex.join(command),'cwd':str(base/'api'),'environment_overrides':{'JAVA_HOME':str(java),'MAVEN_SKIP_RC':'true'},'removed_environment_variables':['MAVEN_OPTS','MAVEN_ARGS','JAVA_TOOL_OPTIONS','JDK_JAVA_OPTIONS','_JAVA_OPTIONS','MAVEN_PROJECTBASEDIR'],'started_utc':started,'cache_file_count_at_start':sum(p.is_file() for p in (base/'cache').rglob('*')),'cache_entry_count_at_start':sum(1 for p in (base/'cache').rglob('*')),'status':'running'}
(base/'build-run.json').write_text(json.dumps(record,indent=2)+'\n')
print('Maven clean package started with empty private cache',flush=True)
t0=time.monotonic()
with (base/'build.log').open('w') as log:
    proc=subprocess.Popen(command,cwd=base/'api',env=env,stdout=log,stderr=subprocess.STDOUT)
    record['pid']=proc.pid
    (base/'build-run.json').write_text(json.dumps(record,indent=2)+'\n')
    code=proc.wait()
record.update({'finished_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'duration_seconds':round(time.monotonic()-t0,3),'exit_code':code,'status':'complete','cache_file_count_after':sum(p.is_file() for p in (base/'cache').rglob('*')),'cache_entry_count_after':sum(1 for p in (base/'cache').rglob('*')),'build_log_sha256':hashlib.sha256((base/'build.log').read_bytes()).hexdigest()})
(base/'build-run.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps({k:record[k] for k in ('finished_utc','duration_seconds','exit_code','cache_file_count_after','build_log_sha256')},indent=2),flush=True)
raise SystemExit(code)
