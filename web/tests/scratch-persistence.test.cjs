const {test}=require('node:test'),assert=require('node:assert/strict')
const {create,query,pair}=require('../public/scratch3/persistence.js')
const flush=()=>new Promise(r=>setImmediate(r))
function harness(params={},overrides={}) {
 const h={opened:[],bodies:[],snapshots:[],saved:[],notices:[],title:'作品',revision:0}
 const options={params,notify:s=>h.notices.push(s),title:()=>h.title,
  info:async()=>({workType:2,workName:'已存作品',workFileKey_url:'/saved.sb3',additionalId:'task',departId:'class'}),
  unit:async()=>({unitName:'课程练习',courseWork_url:'/course.sb3'}),
  open:async(...a)=>h.opened.push(a),opened(){},saved:id=>h.saved.push(id),
  capture:async()=>({project:new Blob(['project '+(++h.revision)]),cover:new Blob(['cover '+h.revision]),hasCloudData:false}),
  upload:async(title,s)=>{h.snapshots.push(s);return {project:'p'+h.revision,cover:'c'+h.revision}},
  submit:async body=>{h.bodies.push(body);return {id:'owned'}},...overrides}
 h.options=options;h.session=create(options);return h
}
test('标准及旧链接只解码一次，保留百分号与 URL 自身的转义',()=>{
 let p=query('?'+new URLSearchParams({queryEncoding:'uri',workName:'练习 + 100%',workFile:'/a%20b.sb3?q=a+b&x=2'}))
 assert.equal(p.workName,'练习 + 100%');assert.equal(p.workFile,'/a%20b.sb3?q=a+b&x=2')
 assert.equal(query('?workName=100%').workName,'100%');assert.equal(query('?workName=%E4%BD%9C%E5%93%81').workName,'作品');assert.equal(query('?workFile=/a%20b.sb3').workFile,'/a%20b.sb3')
})
test('继续作业优先读取 ID，重做才使用模板，课程无文件时请求单元信息',async()=>{
 let h=harness({workId:'existing',workFile:'/template.sb3'});await h.session.load();assert.equal(h.opened[0][0],'/saved.sb3')
 h=harness({workId:'existing',workFile:'/template.sb3',resetTemplate:'1'});await h.session.load();assert.equal(h.opened[0][0],'/template.sb3');assert.equal(h.session.state.dirty,true);await h.session.save(0);assert.equal(h.bodies[0].id,'existing')
 h=harness({unitId:'unit'});await h.session.load();assert.equal(h.opened[0][0],'/course.sb3')
})
test('读取失败不以默认项目覆盖，解除忙状态但禁止保存，重试可恢复',async()=>{
 let fail=true;const h=harness({workId:'saved'},{info:async()=>{if(fail)throw new Error('503');return {workType:2,workFileKey_url:'/saved.sb3'}}})
 assert.equal(await h.session.load(),false);assert.equal(h.session.state.busy,false);assert.equal(h.session.state.ready,false);assert.equal(await h.session.save(1),false);assert.equal(h.opened.length,0)
 fail=false;assert.equal(await h.session.load(),true);assert.equal(h.session.state.ready,true)
})
test('连续保存每次使用新的文件对，非云作品也保留 ID、状态及任务绑定',async()=>{
 const h=harness({workId:'initial'});await h.session.load();await h.session.save(0);h.title='改名';await h.session.save(1)
 assert.deepEqual(h.bodies.map(b=>[b.id,b.workFile,b.workCover,b.workStatus]),[['initial','p1','c1',0],['owned','p2','c2',1]])
 assert.equal(h.bodies[1].workName,'改名');assert.equal(h.bodies[1].additionalId,'task');assert.equal(h.bodies[1].workScene,'additional');assert.deepEqual(h.saved,['owned','owned']);assert.equal(h.session.state.dirty,false)
})
test('慢上传期间再次点击不会捕获第二份快照；状态和标题固定',async()=>{
 let release;const h=harness({}, {upload:()=>new Promise(r=>release=r)});await h.session.load();const first=h.session.save(0);await flush();h.title='第二个标题';assert.equal(await h.session.save(1),false);assert.equal(h.revision,1)
 release({project:'p1',cover:'c1'});await first;assert.equal(h.bodies.length,1);assert.equal(h.bodies[0].workStatus,0);assert.equal(h.bodies[0].workName,'作品')
})
test('文件对等待全部结束，一方失败不会让另一方跨入下一次保存',async()=>{
 let release,finished=false;const p=pair(Promise.reject(new Error('cover failed')),new Promise(r=>release=r)).finally(()=>{finished=true});await flush();assert.equal(finished,false);release('late project');await assert.rejects(p,/cover failed/)
})
test('捕获、上传和业务失败均保留编辑内容并能重试；失败不更新 ID',async()=>{
 for(const boundary of ['capture','upload','submit']) {
  const h=harness();const original=h.options[boundary];let fail=true;h.options[boundary]=async(...args)=>{if(fail)throw new Error(boundary);return original(...args)}
  // create captures options by reference.
  await h.session.load();assert.equal(await h.session.save(1),false);assert.equal(h.session.state.busy,false);assert.equal(h.session.state.dirty,true);assert.equal(h.session.state.workId,'');assert.equal(h.session.state.ready,true)
  fail=false;assert.equal(await h.session.save(1),true);assert.equal(h.session.state.workId,'owned')
 }
})
test('空封面、缺失登记 ID、错误作品类型和缺失保存 ID不能假报成功',async()=>{
 for(const overrides of [{capture:async()=>({project:new Blob(['a']),cover:null})},{upload:async()=>({project:'a'})},{submit:async()=>({})}]) {const h=harness({},overrides);await h.session.load();assert.equal(await h.session.save(0),false);assert.equal(h.saved.length,0)}
 const h=harness({workId:'wrong'},{info:async()=>({workType:4,workFileKey_url:'/a.py'})});assert.equal(await h.session.load(),false);assert.equal(h.opened.length,0)
})
test('初始状态禁止保存，非法状态和空白或超长名称不上传',async()=>{
 const h=harness();assert.equal(await h.session.save(0),false);await h.session.load();assert.equal(await h.session.save(2),false)
 for(const title of ['', ' ', 'a'.repeat(65)]) {h.title=title;assert.equal(await h.session.save(1),false)}
 assert.equal(h.revision,0)
})

