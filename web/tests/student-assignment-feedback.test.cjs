const assert = require('node:assert/strict')
const { test } = require('node:test')
const { readFileSync } = require('node:fs')
const { resolve } = require('node:path')
const vm = require('node:vm')
const flush = () => new Promise(resolve => setImmediate(resolve))
function mount () {
  const source = readFileSync(resolve(__dirname, '../src/views/account/course/MyAdditionalWorkList.vue'), 'utf8')
  const requests = []; const opened = []; const files = []
  const ctx = { component: null, URL, URLSearchParams, TeachingWorkSubmitModal: {}, window: { location: { origin: 'http://local.test' }, open: (...args) => opened.push(args) }, getFilePrevew: value => { if (value === '/broken.doc') throw new Error('broken-config'); return value }, getAction: (url, params) => new Promise((resolve, reject) => requests.push({ url, params, resolve, reject })) }
  vm.createContext(ctx); vm.runInContext(source.match(/<script>([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm, '').replace('export default', 'component ='), ctx)
  const c = ctx.component; const i = { ...c.data(), $refs: { submitModal: { open: value => files.push(value) } }, $set: (o, k, v) => { o[k] = v } }
  for (const [k,v] of Object.entries(c.methods)) i[k] = v.bind(i)
  for (const [k,v] of Object.entries(c.computed)) Object.defineProperty(i,k,{ get: () => v.call(i) })
  return { i, c, requests, opened, files }
}
const work = { additionalWorkId:'task', departId:'class', codeType:0, workName:'任务' }
test('零分与只有评语的反馈仍然可见，缺失分数不伪装成零分', () => {
  const { i } = mount()
  for (const score of [0, '0', 4]) { assert.equal(i.hasScore({ score }), true); assert.equal(i.hasFeedback({ score }), true) }
  for (const score of [null, undefined, '', ' ', 'bad']) assert.equal(i.hasScore({ score }), false)
  assert.equal(i.hasFeedback({ comment:'请补充实验记录' }), true)
  assert.equal(i.hasFeedback({ mineWorkId:'a', mineWorkStatus:2 }), true)
  assert.equal(i.hasFeedback({ mineWorkId:'a', mineWorkStatus:0 }), false)
})
test('草稿、待批改、批改和公开状态遵循实际字典；未知状态不能修改', () => {
  const { i } = mount()
  assert.equal(i.statusInfo(work).label, '未开始'); assert.equal(i.canEdit(work), true)
  const labels = ['已保存草稿', '已提交 · 待批改', '已批改', '已公开展示', '精选作品']
  for (let status=0; status<5; status++) {
    const row = { ...work, mineWorkId:'saved', mineWorkStatus:String(status) }
    assert.equal(i.statusInfo(row).label, labels[status]); assert.equal(i.canEdit(row), status<2)
  }
  for (const status of [undefined,null,'',-1,5]) assert.equal(i.canEdit({ ...work, mineWorkId:'saved', mineWorkStatus:status }), false)
  assert.equal(i.canEdit({ ...work, departId:'' }), false)
})
test('切换提交筛选使用真实参数且回到首页，当前筛选和非法筛选不重复请求', async () => {
  const h = mount(); h.i.page=2; h.i.handleChangeStatus('true'); assert.equal(h.requests[0].params.submit,'true'); assert.equal(h.requests[0].params.pageSize,undefined); assert.equal(h.i.page,1)
  h.i.handleChangeStatus('true'); h.i.handleChangeStatus('bad'); assert.equal(h.requests.length,1)
  h.requests[0].resolve({ success:true, result:[] }); await flush(); assert.equal(h.i.emptyTitle,'还没有已提交的作业')
  h.i.handleChangeStatus(''); assert.equal(h.requests[1].params.submit,'')
})
test('数组响应的本地分页不会遗漏末页，也不会越过边界', async () => {
  const h=mount(); const done=h.i.getList(); h.requests[0].resolve({success:true,result:Array.from({length:10},(_,n)=>({...work,additionalWorkId:String(n)}))}); await done
  assert.equal(h.i.visibleWorks.length,8); assert.equal(h.i.totalPages,2); h.i.changePage(2); assert.deepEqual(Array.from(h.i.visibleWorks,w=>w.additionalWorkId),['8','9']); h.i.changePage(3); assert.equal(h.i.page,2); h.i.changePage(0); assert.equal(h.i.page,2)
})
test('无效列表与网络失败分别进入错误状态，空列表正常；销毁后的响应无效', async () => {
  for(const result of [null,{},[null],[[]]]) { const h=mount(); const done=h.i.getList(); h.requests[0].resolve({success:true,result}); await done; assert.equal(h.i.listError,true); assert.equal(h.i.loading,false) }
  const h=mount(); const done=h.i.getList(); h.c.beforeDestroy.call(h.i); h.requests[0].resolve({success:true,result:[work]}); await done; assert.equal(h.i.datasource.length,0)
})
test('说明保留段落且不执行富文本，缺失图片回退不重复请求原图', () => {
  const { i } = mount(); assert.equal(i.description({ workDesc:'<p>第一段</p><p>第二段<br>第三行</p><script>x()</script>' }),'第一段\n第二段\n第三行')
  const row={...work,workCover_url:'/cover.jpg'}; assert.equal(i.coverUrl(row),'http://local.test/cover.jpg'); i.coverFailed(row); assert.equal(i.coverUrl(row),'')
})
test('资料拒绝可执行协议、配置失败能展示错误；新窗口隔离 opener', () => {
  const h=mount()
  for(const workDocumentUrl of ['javascript:alert(1)','data:text/html,x','/broken.doc']) { h.i.openWorkFile({...work,workDocumentUrl}); assert.equal(h.i.actionError,h.i.rowKey(work)) }
  assert.equal(h.opened.length,0); h.i.openWorkFile({...work,workDocumentUrl:'/notes.PDF?x=1&y=2'}); assert.equal(h.i.actionError,''); assert.equal(h.opened[0][0],'http://local.test/notes.PDF?x=1&y=2'); assert.equal(h.opened[0][2],'noopener,noreferrer')
  assert.equal(h.i.submittedUrl({mineWorkId:'a',mineWorkUrl:'javascript:alert(1)'}),'')
})
test('文件作业继续提交保留作品 ID 和名称，重做保留更新目标且不可修改已批改作品', () => {
  const h=mount(); const row={...work,mineWorkId:'saved',mineWorkStatus:1,mineWorkName:'我的观察'}
  h.i.toAdditionalWork(row,false); assert.equal(h.files[0].id,'saved'); assert.equal(h.files[0].workName,'我的观察'); assert.equal(h.files[0].additionalId,'task')
  h.i.toAdditionalWork(row,true); assert.equal(h.files[1].id,'saved'); assert.equal(h.files[1].workName,'任务')
  h.i.toAdditionalWork({...row,mineWorkStatus:2},false); assert.equal(h.files.length,2)
})

test('Python 继续与重做均保留 ID；名称和模板查询参数完整往返', () => {
  const h=mount(),row={...work,codeType:4,mineWorkId:'saved',mineWorkStatus:1,workName:'任务 & 100%',mineWorkName:'我的 + 作品',mineWorkUrl:'/mine.py?a=1&b=2',workUrl_url:'/template.py?x=a+b&y=2'}
  h.i.toAdditionalWork(row,false);let p=new URL(h.opened[0][0],'http://fixture').searchParams
  assert.equal(p.get('workId'),'saved');assert.equal(p.get('workName'),row.mineWorkName);assert.equal(p.get('workFile'),row.mineWorkUrl)
  h.i.toAdditionalWork(row,true);p=new URL(h.opened[1][0],'http://fixture').searchParams
  assert.equal(p.get('workId'),'saved');assert.equal(p.get('workName'),row.workName);assert.equal(p.get('workFile'),row.workUrl_url);assert.equal(p.get('resetTemplate'),'1')
})

test('两种 Scratch 入口携带已有 ID，继续与重做完整编码模板和名称', () => {
  for (const codeType of [1,2]) {
    const h=mount(),row={...work,codeType,mineWorkId:'saved',mineWorkStatus:0,workName:'任务 & 100%',mineWorkName:'我的 + 作品',mineWorkUrl_url:'/mine.sb3?a=1&b=2',workUrl_url:'/template.sb3?q=a+b&x=2'}
    h.i.toAdditionalWork(row,false);let u=new URL(h.opened[0][0],'http://fixture'),p=u.searchParams
    assert.equal(u.pathname,'/scratch3/index.html');assert.equal(p.get('workId'),'saved');assert.equal(p.get('workName'),row.mineWorkName);assert.equal(p.get('workFile'),row.mineWorkUrl_url)
    h.i.toAdditionalWork(row,true);p=new URL(h.opened[1][0],'http://fixture').searchParams
    assert.equal(p.get('workId'),'saved');assert.equal(p.get('workFile'),row.workUrl_url);assert.equal(p.get('resetTemplate'),'1');assert.equal(h.opened[1][2],'noopener,noreferrer')
  }
})
