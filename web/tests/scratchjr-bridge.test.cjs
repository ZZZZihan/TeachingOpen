const {test}=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto')
const persistence=require('../public/scratch3/persistence.js'),flush=()=>new Promise(r=>setImmediate(r))
async function mount(options={}) {
 const h={calls:[],files:[],frames:[],history:[],nodes:{},name:'本机作品',captures:0,stops:0}
 for(const id of ['project-name','persistence-status','retry-load','save-draft','submit-work','engine-host'])h.nodes[id]={dataset:{},value:'',setAttribute(){}}
 h.nodes.actions={};h.nodes['engine-host'].appendChild=f=>{h.frames.push(f);if(!options.pending)queueMicrotask(()=>context.TeachingJunior.loaded(f.contentWindow))}
 class XHR {open(method,url){h.files.push(url)}send(){this.status=options.fileStatus||200;this.response=new Uint8Array([80,75]).buffer;this.onload()}getResponseHeader(){return options.mime||'application/octet-stream'}}
 const context={URL,URLSearchParams,Blob,FormData,Promise,Uint8Array,atob,setTimeout,clearTimeout,XMLHttpRequest:XHR,ScratchPersistence:persistence,
  location:{search:options.search||'?workId=owned',href:'http://fixture.test/scratchjr/editor.html'+(options.search||'?workId=owned')},history:{replaceState:(s,t,url)=>h.history.push(url)},getUserToken:()=>h.token||'session-a',uuid:()=> 'fixture-uuid',
  document:{getElementById:id=>h.nodes[id],querySelector:()=>h.nodes.actions,createElement:()=>({setAttribute(){},remove(){this.removed=true},contentWindow:{ScratchJr:{getProjectName:()=>h.name,setProjectName:name=>{h.name=name},stopStrips:()=>h.stops++,getProjectSjr:cb=>{h.captures++;cb(new Blob(['sjr']))},getProjectCover:cb=>cb(options.invalidCover?'bad':'data:image/png;base64,iVBORw0KGgo=')}}})},
  qiniu:{region:{z0:{}},upload:(file,key)=>({subscribe:observer=>{observer.complete({key});return {unsubscribe(){}}}})},
  $:{ajax:o=>{
   h.calls.push(o);let overridden=options.response&&options.response(o);if(overridden==='401'){o.error({status:401});return}if(overridden!==undefined){o.success(overridden);return}
   if(o.url.includes('studentWorkInfo'))o.success({success:true,result:{workType:3,workName:'作品 & 100%',workFileKey_url:'/works/owned.sjr',additionalId:'task',departId:'class'}})
   else if(o.url.includes('getUnitWorkInfo'))o.success({success:true,result:{unitName:'课程练习',courseWork_url:'/unit.sjr'}})
   else if(o.url.includes('getCurrentConfig'))o.success({result:{uploadType:'local'}})
   else if(o.url.endsWith('/upload'))o.success({success:true,message:'scratchjr/'+o.data.get('file').name})
   else if(o.url.endsWith('/add')){let b=JSON.parse(o.data);o.success({success:true,result:{id:b.fileName.endsWith('.sjr')?'sjr-id':'cover-id',filePath:b.filePath}})}
   else if(o.url.endsWith('/submit'))o.success({success:true,result:{id:'saved-id'}})
   else throw new Error(o.url)
  }}
 }
 context.window=context;vm.createContext(context);vm.runInContext(fs.readFileSync(path.join(__dirname,'../public/scratchjr/editor-bridge.js'),'utf8'),context);await flush();h.context=context;return h
}
test('ScratchJr 取服务器作品并生成 SJR/PNG，保存 ID、类型、任务与新令牌',async()=>{
 const h=await mount();assert.equal(h.files[0],'http://fixture.test/works/owned.sjr');assert.match(h.frames[0].src,/workFile=blob:/);assert.equal(h.name,'作品 & 100%');assert.equal(h.nodes['engine-host'].inert,false)
 h.token='session-b';await h.nodes['save-draft'].onclick();const body=JSON.parse(h.calls.find(o=>o.url.endsWith('/submit')).data)
 assert.equal(body.workType,3);assert.equal(body.workStatus,0);assert.equal(body.id,'owned');assert.equal(body.workFile,'sjr-id');assert.equal(body.workCover,'cover-id');assert.equal(body.additionalId,'task');assert.equal(body.departId,'class');assert.equal(h.captures,1);assert.equal(h.stops,1)
 assert.match(h.history[0],/workId=saved-id/);assert.equal(h.calls.filter(o=>o.type==='POST').every(o=>o.headers['X-Access-Token']==='session-b'),true)
})
test('本机新作保留本机名；已有平台 ID 忽略陈旧 pmd5',async()=>{
 let h=await mount({search:'?pmd5=local-id'});assert.equal(h.files.length,0);assert.match(h.frames[0].src,/pmd5=local-id/);assert.equal(h.nodes['project-name'].value,'本机作品');await h.nodes['save-draft'].onclick();assert.equal(h.history[0].includes('pmd5'),false)
 h=await mount({search:'?workId=owned&pmd5=old-local-id'});assert.equal(h.files.length,1);assert.equal(h.frames[0].src.includes('pmd5'),false)
})
test('HTTP 失败与 HTML 文件不启动引擎、不允许提交',async()=>{
 for(const options of [{fileStatus:503},{mime:'text/html'}]){const h=await mount(options);assert.equal(h.frames.length,0);assert.equal(h.nodes['submit-work'].disabled,true);assert.equal(h.nodes['retry-load'].hidden,false)}
})
test('引擎错误销毁实例，旧回调不解除新实例的加载锁',async()=>{
 const h=await mount({pending:true}),old=h.frames[0];h.context.TeachingJunior.failed(old.contentWindow);await flush();assert.equal(old.removed,true);assert.equal(h.nodes['save-draft'].disabled,true)
 const retry=h.nodes['retry-load'].onclick();await flush();assert.equal(h.frames.length,2);h.context.TeachingJunior.loaded(old.contentWindow);assert.equal(h.nodes['save-draft'].disabled,true)
 h.context.TeachingJunior.loaded(h.frames[1].contentWindow);await retry;assert.equal(h.nodes['save-draft'].disabled,false)
})
test('封面无效、文件登记不匹配、401 均保留编辑且不业务提交',async()=>{
 for(const options of [{invalidCover:true},{response:o=>o.url.endsWith('/add')?{success:true,result:{id:'wrong',filePath:'wrong'}}:undefined},{response:o=>o.url.endsWith('/upload')?'401':undefined}]){
  const h=await mount(options);await h.nodes['submit-work'].onclick();assert.equal(h.calls.some(o=>o.url.endsWith('/submit')),false);assert.equal(h.nodes['engine-host'].inert,false);assert.match(h.nodes['persistence-status'].textContent,/保存未完成/)
 }
})
test('预览模式隐藏提交，原生云保存入口也不能写入',async()=>{
 const h=await mount({search:'?mode=look&workFile=/preview.sjr'});assert.equal(h.nodes.actions.hidden,true);assert.equal(h.nodes['project-name'].disabled,true);h.context.TeachingJunior.save(h.frames[0].contentWindow);await flush();assert.equal(h.captures,0);assert.match(h.frames[0].src,/mode=look/)
})
test('标题与原生变化触发离页提醒；成功保存后清除',async()=>{
 const h=await mount();let n=0;const event={preventDefault(){n++}};h.context.onbeforeunload(event);assert.equal(n,0)
 h.nodes['project-name'].value='新版';h.nodes['project-name'].oninput();assert.equal(h.name,'新版');h.context.onbeforeunload(event);assert.equal(n,1);await h.nodes['save-draft'].onclick();h.context.onbeforeunload(event);assert.equal(n,1)
 h.context.TeachingJunior.changed(h.frames[0].contentWindow);h.context.onbeforeunload(event);assert.equal(n,2)
})
test('引擎仅含声明的六处局部修补，恢复后字节哈希等于上游基线',()=>{
 const patch=require('./scratchjr-preview/vendor-patch.json');let source=fs.readFileSync(path.join(__dirname,'../public/scratchjr/app.bundle.js'),'utf8')
 assert.equal(patch.replacements.length,6)
 for(const [old,next] of [...patch.replacements].reverse()){assert.equal(source.split(next).length-1,1);source=source.replace(next,old)}
 assert.equal(crypto.createHash('sha256').update(source).digest('hex'),patch.originalSha256)
})
test('Web 界面初始化不再引用不存在的 fcn 或安排第二次启动',()=>{
 const patch=require('./scratchjr-preview/vendor-patch.json');const init=patch.replacements[3][1].slice('key:"init",value:'.length)
 let inits=0,callback=0;vm.runInNewContext('('+init+')(function(){callback()})',{o:{default:{init(){inits++}}},s:null,callback(){callback++}});assert.equal(inits,1);assert.equal(callback,1)
 const wait=patch.replacements[4][1].slice('key:"waitForInterface",value:'.length);let started=0
 vm.runInNewContext('('+wait+')(function(){started()})',{g:null,s:{default:{init(){}}},started(){started++},setTimeout(){throw new Error('duplicate')}});assert.equal(started,1)
})

