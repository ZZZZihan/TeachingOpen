const assert = require('node:assert/strict')
const { test } = require('node:test')
const { readFileSync } = require('node:fs')
const { resolve } = require('node:path')
const { execFileSync } = require('node:child_process')
const vm = require('node:vm')
const root = resolve(__dirname, '..')
const flush = () => new Promise(resolve => setImmediate(resolve))
const deferred = () => { let resolve, reject; const promise = new Promise((a, b) => { resolve = a; reject = b }); return { promise, resolve, reject } }
function loadComponent (source, globals = {}) {
  const script = source.match(/<script>([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm, '').replace('export default', 'component =')
  const context = { component: null, console: { log () {} }, ...globals }
  vm.createContext(context); vm.runInContext(script, context)
  return context.component
}
function mount () {
  const submits = []; const uploads = []; const events = []; const notices = []
  const component = loadComponent(readFileSync(resolve(root, 'src/views/teaching/modules/TeachingWorkSubmitModal.vue'), 'utf8'), {
    axios: request => { const p = deferred(); submits.push({ request, ...p }); return p.promise },
    createFileTask: () => ({ cancelled: false, cancel () { this.cancelled = true } }),
    uploadAssignmentFile: (file, config, task, stage) => { const p = deferred(); uploads.push({ file, config, task, stage, ...p }); return p.promise }
  })
  const instance = { ...component.data(), $store: { getters: { sysConfig: { uploadType: 'local' } } }, $message: { success: value => notices.push(value) }, $emit: (...args) => events.push(args) }
  for (const [name, method] of Object.entries(component.methods)) instance[name] = method.bind(instance)
  for (const [name, getter] of Object.entries(component.computed)) Object.defineProperty(instance, name, { get: () => getter.call(instance) })
  return { component, instance, submits, uploads, events, notices }
}
const assignment = { workName: '  我的观察报告  ', additionalId: 'assignment-a', departId: 'class-a', workType: 0 }
const file = { name: 'report.txt', size: 128 }
function choose (h, chosen = file) { h.instance.selectFile({ target: { files: [chosen] } }) }
async function ready (h) { h.instance.open(assignment); choose(h); h.uploads[0].resolve({ id: 'owned-file-a', filePath: 'temp/report' }); await flush() }

test('基线复现：旧弹窗取消后把上一份文件 ID 提交到新作业', () => {
  const source = execFileSync('git', ['show', '1bd5fecc9f634612cca7180d7211148ecb8ea1dd:web/src/views/teaching/modules/TeachingWorkSubmitModal.vue'], { cwd: root, encoding: 'utf8' })
  const sent = []; const component = loadComponent(source, { JUpload: {}, postAction: (url, body) => { sent.push(body); return new Promise(() => {}) } })
  const i = { ...component.data(), $message: { error () {} } }; for (const [key, fn] of Object.entries(component.methods)) i[key] = fn.bind(i)
  i.open(assignment); i.saved({ id: 'file-from-a' }); i.handleCancel(); i.open({ ...assignment, additionalId: 'assignment-b' }); i.handleOk()
  assert.equal(sent[0].additionalId, 'assignment-b'); assert.equal(sent[0].workFile, 'file-from-a')
})
test('取消再打开新任务不会继承文件、作品 ID 或额外字段', async () => {
  const h = mount(); await ready(h); h.instance.handleCancel(); h.instance.open({ ...assignment, additionalId: 'assignment-b', userId: 'spoof', workFile: 'untrusted' })
  assert.equal(h.instance.fileRecord, null); assert.equal(h.instance.selectedFile, null); assert.equal(h.instance.workInfo.id, ''); assert.equal(h.instance.workInfo.userId, undefined); assert.equal(h.instance.workInfo.workFile, undefined)
  await h.instance.handleOk(); assert.equal(h.submits.length, 0); assert.match(h.instance.error, /完成上传/)
})
test('移除文件会取消上传；迟到上传与登记结果不能恢复选择', async () => {
  const h = mount(); h.instance.open(assignment); choose(h); const pending = h.uploads[0]; h.instance.removeFile()
  assert.equal(pending.task.cancelled, true); pending.stage('registering'); pending.resolve({ id: 'late' }); await flush()
  assert.equal(h.instance.stage, 'idle'); assert.equal(h.instance.fileRecord, null); await h.instance.handleOk(); assert.equal(h.submits.length, 0)
})
test('新文件验证失败会清除旧文件，空文件和超限文件不能提交', async () => {
  const h = mount(); await ready(h)
  for (const size of [0, 10 * 1024 * 1024 + 1]) { choose(h, { name: 'bad.txt', size }); assert.equal(h.instance.fileRecord, null); await h.instance.handleOk() }
  assert.equal(h.uploads.length, 1); assert.equal(h.submits.length, 0)
})
test('上传与登记期间禁止提交，上传失败可重试且只用新登记结果', async () => {
  const h = mount(); h.instance.open(assignment); choose(h); h.uploads[0].stage('registering'); await h.instance.handleOk(); assert.equal(h.submits.length, 0)
  h.uploads[0].reject(new Error('storage unavailable')); await flush(); assert.equal(h.instance.stage, 'error'); assert.equal(h.instance.fileRecord, null)
  const retry = h.instance.retryUpload(); assert.equal(h.uploads.length, 2); h.uploads[1].resolve({ id: 'retry-file' }); await retry
  assert.equal(h.instance.stage, 'ready'); assert.equal(h.instance.fileRecord.id, 'retry-file')
})
test('提交只发送一次，提交期间不允许关闭或切换作业，成功刷新父列表', async () => {
  const h = mount(); await ready(h); const sent = h.instance.handleOk(); h.instance.handleOk(); h.instance.handleCancel()
  assert.equal(h.instance.visible, true); assert.equal(h.instance.open({ additionalId: 'b' }), false); assert.equal(h.submits.length, 1)
  const body = h.submits[0].request.data; assert.equal(body.workStatus, 1); assert.equal(body.workFile, 'owned-file-a'); assert.equal(body.workName, '我的观察报告'); assert.equal(body.additionalId, 'assignment-a')
  h.submits[0].resolve({ success: true, result: { id: 'saved-work' } }); await sent
  assert.equal(h.instance.visible, false); assert.equal(h.instance.submitting, false); assert.equal(h.instance.fileRecord, null); assert.equal(h.events.length, 1); assert.equal(h.events[0][0], 'ok'); assert.equal(h.events[0][1].id, 'saved-work')
})
test('业务失败与不完整成功响应不关闭；网络失败保留文件且说明结果未确认', async () => {
  const h = mount(); await ready(h)
  for (const response of [{ success: false, message: 'SQL secret' }, { success: true, result: null }]) {
    const sent = h.instance.handleOk(); h.submits.at(-1).resolve(response); await sent
    assert.equal(h.instance.visible, true); assert.equal(h.instance.submitting, false); assert.equal(h.instance.fileRecord.id, 'owned-file-a'); assert.doesNotMatch(h.instance.error, /SQL/)
  }
  const sent = h.instance.handleOk(); h.submits.at(-1).reject(new Error('offline')); await sent
  assert.match(h.instance.error, /未能确认/); assert.equal(h.events.length, 0); assert.equal(h.notices.length, 0)
})
test('名称与后端 64 字符约束一致；销毁后迟到提交不弹成功或刷新新页面', async () => {
  const h = mount(); await ready(h)
  for (const name of ['  ', '字'.repeat(65)]) { h.instance.workInfo.workName = name; await h.instance.handleOk() }
  assert.equal(h.submits.length, 0); h.instance.workInfo.workName = '字'.repeat(64)
  const sent = h.instance.handleOk(); h.component.beforeDestroy.call(h.instance); h.submits[0].resolve({ success: true, result: { id: 'saved' } }); await sent
  assert.equal(h.events.length, 0); assert.equal(h.notices.length, 0); assert.equal(h.instance.visible, false)
})

function uploader () {
  const calls = []; const cloud = []; let cancelled = false
  const token = { throwIfRequested () { if (cancelled) throw new Error('cancelled') } }
  const http = config => { const p = deferred(); calls.push({ config, ...p }); return p.promise }
  const Axios = config => { const p = deferred(); cloud.push({ config, ...p }); return p.promise }; Axios.CancelToken = { source: () => ({ token, cancel: () => { cancelled = true } }) }
  class FormData { constructor () { this.items = new Map() } append (key, value) { this.items.set(key, value) } get (key) { return this.items.get(key) } }
  const context = { axios: http, Axios, FormData, Uint8Array, window: { crypto: { getRandomValues: bytes => bytes.fill(7) } } }
  vm.createContext(context); vm.runInContext(readFileSync(resolve(root, 'src/views/teaching/modules/assignmentFileUpload.js'), 'utf8').replace(/^import .*$/gm, '').replace(/^export /gm, ''), context)
  const stages = []; const task = context.createFileTask()
  return { calls, cloud, task, stages, upload: config => context.uploadAssignmentFile(file, config, task, stage => stages.push(stage)) }
}
test('本地上传完成不等于登记成功；登记返回匹配路径与 ID 才可提交', async () => {
  const h = uploader(); const done = h.upload({ uploadType: 'local' }); const form = h.calls[0].config.data
  assert.equal(form.get('file'), file); assert.equal(form.get('bizPath'), 'temp'); h.calls[0].resolve({ success: true, message: 'temp/owned-file' }); await flush()
  assert.deepEqual(h.stages, ['uploading', 'registering']); assert.equal(h.calls[1].config.data.fileLocation, 1)
  h.calls[1].resolve({ success: true, result: { id: 'owned-id', filePath: 'temp/owned-file' } }); assert.equal((await done).id, 'owned-id')
})
test('上传业务失败不登记，登记失败/缺失 ID/错误路径均拒绝就绪', async () => {
  const h = uploader(); const done = h.upload({ uploadType: 'local' }); const rejected = assert.rejects(done); h.calls[0].resolve({ success: false, message: 'bad' }); await rejected; assert.equal(h.calls.length, 1)
  for (const result of [{ success: false }, { success: true, result: { filePath: 'p' } }, { success: true, result: { id: 'x', filePath: 'other' } }]) {
    const h = uploader(); const done = h.upload({}); const rejected = assert.rejects(done); h.calls[0].resolve({ success: true, message: 'p' }); await flush(); h.calls[1].resolve(result); await rejected
  }
})
test('七牛使用受限前缀的新 key，平台认证与 Cookie 不发给云上传', async () => {
  const h = uploader(); const done = h.upload({ uploadType: 'qiniu', qiniuArea: 'z0' }); h.calls[0].resolve({ success: true, result: 'scoped-upload-credential', keyPrefix: 'uploads/current-user/' }); await flush()
  const c = h.cloud[0].config; assert.equal(c.url, 'https://upload-z0.qiniup.com'); assert.equal(c.withCredentials, false); assert.equal(c.headers, undefined)
  const key = c.data.get('key'); assert.match(key, /^uploads\/current-user\/[0-9a-f]{32}\.txt$/); assert.equal(c.data.get('file'), file)
  h.cloud[0].resolve({ data: { key } }); await flush(); assert.equal(h.calls[1].config.data.fileLocation, 2); h.calls[1].resolve({ success: true, result: { id: 'qiniu-id', filePath: key } }); assert.equal((await done).id, 'qiniu-id')
})
test('七牛凭证/区域/响应 key 不合规或上传取消后不登记文件', async () => {
  for (const config of [{ uploadType: 'oss' }, { uploadType: 'qiniu', qiniuArea: 'evil/path' }]) { const h = uploader(); await assert.rejects(h.upload(config)); assert.equal(h.calls.length, 0) }
  for (const credential of [{ success: false }, { success: true, result: 'token' }, { success: true, keyPrefix: 'uploads/u/' }]) {
    const h = uploader(); const done = h.upload({ uploadType: 'qiniu', qiniuArea: 'z0' }); const rejected = assert.rejects(done)
    h.calls[0].resolve(credential); await rejected; assert.equal(h.cloud.length, 0); assert.equal(h.calls.length, 1)
  }
  const h = uploader(); const done = h.upload({}); const rejected = assert.rejects(done); h.task.cancel(); h.calls[0].resolve({ success: true, message: 'p' }); await rejected; assert.equal(h.calls.length, 1)
  const q = uploader(); const wrong = q.upload({ uploadType: 'qiniu', qiniuArea: 'z0' }); const rejection = assert.rejects(wrong); q.calls[0].resolve({ success: true, result: 'scope', keyPrefix: 'uploads/u/' }); await flush(); q.cloud[0].resolve({ data: { key: 'wrong' } }); await rejection; assert.equal(q.calls.length, 1)
})

test('提交成功事件有父列表监听；列表失败结束加载，可重试，迟到筛选不覆盖', async () => {
  const source = readFileSync(resolve(root, 'src/views/account/course/MyAdditionalWorkList.vue'), 'utf8')
  assert.match(source, /<TeachingWorkSubmitModal[^>]+@ok="getList"/)
  const requests = []
  const component = loadComponent(source, { mixinDevice: {}, JDictSelectTag: {}, TeachingWorkSubmitModal: {}, getFileAccessHttpUrl () {}, getFilePrevew () {}, getAction: () => { const p = deferred(); requests.push(p); return p.promise } })
  const i = { ...component.data() }; for (const [key, fn] of Object.entries(component.methods)) i[key] = fn.bind(i)
  const first = i.getList(); requests[0].reject(new Error('offline')); await first; assert.equal(i.loading, false); assert.equal(i.listError, true)
  const old = i.getList(); const current = i.getList(); requests[2].resolve({ success: true, result: [{ id: 'new' }] }); await current; requests[1].resolve({ success: true, result: [{ id: 'old' }] }); await old
  assert.equal(i.datasource[0].id, 'new'); assert.equal(i.listError, false); assert.equal(i.loading, false)
})
