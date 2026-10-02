const {test}=require('node:test'),assert=require('node:assert/strict'),vmLib=require('node:vm'),fs=require('node:fs'),path=require('node:path')
const persistence=require('../public/scratch3/persistence.js'),flush=()=>new Promise(r=>setImmediate(r))
async function mount(overrides={}) {
 const h={calls:[],cloud:[],reads:[],history:[],events:{},cloudIds:[],title:'作品',token:'session-a',capture:0,stops:0,nodes:{}}
 for(const id of ['persistence-status','retry-load','save-draft','submit-work','scratch','editor-unavailable'])h.nodes[id]={dataset:{},setAttribute(){},addEventListener:(event,fn)=>{h.events[event]=fn}}
 const engine={on:(event,fn)=>{h.events[event]=fn},stopAll:()=>h.stops++,loadProject:async bytes=>{h.reads.push(bytes);if(overrides.invalidProject)throw new Error('zip')},saveProjectSb3:async()=>{h.capture++;return new Blob(['project'])},runtime:{hasCloudData:()=>false},renderer:{draw(){},canvas:{toBlob:cb=>cb(overrides.noCover?null:new Blob(['png']))}}}
 class XHR {open(method,url){h.fileRequest={method,url}}send(){this.status=overrides.fileStatus||200;this.response=new Uint8Array([80,75]).buffer;this.onload()}getResponseHeader(){return overrides.mime||'application/octet-stream'}}
 const context={URL,URLSearchParams,Blob,FormData,Promise,setTimeout,clearTimeout,XMLHttpRequest:XHR,ScratchPersistence:persistence,document:{getElementById:id=>h.nodes[id]},location:{search:'?workId=owned',href:'http://fixture.test/scratch3/index.html?workId=owned'},history:{replaceState:(s,t,url)=>h.history.push(url)},getUserToken:()=>h.token,uuid:()=> 'fixture-uuid',scratch:{getProjectName:()=>h.title,setProjectName:title=>{h.title=title},setCloudId:id=>h.cloudIds.push(id)},qiniu:{region:{z0:{}},upload:(...args)=>{h.cloud.push(args);return {subscribe:observer=>{if(overrides.cloudError)observer.error({});else observer.complete({key:args[1]});return {unsubscribe(){}}}}}},$: {ajax:o=>{
  h.calls.push(o);const response=overrides.response&&overrides.response(o)
  if(response==='401'){o.error({status:401});return}if(response!==undefined){o.success(response);return}
  if(o.url.includes('studentWorkInfo'))o.success({code:0,success:true,result:{id:'owned',workType:2,workName:'作品',workFileKey_url:'http://files.test/project.sb3'}})
  else if(o.url.includes('getCurrentConfig'))o.success({code:0,result:{uploadType:overrides.cloud?'qiniu':'local',qiniuArea:'z0'}})
  else if(o.url.includes('getToken'))o.success({code:200,success:true,result:'short-cloud-token',keyPrefix:'server-owned/'})
  else if(o.url.endsWith('/upload'))o.success({success:true,message:'project3/'+o.data.get('file').name})
  else if(o.url.endsWith('/add')){const body=JSON.parse(o.data);o.success({success:true,result:{id:body.fileName.endsWith('.sb3')?'project-id':'cover-id',filePath:body.filePath}})}
  else if(o.url.endsWith('/submit'))o.success({code:200,success:true,result:{id:'owned'}})
  else throw new Error('Unexpected '+o.url)
 }}}
 context.window=context;vmLib.createContext(context);vmLib.runInContext(fs.readFileSync(path.join(__dirname,'../public/scratch3/editor-bridge.js'),'utf8'),context);context.TeachingScratch.initialize(engine);context.TeachingScratch.start();await flush()
 h.context=context;return h
}
function body(h){return JSON.parse(h.calls.find(o=>o.url.endsWith('/submit')).data)}
test('没有 CONFIG 缓存仍能从原生 VM 生成 SB3/PNG，登记成对 ID 并保存',async()=>{
 const h=await mount();h.token='session-b';await h.nodes['save-draft'].onclick();await flush()
 assert.equal(h.capture,1);assert.equal(h.stops,1);assert.equal(body(h).workFile,'project-id');assert.equal(body(h).workCover,'cover-id');assert.equal(body(h).workStatus,0)
 const transfers=h.calls.filter(o=>o.url.endsWith('/upload'));assert.equal(transfers.length,2);assert.equal(transfers[1].data.get('file').name,'作品.png')
 for(const r of h.calls.filter(o=>o.type==='POST'))assert.equal(r.headers['X-Access-Token'],'session-b')
 assert.equal(h.fileRequest.url,'http://files.test/project.sb3');assert.equal('headers' in h.fileRequest,false);assert.match(h.history[0],/workId=owned/);assert.deepEqual(h.cloudIds,['owned','owned']);assert.equal(h.nodes.scratch.inert,false)
})
test('HTTP 错误、HTML 伪文件与无效项目都阻止编辑并保留重试入口',async()=>{
 for(const overrides of [{fileStatus:403},{mime:'text/html'},{invalidProject:true}]) {
  const h=await mount(overrides);assert.equal(h.nodes.scratch.inert,true);assert.equal(h.nodes['save-draft'].disabled,true);assert.equal(h.nodes['retry-load'].hidden,false);assert.match(h.nodes['persistence-status'].textContent,/未能打开/)
 }
})
test('封面生成失败、登记不匹配或上传 401 不提交且保留编辑能力',async()=>{
 for(const overrides of [{noCover:true},{response:o=>o.url.endsWith('/add')?{success:true,result:{id:'wrong',filePath:'elsewhere'}}:undefined},{response:o=>o.url.endsWith('/upload')?'401':undefined}]){
  const h=await mount(overrides);h.nodes['submit-work'].onclick();await flush();assert.equal(h.calls.some(o=>o.url.endsWith('/submit')),false);assert.equal(h.nodes.scratch.inert,false);assert.equal(h.nodes['submit-work'].disabled,false);assert.match(h.nodes['persistence-status'].textContent,/保存未完成/)
 }
})
test('模拟七牛使用同一组唯一前缀但不同扩展名，不传平台令牌',async()=>{
 const h=await mount({cloud:true});h.nodes['submit-work'].onclick();await flush();assert.equal(h.cloud.length,2)
 assert.deepEqual(h.cloud.map(a=>a[1]),['server-owned/project3/fixture-uuid.sb3','server-owned/project3/fixture-uuid.png'])
 for(const a of h.cloud){assert.equal(a[2],'short-cloud-token');assert.equal(JSON.stringify(a).includes('session-a'),false)}
 assert.equal(body(h).workFile,'project-id');assert.equal(body(h).workCover,'cover-id');assert.equal(h.calls.filter(o=>o.url.endsWith('/add')).every(o=>JSON.parse(o.data).fileLocation===2),true)
})
test('云上传报错解除忙状态，禁止提交未登记的一对文件',async()=>{
 const h=await mount({cloud:true,cloudError:true});h.nodes['submit-work'].onclick();await flush();assert.equal(h.calls.some(o=>o.url.endsWith('/submit')),false);assert.equal(h.nodes.scratch.inert,false)
})
test('实际 VM 的项目变化和标题输入触发未保存提示；成功保存后清除离页提示',async()=>{
 const h=await mount();let prevented=0;const e={preventDefault:()=>prevented++}
 h.context.onbeforeunload(e);assert.equal(prevented,0);h.events.PROJECT_CHANGED();h.context.onbeforeunload(e);assert.equal(prevented,1)
 h.nodes['save-draft'].onclick();await flush();h.context.onbeforeunload(e);assert.equal(prevented,1)
 h.events.input();h.context.onbeforeunload(e);assert.equal(prevented,2)
})
