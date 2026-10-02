const assert=require('node:assert/strict')
const {test}=require('node:test')
const vm=require('node:vm'),fs=require('node:fs'),path=require('node:path')
const persistence=require('../public/python/persistence.js')
const flush=()=>new Promise(r=>setImmediate(r))
async function mount(overrides={}){
 const h={calls:[],token:'session-a',cloud:[],history:[],readOnly:[],events:{},nodes:{'persistence-status':{dataset:{}},'retry-load':{}},content:'print(42)'}
 const host={projectName:'',code:'',$refs:{codeEditor:{editor:{setReadOnly:v=>h.readOnly.push(v)},$watch(){}}},$set:(o,k,v)=>{o[k]=v},$watch(){},setCode:v=>{host.code=v},getCode:()=>host.code}
 const context={URL,URLSearchParams,Blob,FormData,Promise,setTimeout,clearTimeout,PythonPersistence:persistence,document:{getElementById:id=>h.nodes[id]},location:{search:'?workId=existing',href:'http://fixture.test/python/index.html?workId=existing'},history:{replaceState:(s,t,url)=>h.history.push(url)},getUserToken:()=>h.token,uuid:()=> 'fixture-uuid',addEventListener:(name,fn)=>{h.events[name]=fn},qiniu:{region:{z0:{}},upload:(...args)=>{h.cloud.push(args);return {subscribe:observer=>{observer.complete({key:args[1]});return {unsubscribe(){}}}}}},$: {ajax:o=>{
  h.calls.push(o)
  const response=overrides.response&&overrides.response(o)
  if(response==='error'){o.error({status:401});return}
  if(response!==undefined){o.success(response,'success',{getResponseHeader:()=> 'text/plain'});return}
  if(o.url.includes('studentWorkInfo'))o.success({code:0,success:true,result:{id:'existing',workType:4,workName:'作品',workFileKey_url:'http://files.test/code.py'}})
  else if(o.url==='http://files.test/code.py')o.success(h.content,'success',{getResponseHeader:()=>overrides.mime||'text/plain'})
  else if(o.url.includes('getCurrentConfig'))o.success({code:0,result:{uploadType:overrides.cloud?'qiniu':'local',qiniuArea:'z0'}})
  else if(o.url.includes('getToken'))o.success({code:200,success:true,result:'fixture-cloud-credential',keyPrefix:'server-owned/'})
  else if(o.url.endsWith('/upload'))o.success({success:true,message:'python/upload.py'})
  else if(o.url.endsWith('/add'))o.success({success:true,result:{id:'file-owned',filePath:JSON.parse(o.data).filePath}})
  else if(o.url.endsWith('/submit'))o.success({code:200,success:true,result:{id:'existing'}})
  else throw new Error('Unexpected request '+o.url)
 }}}
 context.window=context;vm.createContext(context);vm.runInContext(fs.readFileSync(path.join(__dirname,'../public/python/editor-bridge.js'),'utf8'),context);context.TeachingPython.mount(host);await flush()
 return {...h,h,host,context}
}
test('桥接没有 CONFIG 缓存也可本地上传、登记、提交；每次 API 使用当前令牌',async()=>{
 const {h,host,context}=await mount();assert.equal(host.persistReady,true);h.token='session-b';await context.submitCode('新名称','print(7)')
 const writes=h.calls.filter(o=>o.type==='POST');assert.equal(writes.length,3);for(const r of writes)assert.equal(r.headers['X-Access-Token'],'session-b')
 assert.equal(h.calls.find(o=>o.url==='http://files.test/code.py').headers,undefined);assert.equal(writes[0].url,'/api/sys/common/upload');assert.equal(JSON.parse(writes[2].data).workFile,'file-owned');assert.match(h.history[0],/workId=existing/)
})
test('文件返回 HTML 登录页不会作为代码载入；401 有明确提示且解除忙状态',async()=>{
 const bad=await mount({mime:'text/html'});assert.equal(bad.host.persistReady,false);assert.equal(bad.host.code,'');assert.match(bad.h.nodes['persistence-status'].textContent,/文件格式/)
 const h=await mount({response:o=>o.url.includes('getCurrentConfig')?'error':undefined});await h.context.submitCode('作品','print(1)');assert.equal(h.host.persistBusy,false);assert.match(h.h.nodes['persistence-status'].textContent,/登录已失效/);assert.equal(h.h.calls.some(o=>o.url.endsWith('/submit')),false)
})
test('文件登记路径不匹配、业务失败不能进入提交成功状态',async()=>{
 const h=await mount({response:o=>o.url.endsWith('/add')?{success:true,result:{id:'foreign',filePath:'wrong'}}:undefined});await h.context.submitCode('作品','print(1)');assert.equal(h.h.calls.some(o=>o.url.endsWith('/submit')),false);assert.match(h.h.nodes['persistence-status'].textContent,/登记失败/)
})
test('云上传使用服务器前缀和单次凭据，不向云传平台会话；验证返回键后登记',async()=>{
 const h=await mount({cloud:true});await h.context.submitCode('作品','print(1)');const [file,key,token,extra,config]=h.h.cloud[0]
 assert.ok(file instanceof Blob);assert.equal(key,'server-owned/python/fixture-uuid.py');assert.equal(token,'fixture-cloud-credential');assert.equal(JSON.stringify(extra).includes('session-a'),false);assert.equal(JSON.stringify(config).includes('session-a'),false)
 const registration=JSON.parse(h.h.calls.find(o=>o.url.endsWith('/add')).data);assert.equal(registration.fileLocation,2);assert.equal(registration.filePath,key)
})
test('未保存改动或正在保存时有离页提示，打开后未修改不触发',async()=>{
 const h=await mount();let prevented=0;const event={preventDefault:()=>prevented++};h.h.events.beforeunload(event);assert.equal(prevented,0);h.host.code='new code';h.h.events.beforeunload(event);assert.equal(prevented,1)
})
test('预编译编辑器只在下一轮渲染完成后挂接；本地导出和提交读取当前 Ace 内容',()=>{
 const source=fs.readFileSync(path.join(__dirname,'../public/python/static/js/app.js'),'utf8')
 const componentSource=source.slice(source.indexOf('c={name:"PythonEditor"')+2,source.indexOf(',p={render:',source.indexOf('c={name:"PythonEditor"')))
 const callbacks=[],mounted=[],downloads=[],submitted=[]
 const context={component:null,window:{TeachingPython:{mount:h=>mounted.push(h)},submitCode:(...v)=>submitted.push(v)},o:{a:{}},s:{a:{}},r:{saveAs:f=>downloads.push(f)},File,document:{},u:{}}
 vm.createContext(context);vm.runInContext('component='+componentSource,context)
 const component=context.component;const h={code:'stale',projectName:'作品',getCode:()=> 'current Ace code',$nextTick:fn=>callbacks.push(fn)}
 assert.equal(component.data().persistBusy,true);assert.equal(component.data().persistReady,false)
 component.created.call(h);assert.equal(mounted.length,0);callbacks[0]();assert.equal(mounted[0],h)
 component.methods.saveFile.call(h);assert.equal(downloads[0].size,new Blob(['current Ace code']).size)
 component.methods.submitCode.call(h);assert.equal(submitted[0][1],'current Ace code')
})
