const { test } = require('node:test')
const assert = require('node:assert/strict')
const vm = require('node:vm')
const fs = require('node:fs')
const path = require('node:path')
const cp = require('node:child_process')
const base = path.resolve(__dirname, '..')
const flush = () => new Promise(resolve => setImmediate(resolve))
function mount (file, old = false) {
  const text = old ? cp.execFileSync('git', ['show', '193b8bfb349e7b2aa40d51f145b54b07e48ca236:web/src/views/teaching/' + file], { cwd: base, encoding: 'utf8' }) : fs.readFileSync(path.join(base, 'src/views/teaching', file), 'utf8')
  const calls = [], events = [], notices = [], confirms = [], opened = []
  const request = method => (url, data) => new Promise((resolve, reject) => calls.push({ method, url, data, resolve, reject }))
  const context = { component: null, URL, URLSearchParams, Blob, Uint8Array, setTimeout, window: { location: { origin: 'http://local.test' }, open: (...args) => opened.push(args) }, console: { log () {} }, TeachingWorkModal: {}, TeachingWorkPreviewModal: {}, SelectUserModal: {}, JDictSelectTag: {}, QrCode: {}, TeachingWorkCorrectForm: {}, getAction: request('GET'), postAction: request('POST'), putAction: request('PUT'), deleteAction: request('DELETE'), downFile: request('DOWNLOAD') }
  vm.createContext(context); vm.runInContext(text.match(/<script>([\s\S]*?)<\/script>/)[1].replace(/^\s*import [^\n]*$/gm, '').replace('export default', 'component ='), context)
  const c = context.component
  const form = { createForm: () => ({ validateFields: callback => callback(null, { score: 0, comment: '' }) }) }
  const i = { ...c.data.call({ $form: form }), $route: { query: {} }, $emit: (...args) => events.push(args), $message: { success: s => notices.push(s) }, $confirm: value => confirms.push(value), $set: (o, k, v) => { o[k] = v }, $refs: { selectUserModal: { visible: false }, modalForm: { edit: () => {} }, previewModal: { previewCode: () => {} } } }
  for (const [key, fn] of Object.entries(c.methods)) i[key] = fn.bind(i)
  for (const [key, fn] of Object.entries(c.computed || {})) Object.defineProperty(i, key, { get: () => fn.call(i) })
  return { c, i, calls, events, notices, confirms, opened }
}
const row = { id: 'work-a', workName: '观察记录', workStatus: '1', userId: 'student', workFile: 'file', workType: '0' }
async function ready (h, feedback = [], record = row) {
  h.i.edit(record)
  const calls = h.calls.filter(c => c.method === 'GET')
  calls.at(-3).resolve({ success: true, result: [{ id: 'comment', comment: '学生讨论' }] })
  calls.at(-2).resolve({ success: true, result: record })
  calls.at(-1).resolve({ success: true, result: feedback })
  await flush(); assert.equal(h.i.ready, true)
}
const modal = () => mount('modules/TeachingWorkModal.vue')
const list = () => mount('TeachingWorkList.vue')
test('旧表单实际复现：0 分且评语为空时被序列化为空列表', () => {
  const h = mount('modules/TeachingWorkCorrectForm.vue', true)
  assert.equal(h.i.getFormData().length, 0)
})
test('读取未完成或失败不能保存，重新读取可以恢复', async () => {
  const h = modal(); h.i.edit(row); await h.i.handleOk(); assert.equal(h.calls.length, 3)
  h.calls[0].resolve({success:true,result:[]}); h.calls[1].resolve({success:true,result:row}); h.calls[2].reject(new Error('network')); await flush()
  assert.equal(h.i.loading, false); assert.equal(h.i.ready, false); assert.ok(h.i.loadError); await h.i.handleOk(); assert.equal(h.calls.length, 3)
  await ready(h); assert.equal(h.i.feedback.score, null)
})
test('零分实际提交，忽略列表受保护字段与已读取讨论，保存只发送一次', async () => {
  const h = modal(); await ready(h); h.i.feedback.score = 0
  const pending = h.i.handleOk(); h.i.handleOk(); h.i.handleCancel(); h.i.edit({id:'other'})
  const call = h.calls.at(-1); assert.equal(call.method, 'PUT'); assert.equal(call.data.id, row.id); assert.equal(call.data.teachingWorkCorrectList[0].score, 0)
  assert.deepEqual(Object.keys(call.data).sort(), ['id','teachingWorkCorrectList','workName','workStatus']); assert.equal(call.data.workStatus, '2'); assert.equal(h.calls.length,4); assert.equal(h.i.visible,true)
  call.resolve({success:true}); await pending; assert.equal(h.i.visible,false); assert.equal(h.i.saving,false); assert.equal(h.notices.length,1); assert.equal(h.events.filter(v=>v[0]==='ok').length,1)
})
test('只有评语可以保存，改一个评分时保留额外反馈与第一条 ID', async () => {
  const h=modal();await ready(h,[{id:'first',score:2,comment:'原反馈',createTime:'fixed'},{id:'second',score:4,comment:'其他反馈'}]);h.i.feedback={score:null,comment:'请补充实验步骤'}
  const done=h.i.handleOk(),body=h.calls.at(-1).data;assert.equal(body.teachingWorkCorrectList[0].id,'first');assert.equal(body.teachingWorkCorrectList[0].score,null);assert.equal(body.teachingWorkCorrectList[1].id,'second');assert.equal(body.teachingWorkCommentList,undefined)
  h.calls.at(-1).resolve({success:true});await done
})
test('仅改作品信息不重发评分；清空已有反馈时显式提交空列表', async () => {
  const h=modal();await ready(h,[{id:'grade',score:3,comment:''}],{...row,workStatus:'0'});h.i.workName='新名称'
  let done=h.i.handleOk();assert.equal(h.calls.at(-1).data.teachingWorkCorrectList,undefined);h.calls.at(-1).resolve({success:true});await done
  await ready(h,[{id:'grade',score:3,comment:''}],{...row,workStatus:'0'});h.i.feedback.score=null;done=h.i.handleOk();assert.equal(h.calls.at(-1).data.teachingWorkCorrectList.length,0);h.calls.at(-1).resolve({success:true});await done
})
test('网络和业务失败保留输入，不显示成功、不关弹窗；再次保存可成功', async () => {
  const h=modal();await ready(h);h.i.feedback={score:0,comment:'我的评语'}
  for (const fail of ['network','business']) { const done=h.i.handleOk();if(fail==='network')h.calls.at(-1).reject(new Error('network'));else h.calls.at(-1).resolve({success:false,message:'SQL secret'});await done;assert.equal(h.i.visible,true);assert.equal(h.i.saving,false);assert.equal(h.i.feedback.score,0);assert.equal(h.i.feedback.comment,'我的评语');assert.ok(h.i.saveError);assert.doesNotMatch(h.i.saveError,/SQL/);assert.equal(h.notices.length,0) }
  const done=h.i.handleOk();h.calls.at(-1).resolve({success:true});await done;assert.equal(h.notices.length,1)
})
test('切换作品、关闭或销毁后，迟到读取不能填入新弹窗', async () => {
  const h=modal();h.i.edit(row);const old=h.calls.slice();await ready(h,[],{...row,id:'b',workName:'第二份'});old[0].resolve({success:true,result:[{comment:'旧讨论'}]});old[1].resolve({success:true,result:row});old[2].resolve({success:true,result:[{score:5,comment:'旧反馈'}]});await flush();assert.equal(h.i.record.id,'b');assert.equal(h.i.feedback.score,null)
  h.i.edit(row);h.i.close();h.calls.at(-3).resolve({success:true,result:[]});h.calls.at(-2).resolve({success:true,result:row});h.calls.at(-1).resolve({success:true,result:[]});await flush();assert.equal(h.i.ready,false)
  h.i.edit(row);h.c.beforeDestroy.call(h.i);h.calls.at(-3).resolve({success:true,result:[]});h.calls.at(-2).resolve({success:true,result:row});h.calls.at(-1).resolve({success:true,result:[]});await flush();assert.equal(h.i.ready,false)
})
test('讨论失败可单独重试，保存不依赖旧讨论快照', async () => {
  const h=modal();h.i.edit(row);h.calls[0].reject(new Error('comments failed'));h.calls[1].resolve({success:true,result:row});h.calls[2].resolve({success:true,result:[]});await flush();assert.equal(h.i.ready,true);assert.equal(h.i.commentsError,true)
  const done=h.i.loadComments();h.calls.at(-1).resolve({success:true,result:[]});await done;assert.equal(h.i.commentsError,false)
})
test('无效评分、名称和状态不提交；未保存退出需要明确放弃', async () => {
  const h=modal();await ready(h)
  for(const score of [-1,6,1.5,NaN,'0']){h.i.feedback.score=score;await h.i.handleOk();assert.equal(h.calls.length,3)}
  h.i.feedback.score=0;for(const name of [' ','字'.repeat(65)]){h.i.workName=name;await h.i.handleOk();assert.equal(h.calls.length,3)}
  h.i.workName='记录';h.i.workStatus='unknown';await h.i.handleOk();assert.equal(h.calls.length,3);h.i.handleCancel();assert.equal(h.confirms.length,1);assert.equal(h.i.visible,true);h.confirms[0].onOk();assert.equal(h.i.visible,false)
})
test('列表状态使用真实参数，未提交的搜索不随状态切换生效', async () => {
  const h=list();h.i.queryParam.workName='未提交';h.i.chooseStatus('2');assert.equal(h.calls[0].data.workStatus,'2');assert.equal(h.calls[0].data.workName,undefined);assert.equal(h.calls[0].data.pageNo,1)
  h.calls[0].resolve({success:true,result:{records:[],total:0}});await flush();const done=h.i.searchQuery();assert.equal(h.calls[1].data.workName,'未提交');h.calls[1].resolve({success:true,result:{records:[],total:0}});await done
})
test('旧列表响应不能覆盖新筛选，拒绝和畸形响应有恢复状态', async () => {
  const h=list();let done=h.i.loadData();h.calls[0].reject(new Error('offline'));await done;assert.equal(h.i.loading,false);assert.ok(h.i.listError)
  const older=h.i.loadData();const newer=h.i.chooseStatus('');h.calls[2].resolve({success:true,result:{records:[row],total:1}});await newer;h.calls[1].resolve({success:true,result:{records:[{...row,id:'old'}],total:99}});await older;assert.equal(h.i.total,1);assert.equal(h.i.dataSource[0].id,row.id)
  for(const result of [null,{}, {records:[null],total:1}, {records:[],total:'bad'}]){done=h.i.loadData();h.calls.at(-1).resolve({success:true,result});await done;assert.ok(h.i.listError);assert.equal(h.i.dataSource.length,0)}
})
test('删除末页后回退有效页，翻页清空选择；销毁后不接受响应', async () => {
  const h=list();h.i.page=2;h.i.selectedRowKeys=['old'];const done=h.i.loadData();assert.equal(h.i.selectedRowKeys.length,0);h.calls[0].resolve({success:true,result:{records:[],total:3}});await flush();assert.equal(h.i.page,1);assert.equal(h.calls[1].data.pageNo,1);h.calls[1].resolve({success:true,result:{records:[row],total:3}});await done;assert.equal(h.i.loading,false)
  const late=h.i.loadData();h.c.beforeDestroy.call(h.i);h.calls.at(-1).resolve({success:true,result:{records:[],total:0}});await late;assert.equal(h.i.total,3)
})
test('标签草稿按作品重置，失败保留输入，重复点击不重复写入', async () => {
  const h=list();h.i.openTag({...row,workTag:'A'});h.i.tagValue='修改';h.i.openTag({...row,id:'b',workTag:'B'});assert.equal(h.i.tagValue,'B')
  const done=h.i.saveTag();h.i.saveTag();assert.equal(h.calls.length,1);h.calls[0].resolve({success:false});await done;assert.equal(h.i.tagRecord.id,'b');assert.equal(h.i.tagValue,'B');assert.ok(h.i.tagError);assert.equal(h.i.actionBusy,'')
})
test('导出只使用已生效条件，姓名和标签筛选要求选中，JSON 错误不能伪装 Excel', async () => {
  const h=list();h.i.applied.realname='学生';await h.i.exportWorks();assert.equal(h.calls.length,0)
  h.i.selectedRowKeys=[row.id];h.i.queryParam.workName='草稿条件';const done=h.i.exportWorks();const req=h.calls.at(-1);assert.equal(req.data.selections,row.id);assert.equal(req.data.workName,undefined);assert.equal(req.data.realname,undefined);req.resolve(new Blob(['{"success":false}']));await done;assert.ok(h.i.actionError);assert.equal(h.i.actionBusy,'')
})
test('预览编码完整查询参数，拒绝可执行 URL，关闭不假设 Scratch VM 存在', () => {
  const h=mount('modules/TeachingWorkPreviewModal.vue');for(const type of ['0','4','3']){h.i.previewCode({...row,workType:type,workFileKey_url:'javascript:alert(1)'});assert.equal(h.i.frameHref,'');assert.equal(h.i.fileUrl,'');h.i.close();assert.equal(h.i.visible,false)}
  const file='https://files.test/report.py?name=a+b&x=2';h.i.previewCode({...row,workType:4,workFileKey_url:file});assert.equal(new URL(h.i.frameHref,'http://local').searchParams.get('url'),file)
  h.i.previewCode({...row,id:'a&b',workType:2});assert.equal(new URL(h.i.frameHref,'http://local').searchParams.get('workId'),'a&b');h.i.close();assert.equal(h.i.frameHref,'')
})
test('打开作品保留既有编辑器入口并隔离新窗口 opener；缺图不再重试原地址', () => {
  const h=list();const file='/work.sjr?x=a+b&n=2';h.i.handleView({...row,workType:3,workFileKey_url:file});assert.equal(new URL(h.opened[0][0]).searchParams.get('workFile'),file);assert.equal(h.opened[0][2],'noopener,noreferrer')
  h.i.download('data:text/html,evil');assert.equal(h.opened.length,1);assert.ok(h.i.actionError);const image={...row,coverFileKey_url:'/bad.png'};assert.ok(h.i.coverUrl(image));h.i.brokenCovers[row.id]=true;assert.equal(h.i.coverUrl(image),'')
})

// Match the persisted 512-character comment contract and exact-name export endpoint.
test('oversized feedback is retained locally instead of sending an invalid save', async () => {
  const h = modal(); await ready(h); const count = h.calls.length; h.i.feedback = {score: 0, comment: '评'.repeat(513)}
  await h.i.handleOk(); assert.equal(h.calls.length, count); assert.match(h.i.saveError, /512/); assert.equal(h.i.feedback.comment.length, 513)
})
test('fuzzy-name export requires selected results and omits the incompatible exact-name filter', async () => {
  const h = list(); h.i.applied.workName = '部分名称'; await h.i.exportWorks(); assert.equal(h.calls.length, 0); assert.match(h.i.actionError, /先选择/)
  h.i.selectedRowKeys = [row.id]; const done = h.i.exportWorks(); const req = h.calls.at(-1); assert.equal(req.data.selections, row.id); assert.equal(req.data.workName, undefined)
  req.resolve(new Blob(['{}'])); await done
})
