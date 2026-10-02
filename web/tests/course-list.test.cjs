const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { resolve } = require('node:path')
const { test } = require('node:test')
const vm = require('node:vm')

// Exercise the real SFC methods with controlled request ordering. No live API is used.
function mountCourseList (userAgent = 'desktop') {
  const source = readFileSync(resolve(__dirname, '../src/views/home/CourseList.vue'), 'utf8')
  const script = source.match(/<script>([\s\S]*?)<\/script>/)[1]
    .replace(/^import .*$/gm, '')
    .replace('export default', 'component =')
  const requests = []
  const context = {
    component: null,
    navigator: { userAgent },
    console,
    Header: {}, Banner: {}, Footer: {}, UserEnter: {}, QrCode: {},
    getFileAccessHttpUrl: value => value,
    getAction: (url, params) => new Promise((resolve, reject) => {
      requests.push({ url, params, resolve, reject })
    })
  }
  vm.createContext(context)
  vm.runInContext(script, context)
  const component = context.component
  const instance = component.data()
  for (const [name, method] of Object.entries(component.methods)) instance[name] = method.bind(instance)
  return { instance, requests, component }
}

const flush = () => new Promise(resolve => setImmediate(resolve))
const success = (id, total = 100) => ({ success: true, result: { records: [{ id }], total } })
const ids = instance => Array.from(instance.datasource, row => row.id)

test('初次查询携带筛选条件与桌面分页大小', async () => {
  const { instance, requests, component } = mountCourseList()
  component.created.call(instance)
  assert.equal(requests[0].url, '/teaching/teachingCourse/getHomeCourse')
  assert.equal(requests[0].params.pageNo, 1)
  assert.equal(requests[0].params.pageSize, 24)
  requests[0].resolve(success('first'))
  await flush()
  assert.deepEqual(ids(instance), ['first'])
  assert.equal(instance.loading, false)
})

test('重复点击加载更多只发出一个请求', async () => {
  const { instance, requests } = mountCourseList()
  instance.getData()
  instance.getData()
  assert.equal(requests.length, 1)
  requests[0].resolve(success('first'))
  await flush()
})

test('失败响应后重试第一页，不跳过课程', async () => {
  const { instance, requests } = mountCourseList()
  instance.getData()
  requests[0].resolve({ success: false, message: 'unavailable' })
  await flush()
  assert.equal(instance.loading, false)
  assert.ok(instance.loadError)
  instance.getData()
  assert.equal(requests[1].params.pageNo, 1)
  requests[1].resolve(success('retried'))
  await flush()
  assert.deepEqual(ids(instance), ['retried'])
  assert.equal(instance.loadError, '')
})

test('网络失败结束加载并保留已有课程，重试同一页', async () => {
  const { instance, requests } = mountCourseList()
  instance.getData()
  requests[0].resolve(success('first'))
  await flush()
  instance.getData()
  requests[1].reject(new Error('offline'))
  await flush()
  assert.equal(instance.loading, false)
  assert.deepEqual(ids(instance), ['first'])
  assert.ok(instance.loadError)
  instance.getData()
  assert.equal(requests[2].params.pageNo, 2)
  requests[2].resolve(success('second'))
  await flush()
  assert.deepEqual(ids(instance), ['first', 'second'])
})

test('旧筛选结果提前返回时不污染新结果或结束新请求的加载', async () => {
  const { instance, requests } = mountCourseList()
  instance.getData()
  instance.handleChangeCategory('2')
  assert.equal(requests[1].params.courseCategory, '2')
  assert.equal(requests[1].params.pageNo, 1)
  requests[0].resolve(success('old'))
  await flush()
  assert.deepEqual(ids(instance), [])
  assert.equal(instance.loading, true)
  requests[1].resolve(success('new'))
  await flush()
  assert.deepEqual(ids(instance), ['new'])
})

test('旧筛选结果最后返回时不覆盖新结果', async () => {
  const { instance, requests } = mountCourseList()
  instance.getData()
  instance.handleChangeType('1')
  requests[1].resolve(success('new'))
  await flush()
  requests[0].resolve(success('old'))
  await flush()
  assert.deepEqual(ids(instance), ['new'])
  assert.equal(instance.loading, false)
})

test('旧请求失败不显示新查询的错误', async () => {
  const { instance, requests } = mountCourseList()
  instance.getData()
  instance.onSearch('AI')
  requests[0].reject(new Error('old request failed'))
  await flush()
  assert.equal(instance.loadError, '')
  assert.equal(instance.loading, true)
  assert.equal(requests[1].params.courseName, 'AI')
  requests[1].resolve(success('new'))
  await flush()
})

test('课程总数到达后停止分页，切换搜索恢复第一页', async () => {
  const { instance, requests } = mountCourseList()
  instance.getData()
  requests[0].resolve(success('only', 1))
  await flush()
  instance.getData()
  assert.equal(requests.length, 1)
  instance.onSearch('new')
  assert.equal(requests[1].params.pageNo, 1)
  requests[1].resolve({ success: true, result: { records: [], total: 0 } })
  await flush()
  assert.deepEqual(ids(instance), [])
  assert.equal(instance.hasMore, false)
  assert.equal(instance.loadError, '')
})

test('服务端返回空页时停止继续加载', async () => {
  const { instance, requests } = mountCourseList()
  instance.getData()
  requests[0].resolve({ success: true, result: { records: [], total: 10 } })
  await flush()
  instance.getData()
  assert.equal(requests.length, 1)
})

test('格式错误的响应显示可重试错误', async () => {
  const { instance, requests } = mountCourseList()
  instance.getData()
  requests[0].resolve({ success: true, result: null })
  await flush()
  assert.equal(instance.loading, false)
  assert.ok(instance.loadError)
  instance.getData()
  assert.equal(requests[1].params.pageNo, 1)
  requests[1].resolve(success('retried'))
  await flush()
})

test('移动设备每页请求 12 条课程', async () => {
  const { instance, requests } = mountCourseList('iPhone')
  instance.getData()
  assert.equal(requests[0].params.pageSize, 12)
  requests[0].resolve(success('mobile'))
  await flush()
})

test('缺失总数的响应不会静默结束分页', async () => {
  const { instance, requests } = mountCourseList()
  instance.getData()
  requests[0].resolve({ success: true, result: { records: [{ id: 'invalid' }] } })
  await flush()
  assert.ok(instance.loadError)
  assert.deepEqual(ids(instance), [])
  instance.getData()
  assert.equal(requests[1].params.pageNo, 1)
  requests[1].resolve(success('valid'))
  await flush()
})

test('离开页面后忽略尚未完成的请求', async () => {
  const { instance, requests, component } = mountCourseList()
  instance.getData()
  component.beforeDestroy.call(instance)
  requests[0].resolve(success('late'))
  await flush()
  assert.deepEqual(ids(instance), [])
})