test('基线复现：ScratchJr 第二次封面回调混用上一轮项目编号',()=>{
 const {execFileSync}=require('node:child_process')
 const html=execFileSync('git',['show','45dd581:web/public/scratchjr/editor.html'],{encoding:'utf8'}),script=html.match(/<script>([\s\S]*?)<\/script>/)[1]
 const writes=[],uploads=[],ctx={console:{log(){}},setInterval(){},urlParams:()=>'',getUserToken:()=>'',getUserInfo:()=>({}),getQiniuToken(){},getSysConfig:()=> 'local',uuid:()=> 'uuid',uploadFile:key=>key,update2Local:(file,name,biz,cb)=>uploads.push({name,cb}),dataURLtoBlob:()=>({}),alert(){},$:{ajax:o=>writes.push(JSON.parse(o.data))}}
 ctx.window=ctx;ctx.ScratchJr={getProjectCover:cb=>cb('data:image/png;base64,')};vm.createContext(ctx);vm.runInContext(script,ctx)
 ctx.JrConfig.onSaveCloud({},'first');uploads[0].cb({success:true,message:'old.sjr'});uploads[1].cb({success:true,message:'old.png'});assert.equal(writes.length,1)
 ctx.JrConfig.onSaveCloud({},'second');uploads[3].cb({success:true,message:'new.png'});assert.equal(writes.length,2);assert.equal(writes[1].workFile,'old.sjr');assert.equal(writes[1].workCover,'new.png')
})
