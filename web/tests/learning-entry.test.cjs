const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { resolve } = require('node:path')
const { test } = require('node:test')
const vm = require('node:vm')
const sourceDir = resolve(__dirname, '../src/views/account/course')
const flush = () => new Promise(resolve => setImmediate(resolve))
function mount (file = 'CourseUnitListCard.vue', id = 'course-a') {
  const script = readFileSync(resolve(sourceDir, file), 'utf8').match(/<script>([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm, '').replace('export default', 'component =')
  const helpers = readFileSync(resolve(sourceDir, 'learningPresentation.js'), 'utf8').replace(/export /g, '')
  const requests = []; const opened = []
  const ctx = { component: null, UnitViewModal: {}, getFileAccessHttpUrl: value => value, getAction: (url, params) => new Promise((resolve, reject) => requests.push({ url, params, resolve, reject })) }
  vm.createContext(ctx); vm.runInContext(helpers + '\n' + script, ctx)
  const component = ctx.component
  const instance = Object.assign(component.data(), { $route: { query: { id } }, $refs: { unitViewModal: { view: value => opened.push(value), handleCancel () {} } } })
  for (const [key, method] of Object.entries(component.methods)) instance[key] = method.bind(instance)
  for (const [key, method] of Object.entries(component.computed || {})) Object.defineProperty(instance, key, { get: () => method.call(instance) })
  return { instance, component, requests, opened }
}
const course = id => ({ success: true, result: { id, courseName: id } })
const units = (ids, total = ids.length) => ({ success: true, result: { records: ids.map(id => ({ id, unitName: id })), total } })
async function firstPage (h, ids = ['unit-a'], total = ids.length) {
  h.instance.loadCourse(); h.requests[0].resolve(course(h.instance.courseId)); h.requests[1].resolve(units(ids, total)); await flush()
}
test('我的课程：忙状态防止重复请求，空、失败和重试成功不同', async () => {
  const h = mount('CourseListCard.vue'); h.instance.getCourseList(); h.instance.getCourseList(); assert.equal(h.requests.length, 1)
  h.requests[0].resolve({ success: true, result: [] }); await flush(); assert.equal(h.instance.loaded, true); assert.equal(h.instance.loadError, '')
  h.instance.getCourseList(); h.requests[1].reject(new Error('offline')); await flush(); assert.equal(h.instance.loaded, false); assert.ok(h.instance.loadError); assert.equal(h.instance.loading, false)
  h.instance.getCourseList(); h.requests[2].resolve({ success: true, result: [{ id: 'a' }] }); await flush(); assert.equal(h.instance.loaded, true); assert.equal(h.instance.loadError, '')
})
test('我的课程：畸形响应不伪装空列表，销毁后响应不恢复数据', async () => {
  const h = mount('CourseListCard.vue'); h.instance.getCourseList(); h.requests[0].resolve({ success: true, result: {} }); await flush(); assert.ok(h.instance.loadError)
  h.instance.getCourseList(); h.component.beforeDestroy.call(h.instance); h.requests[1].resolve({ success: true, result: [{ id: 'old' }] }); await flush(); assert.equal(h.instance.dataSource.length, 0)
})
test('地图与目录入口保留路由，摘要只显示文本', () => {
  const { instance } = mount('CourseListCard.vue')
  assert.equal(instance.courseLocation({ showType: '1', id: 'a&b' }).path, '/teaching/mineCourse/courseUnitMap'); assert.equal(instance.courseLocation({ showType: 1, id: 'a&b' }).query.id, 'a&b')
  assert.equal(instance.courseLocation({ showType: 2, id: 'a' }).path, '/teaching/mineCourse/courseUnitCard')
  assert.equal(instance.learningSummary('<style>x</style><p>一 &amp; 二</p><script>secret</script>'), '一 & 二')
})
test('目录：缺失或多值地址不请求后端', () => {
  for (const id of ['', ['a', 'b']]) { const h = mount(undefined, id); h.instance.loadCourse(); assert.equal(h.requests.length, 0); assert.ok(h.instance.loadError); assert.equal(h.instance.loading, false) }
})
test('目录：分页契约和空单元、失败响应不同', async () => {
  const h = mount(); await firstPage(h, []); assert.equal(h.requests[1].params.pageSize, 20); assert.equal(h.requests[1].params.pageNo, 1); assert.equal(h.instance.loaded, true); assert.equal(h.instance.total, 0)
  h.instance.loadCourse(); h.requests[2].resolve(course('a')); h.requests[3].resolve({ success: false }); await flush(); assert.equal(h.instance.loaded, false); assert.ok(h.instance.loadError)
})
test('目录：切课后旧错误不覆盖新页面或忙状态', async () => {
  const h = mount(); h.instance.loadCourse(); h.instance.$route.query.id = 'b'; h.instance.loadCourse()
  h.requests[0].resolve(course('a')); h.requests[1].reject(new Error('old offline')); await flush(); assert.equal(h.instance.loading, true); assert.equal(h.instance.loadError, '')
  h.requests[2].resolve(course('b')); h.requests[3].resolve(units(['unit-b'])); await flush(); assert.equal(h.instance.courseInfo.id, 'b'); assert.equal(h.instance.dataSource[0].id, 'unit-b')
})
test('目录：下一页失败保留已有内容，重试同页，连击不重复请求', async () => {
  const h = mount(); await firstPage(h, ['a'], 3); h.instance.loadMore(); h.instance.loadMore(); assert.equal(h.requests.length, 3)
  h.requests[2].reject(new Error('offline')); await flush(); assert.equal(h.instance.dataSource[0].id, 'a'); assert.equal(h.instance.page, 1); assert.ok(h.instance.loadError)
  h.instance.loadMore(); assert.equal(h.requests[3].params.pageNo, 2); h.requests[3].resolve(units(['a', 'b', 'c'], 3)); await flush()
  assert.deepEqual(Array.from(h.instance.dataSource, x => x.id), ['a', 'b', 'c']); assert.equal(h.instance.loadError, ''); h.instance.loadMore(); assert.equal(h.requests.length, 4)
})
test('目录：切课后的旧下一页不能追加单元', async () => {
  const h = mount(); await firstPage(h, ['a'], 2); h.instance.loadMore(); h.instance.$route.query.id = 'b'; h.instance.loadCourse()
  h.requests[2].resolve(units(['old'], 2)); await flush(); assert.equal(h.instance.dataSource.length, 0); assert.equal(h.instance.loading, true)
  h.requests[3].resolve(course('b')); h.requests[4].resolve(units(['new'])); await flush(); assert.deepEqual(Array.from(h.instance.dataSource, x => x.id), ['new'])
})
test('目录：分页无进展或结构损坏后重试，不无限追加空页', async () => {
  const h = mount(); await firstPage(h, ['a'], 3); h.instance.loadMore(); h.requests[2].resolve(units([], 3)); await flush(); assert.equal(h.instance.page, 1); assert.ok(h.instance.loadError)
  h.instance.loadMore(); h.requests[3].resolve({ success: true, result: { records: [], total: 'invalid' } }); await flush(); assert.equal(h.instance.page, 1); assert.ok(h.instance.loadError)
})
test('目录：资源类型只取已返回字段，原对象交给学习弹窗', async () => {
  const h = mount(); await firstPage(h); const unit = { id: 'a', courseVideo: 'video', courseWork: 'hidden-template' }
  assert.deepEqual(Array.from(h.instance.resourceLabels(unit)), ['视频']); h.instance.viewUnit(unit); assert.equal(h.opened[0], unit); assert.equal(h.instance.activeUnitId, 'a')
  assert.deepEqual(Array.from(h.instance.resourceLabels({ mediaContent: 'text', courseCase: 'case', coursePpt: 'ppt', courseWork_url: 'work' })), ['课程内容', '案例', '学习资料', '课后练习'])
})
test('目录：销毁后第一批响应不恢复数据', async () => {
  const h = mount(); h.instance.loadCourse(); h.component.beforeDestroy.call(h.instance); h.requests[0].resolve(course('a')); h.requests[1].resolve(units(['old'])); await flush(); assert.equal(h.instance.loaded, false); assert.equal(h.instance.dataSource.length, 0)
})