test('基线复现：旧页面第二次先上传封面，会携带上次项目 ID 提交',()=>{
 const {execFileSync}=require('node:child_process'),vm=require('node:vm')
 const source=execFileSync('git',['show','e772f02:web/public/scratch3/index.html'],{encoding:'utf8'}).match(/<script>([\s\S]*?)<\/script>/)[1]
 const writes=[],requests=[],ctx={console:{log(){}},setInterval(){},urlParams:()=>'',getUserInfo:()=>({}),getQiniuToken(){},getUserToken:()=>'',getSysConfig:()=> 'local',getFileAccessHttpUrl:()=>'',getLogo:()=>'',uuid:()=> 'uuid',uploadFile:key=>key,update2Local:(file,name,biz,cb)=>requests.push({name,cb}),alert(){}}
 ctx.$=()=>({show(){},hide(){},html(){}});ctx.$.ajax=o=>writes.push(JSON.parse(o.data));ctx.window=ctx;ctx.location={hostname:'fixture'};ctx.scratch={getProjectName:()=> 'name',getProjectCoverBlob:cb=>cb({}),getProjectFile:cb=>cb({})};ctx.vm={runtime:{hasCloudData:()=>false}}
 vm.createContext(ctx);vm.runInContext(source,ctx)
 ctx.requestUpload(0);requests[0].cb({success:true,message:'old.jpg'});requests[1].cb({success:true,message:'old.sb3'});assert.equal(writes.length,1)
 ctx.requestUpload(1);requests[2].cb({success:true,message:'new.jpg'})
 assert.equal(writes.length,2);assert.equal(writes[1].workCover,'new.jpg');assert.equal(writes[1].workFile,'old.sb3')
})

test('ScratchJr 使用独立类型与默认模板，不能打开 Scratch 项目后误覆盖',async()=>{
 const options={workType:3,acceptedTypes:['3'],defaultTitle:'ScratchJr 作品',defaultFile:'./project.sjr'}
 let h=harness({},options);await h.session.load();assert.deepEqual(h.opened[0],['./project.sjr','ScratchJr 作品']);await h.session.save(0);assert.equal(h.bodies[0].workType,3)
 h=harness({workId:'wrong'},options);assert.equal(await h.session.load(),false);assert.equal(h.opened.length,0)
 h=harness({workId:'owned',pmd5:'stale'}, {...options,info:async()=>({workType:3,workName:'SJR',workFileKey_url:'/saved.sjr',courseId:'unit'})});await h.session.load();await h.session.save(1);assert.equal(h.opened[0][0],'/saved.sjr');assert.equal(h.bodies[0].courseId,'unit');assert.equal(h.bodies[0].workScene,'course')
})
