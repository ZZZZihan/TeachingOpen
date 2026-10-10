from pathlib import Path
import collections, datetime, hashlib, io, json, re, zipfile
base=Path(__file__).resolve().parent
root=Path('/Users/xuzihan/Documents/Projects/TeachingOpen')
sha=lambda b: hashlib.sha256(b).hexdigest()
manifest=json.loads((base/'source-manifest.json').read_text())
pre=json.loads((base/'pre-build.json').read_text())
run=json.loads((base/'build-run.json').read_text())
assert run['status']=='complete'
log=(base/'build.log').read_text(errors='replace')
source_errors=[]
for row in manifest['files']:
    p=base/row['path']
    if not p.is_file() or sha(p.read_bytes())!=row['sha256']:
        source_errors.append(row['path'])
settings=base/'api/dev/maven-settings.xml'
jar=base/'api/jeecg-boot-module-system/target/teaching-open-2.8.0.jar'
frozen=root/'.devspace/artifacts/account-recovery-20261005/api-author/teaching-open-account-recovery.jar'
result={'schema_version':1,'generated_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'scope':'Precise committed api source, macOS arm64 JDK8, isolated cold Maven cache compilation and packaging only','source_commit':manifest['commit'],'api_tree':manifest['api_tree'],'source_archive_sha256':manifest['archive_sha256'],'source_manifest_sha256':sha((base/'source-manifest.json').read_bytes()),'source_file_count':manifest['file_count'],'source_file_hash_mismatches_after_build':source_errors,'cache_was_empty':pre['cache_before_file_count']==0 and pre['cache_before_entry_count']==0 and run['cache_file_count_at_start']==0 and run['cache_entry_count_at_start']==0,'project_settings_sha256':sha(settings.read_bytes()),'isolated_global_settings_sha256':pre['isolated_global_settings_sha256'],'java_maven_versions':json.loads((base/'tool-versions.json').read_text()),'build':run,'test_status':{'java_tests_executed':False,'parent_pom_skipTests':True,'surefire_skipped_log_lines':[line for line in log.splitlines() if 'Tests are skipped.' in line],'test_result_claim':'Java tests explicitly skipped by the default parent POM; BUILD SUCCESS is compilation and packaging evidence only'},'network':{'downloaded_log_event_count':sum('Downloaded from ' in line for line in log.splitlines()),'download_repository_ids':sorted(set(re.findall(r'Downloaded from ([^: ]+):',log)))},'reportable_build_success':run['exit_code']==0 and '[INFO] BUILD SUCCESS' in log and jar.is_file(),'jar':None,'comparison':None}
if jar.is_file():
    jbytes=jar.read_bytes(); fbytes=frozen.read_bytes()
    result['jar']={'path':str(jar),'bytes':len(jbytes),'sha256':sha(jbytes),'frozen_path':str(frozen),'frozen_bytes':len(fbytes),'frozen_sha256':sha(fbytes),'whole_archive_bytes_equal':jbytes==fbytes}
    libraries=[]
    with zipfile.ZipFile(io.BytesIO(jbytes)) as fresh, zipfile.ZipFile(io.BytesIO(fbytes)) as old:
        def entries(z,prefix):
            return {i.filename:{'bytes':i.file_size,'sha256':sha(z.read(i.filename))} for i in z.infolist() if i.filename.startswith(prefix) and not i.is_dir()}
        def compare(a,b):
            shared=sorted(a.keys()&b.keys())
            differences=[{'path':p,'new_bytes':a[p]['bytes'],'frozen_bytes':b[p]['bytes'],'new_sha256':a[p]['sha256'],'frozen_sha256':b[p]['sha256']} for p in shared if a[p]!=b[p]]
            return {'new_file_count':len(a),'frozen_file_count':len(b),'path_set_equal':a.keys()==b.keys(),'only_new_paths':sorted(a.keys()-b.keys()),'only_frozen_paths':sorted(b.keys()-a.keys()),'equal_file_count':sum(a[p]==b[p] for p in shared),'different_files':differences,'all_file_bytes_equal':a==b}
        fresh_lib=entries(fresh,'BOOT-INF/lib/'); frozen_lib=entries(old,'BOOT-INF/lib/')
        fresh_cls=entries(fresh,'BOOT-INF/classes/'); frozen_cls=entries(old,'BOOT-INF/classes/')
        all_new=entries(fresh,''); all_old=entries(old,'')
        for path in sorted(fresh_lib):
            data=fresh.read(path)
            props=[]
            with zipfile.ZipFile(io.BytesIO(data)) as dep:
                for p in sorted(dep.namelist()):
                    if p.startswith('META-INF/maven/') and p.endswith('/pom.properties'):
                        values={}
                        for line in dep.read(p).decode('utf-8',errors='replace').splitlines():
                            if line and not line.startswith('#') and '=' in line:
                                k,v=line.split('=',1)
                                if k in ('groupId','artifactId','version'): values[k]=v
                        props.append(values)
            internal=path.rsplit('/',1)[-1]=='jeecg-boot-base-common-2.8.0.jar'
            libraries.append({'path':path,'internal_reactor_artifact':internal,**fresh_lib[path],'maven_properties':props,'frozen_sha256':frozen_lib.get(path,{}).get('sha256'),'bytes_equal_to_frozen':fresh_lib[path]==frozen_lib.get(path)})
        libcmp=compare(fresh_lib,frozen_lib)
        internal_diffs=[]
        for diff in libcmp['different_files']:
            path=diff['path']
            if not path.endswith('/jeecg-boot-base-common-2.8.0.jar'):
                continue
            with zipfile.ZipFile(io.BytesIO(fresh.read(path))) as new_dep, zipfile.ZipFile(io.BytesIO(old.read(path))) as old_dep:
                nested=compare(entries(new_dep,''),entries(old_dep,''))
                new_info={i.filename:i for i in new_dep.infolist()}; old_info={i.filename:i for i in old_dep.infolist()}
                meta=[]
                for p in sorted(new_info.keys()&old_info.keys()):
                    a=new_info[p]; b=old_info[p]
                    changed=[]
                    for attr in ('date_time','compress_type','compress_size','flag_bits','external_attr','extra','comment'):
                        if getattr(a,attr)!=getattr(b,attr): changed.append(attr)
                    if changed:
                        meta.append({'path':p,'different_metadata_fields':changed,'new_zip_datetime':a.date_time,'frozen_zip_datetime':b.date_time})
                internal_diffs.append({'path':path,'nested_file_comparison':nested,'zip_metadata_differences':meta,'reason':'Nested file path sets and all payload bytes equal; ZIP metadata differs.' if nested['all_file_bytes_equal'] and meta else 'Payload or ZIP packaging difference requires further review.'})
        external=[r for r in libraries if not r['internal_reactor_artifact']]
        internal=[r for r in libraries if r['internal_reactor_artifact']]
        result['jar']['embedded_library_count']=len(libraries)
        result['jar']['external_library_count']=len(external)
        result['jar']['internal_library_count']=len(internal)
        result['comparison']={'boot_inf_lib':libcmp,'boot_inf_classes':compare(fresh_cls,frozen_cls),'boot_inf_class_file_count':sum(p.endswith('.class') for p in fresh_cls),'boot_inf_resource_file_count':sum(not p.endswith('.class') for p in fresh_cls),'external_library_bytes_equal_count':sum(r['bytes_equal_to_frozen'] for r in external),'internal_library_bytes_equal_count':sum(r['bytes_equal_to_frozen'] for r in internal),'internal_library_differences':internal_diffs,'whole_jar_file_entries':compare(all_new,all_old)}
    (base/'dependency-inventory.json').write_text(json.dumps({'libraries':libraries},indent=2)+'\n')
    (base/'jar-entry-manifest.json').write_text(json.dumps({'fresh':all_new,'frozen':all_old},indent=2)+'\n')
result['verdict']='PASS_COMPILE_PACKAGE_AND_DEPENDENCY_REPRODUCTION' if result['reportable_build_success'] and not source_errors and result['cache_was_empty'] and result['comparison']['external_library_bytes_equal_count']==208 and result['comparison']['boot_inf_classes']['all_file_bytes_equal'] else 'REVIEW_REQUIRED'
(base/'result.json').write_text(json.dumps(result,indent=2)+'\n')
lines=['# TeachingOpen 精确候选后端空缓存构建审计','','本记录只确认从精确提交源码、私有空 Maven 缓存完成依赖解析、编译和打包，以及与现有冻结 JAR 的文件内容比较。Java 测试由父 POM 默认设置跳过；没有运行任何服务或业务验收。','','- 源提交：`'+manifest['commit']+'`','- api Git 树：`'+manifest['api_tree']+'`','- 源文件数量：'+str(manifest['file_count'])+'；构建后摘要差异：'+str(len(source_errors)),'- 初始 Maven 缓存：0 个条目，0 个文件（见 `pre-build.json` 和 `build-run.json`）。','- 项目 settings SHA-256：`'+result['project_settings_sha256']+'`','- 使用额外 `-gs empty-global-settings.xml`，覆盖全局 settings；`MAVEN_SKIP_RC=true`，本次移除可影响 JVM/Maven 的自定义参数变量。','- Maven/JDK 实际版本：见 `tool-versions.json`；本次未修改机器级配置。','','## 构建命令','','```sh','JAVA_HOME='+run['environment_overrides']['JAVA_HOME']+' MAVEN_SKIP_RC=true '+run['command_shell'],'```','','执行目录：`'+run['cwd']+'`','开始 UTC：`'+run['started_utc']+'`；结束 UTC：`'+run['finished_utc']+'`。','退出码：`'+str(run['exit_code'])+'`；耗时 '+str(run['duration_seconds'])+' 秒。','Maven 日志 `BUILD SUCCESS`：'+str('[INFO] BUILD SUCCESS' in log)+'。日志 SHA-256：`'+run['build_log_sha256']+'`。','实际下载记录：'+str(result['network']['downloaded_log_event_count'])+' 条，仓库标识：'+', '.join(result['network']['download_repository_ids'])+'。','','## Java 测试状态','','父 POM `skipTests=true`，Surefire 配置 `<skipTests>${skipTests}</skipTests>`。实际日志出现 `Tests are skipped.` '+str(len(result['test_status']['surefire_skipped_log_lines']))+' 次。此轮 Java 测试未执行，不能将编译打包成功写成测试通过。']
if result['jar']:
    j=result['jar']; c=result['comparison']
    lines+=['','## JAR 与冻结产物比较','','新 JAR：`'+j['path']+'`','字节数：'+str(j['bytes'])+'；SHA-256：`'+j['sha256']+'`。','冻结 JAR：`'+j['frozen_path']+'`','冻结 SHA-256：`'+j['frozen_sha256']+'`。','整包字节相同：'+str(j['whole_archive_bytes_equal'])+'。','','`BOOT-INF/lib/` 共 '+str(j['embedded_library_count'])+' 个 JAR：外部依赖 '+str(j['external_library_count'])+' 个，项目 reactor 产物 '+str(j['internal_library_count'])+' 个。路径集合相等：'+str(c['boot_inf_lib']['path_set_equal'])+'。外部依赖按路径和字节与冻结包相等：'+str(c['external_library_bytes_equal_count'])+'/'+str(j['external_library_count'])+'。全部版本、Maven 坐标与单文件摘要见 `dependency-inventory.json`。','','`BOOT-INF/classes/` '+str(c['boot_inf_classes']['new_file_count'])+' 个文件（class '+str(c['boot_inf_class_file_count'])+'，resource '+str(c['boot_inf_resource_file_count'])+'），与冻结包路径集合和文件内容相等：'+str(c['boot_inf_classes']['all_file_bytes_equal'])+'。比较没有排除任何 class/resource 文件；只忽略 ZIP 时间和目录条目的空 payload。','']
    for d in c['boot_inf_lib']['different_files']:
        lines+=['- 嵌入 JAR 字节差异：`'+d['path']+'`；新 SHA-256 `'+d['new_sha256']+'`；冻结 SHA-256 `'+d['frozen_sha256']+'`。']
    for d in c['internal_library_differences']:
        n=d['nested_file_comparison']
        lines+=['- 对上述项目 JAR 解包后：路径集合相等 '+str(n['path_set_equal'])+'，全部 '+str(n['new_file_count'])+' 个文件 payload 相等 '+str(n['all_file_bytes_equal'])+'；ZIP 元数据不同条目 '+str(len(d['zip_metadata_differences']))+'。原因判定：'+d['reason']]
    for d in c['boot_inf_classes']['different_files']:
        lines+=['- class/resource 字节差异：`'+d['path']+'`；具体原因未认定，需要复核，正文不展示配置。']
    for p in c['boot_inf_classes']['only_new_paths']:
        lines+=['- class/resource 新增路径：`'+p+'`。']
    for p in c['boot_inf_classes']['only_frozen_paths']:
        lines+=['- class/resource 缺失路径：`'+p+'`。']
    lines+=['','全 JAR 内容条目摘要与差异见 `jar-entry-manifest.json` 和 `result.json`；未忽略其他内容差异。']
lines+=['','## 结论与边界','','结论：`'+result['verdict']+'`。','','本次从新私有缓存解析依赖，没有复制现有 Maven 缓存、修改依赖版本、关闭 TLS、启动服务、连接数据库/Redis、执行登录/验证码/安全探针、运行浏览器或替换冻结产物。没有修改产品源码、创建分支/PR或推送。成功只针对本机 macOS arm64 固定工具和本次网络状态，不能推及其他机器或生产。','']
(base/'REPORT.md').write_text('\n'.join(lines))
for p in base.iterdir():
    if p.is_file(): p.chmod(0o600)
print(json.dumps({'verdict':result['verdict'],'jar':result['jar'],'source_file_hash_mismatches_after_build':source_errors,'java_test_skipped_logs':len(result['test_status']['surefire_skipped_log_lines']),'boot_inf_classes':result['comparison']['boot_inf_classes'] if result['comparison'] else None,'boot_inf_lib':result['comparison']['boot_inf_lib'] if result['comparison'] else None},indent=2))
