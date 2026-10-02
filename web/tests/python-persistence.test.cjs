const assert = require('node:assert/strict')
const { test } = require('node:test')
const vm = require('node:vm')
const { execFileSync } = require('node:child_process')
const { create, query } = require('../public/python/persistence.js')
const deferred = () => { let resolve, reject; const promise = new Promise((a,b) => { resolve=a; reject=b }); return { promise, resolve, reject } }
function harness(params = {}) {
  const h = { events: [], uploads: [], writes: [], applied: [], saved: [], reads: [] }
  h.options = { params, notify: s => h.events.push(s), apply: (...a) => h.applied.push(a), saved: id => h.saved.push(id),
    info: async id => ({ id, workType:'4', workName:'已保存 & 100%', workFileKey_url:'/saved.py?a=1&b=2', courseId:'unit-saved', departId:'saved-class' }),
    text: async url => { h.reads.push(url); return 'print(42)' }, upload: async (title,code) => { h.uploads.push({title,code}); return {id:'file-'+h.uploads.length} },
    submit: async body => { h.writes.push(body); return {id:body.id||'saved-work'} } }
  h.session=create(h.options);return h
}
test('基线复现：旧桥接保存成功后不记住 ID，第二次改名保存仍是新建请求', () => {
  const src=execFileSync('git',['show','7ab1dd5:web/public/python/index.html'],{encoding:'utf8'}).match(/<script>([\s\S]*?)<\/script>/)[1]
  const writes=[];const ctx={Blob,console:{log(){}},setInterval(){},urlParams:()=>'',getUserToken:()=>null,getUserInfo:()=>({}),getQiniuToken(){},getSysConfig:()=> 'local',alert(){},uploadFile:()=> 'file',update2Local:(f,n,p,cb)=>cb({success:true,message:'fixture/file.py'}),$: {ajax:o=>{writes.push(JSON.parse(o.data));o.success({code:200,result:{id:'created-id'}})}}}
  ctx.window=ctx;ctx.uuid=()=> 'uuid';vm.createContext(ctx);vm.runInContext(src,ctx);ctx.submitCode('first','print(1)');ctx.submitCode('renamed','print(2)')
  assert.equal(writes.length,2);assert.equal(writes[0].id,'');assert.equal(writes[1].id,'');assert.equal(ctx.workId,'')
})
test('新链接完整往返名称、中文、百分号和查询地址；旧裸文件链接兼容', () => {
  const input={queryEncoding:'uri',workName:'中文 & 100% + #',workFile:'/file.py?a=x+y&b=20%25'},result=query('?'+new URLSearchParams(input))
  assert.equal(result.workName,input.workName);assert.equal(result.workFile,input.workFile);assert.equal(query('?workName=100%&workFile=/file%20name.py').workName,'100%');assert.equal(query('?workFile=/file%20name.py').workFile,'/file%20name.py');assert.equal(query('?workFile=undefined').workFile,'')
})
test('已有作品只加载一个目标，并从记录恢复课程和班级归属', async () => {
  const h=harness({workId:'existing',workFile:'/template.py'});await h.session.load();assert.deepEqual(h.reads,['/saved.py?a=1&b=2']);assert.deepEqual(h.applied,[['已保存 & 100%','print(42)']])
  await h.session.save('名称','print(2)');assert.equal(h.writes[0].id,'existing');assert.equal(h.writes[0].courseId,'unit-saved');assert.equal(h.writes[0].departId,'saved-class')
})
test('课程 url 与作业 workFile 均加载；重做读取模板但更新原作品 ID', async () => {
  for(const params of [{url:'/course.py'},{workFile:'/task.py'},{workId:'existing',resetTemplate:'1',workFile:'/template.py'}]) { const h=harness(params);await h.session.load();assert.equal(h.reads[0],params.workFile||params.url);await h.session.save('作品','print(2)');assert.equal(h.writes[0].id,params.workId||'') }
})
test('慢速或失败读取禁止保存、不会回退默认示例，恢复后可以重试', async () => {
  const h=harness({workId:'existing'}),wait=deferred();h.options.text=()=>wait.promise;const load=h.session.load()
  assert.equal(await h.session.save('a','x'),false);assert.equal(await h.session.load(),false);wait.reject(new Error('503'));await load
  assert.equal(h.session.state.ready,false);assert.equal(h.applied.length,0);assert.equal(h.writes.length,0);assert.equal(h.session.state.phase,'load-error')
  h.options.text=async()=> 'restored';await h.session.load();assert.equal(h.applied[0][1],'restored')
})
test('保存锁覆盖上传到提交，连续点击只使用固定的一次快照', async () => {
  const h=harness(),wait=deferred();await h.session.load();h.options.upload=async(title,code)=>{h.uploads.push({title,code});return wait.promise}
  const save=h.session.save('第一次','print(1)');assert.equal(await h.session.save('第二次','print(2)'),false);assert.equal(h.uploads.length,1)
  wait.resolve({id:'new-file'});await save;assert.equal(h.writes.length,1);assert.equal(h.writes[0].workName,'第一次');assert.equal(h.writes[0].workFile,'new-file');assert.equal(h.session.state.busy,false)
})
test('成功后改名与修改代码仍使用返回 ID，默认场景为 create', async () => {
  const h=harness();await h.session.load();await h.session.save('first','one');await h.session.save('renamed','two')
  assert.equal(h.writes[0].id,'');assert.equal(h.writes[1].id,'saved-work');assert.equal(h.writes[1].workFile,'file-2');assert.equal(h.writes[1].workScene,'create');assert.deepEqual(h.saved,['saved-work','saved-work'])
})
test('上传或登记失败均不提交；重试只使用成功文件', async () => {
  const h=harness();await h.session.load();h.options.upload=async()=>{throw new Error('upload failure')};await h.session.save('name','code');assert.equal(h.writes.length,0)
  h.options.upload=async()=>({});await h.session.save('name','code');assert.equal(h.writes.length,0)
  h.options.upload=async()=>({id:'good'});await h.session.save('name','code');assert.equal(h.writes[0].workFile,'good')
})
test('提交失败保留 ID；未改动重试复用文件，改变快照重新上传', async () => {
  const h=harness({workId:'existing'});await h.session.load();h.options.submit=async()=>{throw new Error('503')};await h.session.save('name','code')
  assert.equal(h.session.state.workId,'existing');assert.equal(h.session.state.ready,true);assert.equal(h.session.state.phase,'save-error')
  h.options.submit=async body=>{h.writes.push(body);return {id:'existing'}};await h.session.save('name','code');assert.equal(h.uploads.length,1)
  await h.session.save('name','changed');assert.equal(h.uploads.length,2);assert.equal(h.writes[1].workFile,'file-2')
})
test('空代码和非法名称不上传；缺少结果 ID 不能宣称成功', async () => {
  const h=harness();await h.session.load();for(const [title,code] of [['','x'],['x','  '],['x'.repeat(65),'x']])assert.equal(await h.session.save(title,code),false)
  assert.equal(h.uploads.length,0);h.options.submit=async()=>({});await h.session.save('x','code');assert.equal(h.saved.length,0);assert.equal(h.session.state.phase,'save-error')
})
test('未知或不完整作品不能降级为可保存的空编辑器', async () => {
  for(const info of [null,{workType:2,workFileKey_url:'/x'},{workType:4}]){const h=harness({workId:'existing'});h.options.info=async()=>info;await h.session.load();assert.equal(h.session.state.ready,false);assert.equal(h.applied.length,0)}
})
