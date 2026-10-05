const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { resolve } = require('node:path')
const { test } = require('node:test')
const vm = require('node:vm')
const flush = () => new Promise(resolve => setImmediate(resolve))
function mount () {
  const source = readFileSync(resolve(__dirname, '../src/views/account/course/modules/UnitViewModal.vue'), 'utf8')
  const script = source.match(/<script>([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm, '').replace('export default', 'component =')
  const requests = []; const listeners = new Map(); const removed = []; let previews = 0
  const doc = { addEventListener: (name, fn) => listeners.set(name, fn), removeEventListener: (name, fn) => { assert.equal(listeners.get(name), fn); removed.push(name); listeners.delete(name) } }
  const ctx = { component: null, document: doc, URL, URLSearchParams, window: { location: { origin: 'http://localhost:18112' } }, getFileAccessHttpUrl: path => path || undefined, getFilePrevew: path => { previews++; if (new URL(path, 'http://localhost:18112').pathname === '/broken-config') throw new Error('broken preview'); return path }, getAction: (url, params) => new Promise((resolve, reject) => requests.push({ url, params, resolve, reject })) }
  vm.createContext(ctx); vm.runInContext(script, ctx)
  const component = ctx.component; const instance = Object.assign(component.data(), { $refs: {} })
  for (const [name, fn] of Object.entries(component.methods)) instance[name] = fn.bind(instance)
  for (const [name, fn] of Object.entries(component.computed)) Object.defineProperty(instance, name, { get: () => fn.call(instance) })
  return { instance, component, requests, doc, listeners, removed, previews: () => previews }
}
function legacyRead (href, key) {
  const source = readFileSync(resolve(__dirname, '../public/js/common.js'), 'utf8').split('window.uuid')[0]
  const context = { URLSearchParams, window: { location: { search: new URL(href, 'http://local').search } } }
  vm.createContext(context); vm.runInContext(source, context); return context.window.urlParams(key)
}
test('阅读器：按实际内容选择初始视图，记录失败不会阻止阅读', async () => {
  const h = mount(); h.instance.view({ id: 'a&b', unitName: 'Lesson', mediaContent: '<p>Text</p>' })
  assert.equal(h.instance.activeTab, 'content'); assert.equal(h.requests[0].params.unitId, 'a&b'); assert.equal(h.requests[0].url.includes('?'), false)
  h.requests[0].reject(new Error('offline')); await flush(); assert.equal(h.instance.logFailed, true); assert.equal(h.instance.visible, true)
})
test('阅读器：旧单元日志失败不污染新单元，关闭后不恢复状态', async () => {
  const h = mount(); h.instance.view({ id: 'a' }); h.instance.view({ id: 'b', courseVideo: 'video' }); h.requests[0].reject(new Error('old')); await flush(); assert.equal(h.instance.logFailed, false)
  h.instance.handleCancel(); h.requests[1].reject(new Error('late')); await flush(); assert.equal(h.instance.visible, false); assert.equal(h.instance.logFailed, false)
})
test('阅读器：切换和关闭暂停视频、移除源并卸载 iframe，重试重建媒体', () => {
  const h = mount(); const events = []
  h.instance.$refs.video = { pause: () => events.push('pause'), removeAttribute: name => events.push(name), load: () => events.push('load') }; h.instance.$refs.caseFrame = { src: '/old' }
  h.instance.activeTab = 'video'; h.instance.selectTab('case'); assert.deepEqual(events, ['pause', 'src', 'load']); assert.equal(h.instance.$refs.caseFrame.src, 'about:blank')
  const version = h.instance.mediaVersion; h.instance.videoState = 'error'; h.instance.retryMedia(); assert.equal(h.instance.mediaVersion, version + 1); assert.equal(h.instance.videoState, 'loading')
  h.instance.handleCancel(); assert.equal(h.instance.visible, false); assert.equal(h.instance.activeTab, '')
})
test('阅读器：迟到的视频事件不能污染新播放器', () => {
  const { instance } = mount(); instance.mediaVersion = 3; instance.setVideoState({ target: { dataset: { mediaVersion: '2' } } }, 'error'); assert.equal(instance.videoState, 'loading')
  instance.setVideoState({ target: { dataset: { mediaVersion: '3' } } }, 'ready'); assert.equal(instance.videoState, 'ready')
})
test('阅读器：生命周期移除三个相同监听器，缓存停用关闭媒体', () => {
  const h = mount(); h.component.mounted.call(h.instance); assert.equal(h.listeners.size, 3)
  h.instance.visible = true; h.component.deactivated.call(h.instance); assert.equal(h.instance.visible, false)
  h.component.beforeDestroy.call(h.instance); assert.equal(h.listeners.size, 0); assert.equal(h.removed.length, 3)
})
test('阅读器：空 iframe 与跨域 document 不能触发异常', () => {
  const h = mount(); h.instance.visible = true; h.instance.activeTab = 'case'; h.instance.handleScratchInit(); h.instance.handleScratchFullscreen()
  const frame = {}; Object.defineProperty(frame, 'contentDocument', { get () { throw new Error('cross origin') } }); h.instance.$refs.caseFrame = frame
  assert.doesNotThrow(() => h.instance.handleScratchInit())
})
test('阅读器：案例点击监听不重复，退出只操作自己的全屏', () => {
  const h = mount(); let added = 0; let removed = 0; let exited = 0
  const target = { addEventListener: () => added++, removeEventListener: () => removed++ }
  const frame = { contentDocument: { getElementById: () => target } }
  h.instance.$refs.caseFrame = frame; h.instance.visible = true; h.instance.activeTab = 'case'; h.instance.handleScratchInit(); h.instance.handleScratchInit()
  assert.equal(added, 2); assert.equal(removed, 1); h.instance.stopMedia(); assert.equal(removed, 2)
  h.doc.fullscreenElement = {}; h.doc.exitFullscreen = () => exited++; h.instance.handleScratchExit(); assert.equal(exited, 0)
  h.doc.fullscreenElement = frame; h.instance.handleScratchExit(); assert.equal(exited, 1)
})
test('阅读器：ScratchJr 与 Python 保留完整任务和特殊字符文件参数', () => {
  const { instance } = mount(); const file = 'https://files.test/a%20b.sjr?x=1&y=中文#part'
  instance.unit = { id: 'lesson&a', courseWorkType: '3', courseWork: file, courseWork_url: file }
  assert.equal(legacyRead(instance.workUrl, 'unitId'), 'lesson&a'); assert.equal(legacyRead(instance.workUrl, 'scene'), 'course'); assert.equal(legacyRead(instance.workUrl, 'workFile'), new URL(file).href)
  instance.unit.courseWorkType = 4; const python = new URL(instance.workUrl, 'http://local'); assert.equal(python.searchParams.get('unitId'), 'lesson&a'); assert.equal(python.searchParams.get('url'), new URL(file).href)
})
test('阅读器：Scratch 案例的嵌套地址能由实际公共解析器解码', () => {
  const { instance } = mount(); const file = 'https://files.test/a.sb3?x=1&y=2'
  instance.unit = { courseWorkType: '2', courseCase: file }; assert.equal(legacyRead(instance.caseUrl, 'workUrl'), file)
  instance.unit = { id: 'lesson', courseWorkType: 2, courseWork_url: file }; assert.equal(legacyRead(instance.workUrl, 'unitId'), 'lesson')
})
test('公共查询解析器：不带 opt-in 的历史链接保持百分号与大小写契约', () => {
  assert.equal(legacyRead('/scratch3/player.html?workUrl=https://files.test/a%20b.sb3', 'workUrl'), 'https://files.test/a%20b.sb3')
  assert.equal(legacyRead('/scratch3/player.html?UNITID=abc', 'unitId'), 'abc'); assert.equal(legacyRead('/x', 'missing'), '')
})
test('阅读器：资料配置异常不破坏其他资料，拒绝可执行协议', () => {
  const { instance } = mount(); instance.unit = { coursePpt: 'broken-config,https://files.test/one.SB3?x=1&y=2', coursePlan: 'javascript:alert(1)' }
  assert.equal(instance.resources.length, 3); assert.equal(instance.resources[0].url, ''); assert.equal(legacyRead(instance.resources[1].url, 'workFile'), 'https://files.test/one.SB3?x=1&y=2'); assert.equal(instance.resources[2].url, '')
  for (const input of ['javascript:alert(1)', 'data:text/html,x', 'file:///etc/passwd', null, '']) assert.equal(instance.safeUrl(input), '')
})
