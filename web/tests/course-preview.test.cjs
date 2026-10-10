const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { resolve } = require('node:path')
const { test } = require('node:test')
const vm = require('node:vm')

function preview () {
  const requests = []
  const source = readFileSync(resolve(__dirname, '../src/views/home/modules/CoursePreview.vue'), 'utf8')
  const script = source.match(/<script>([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm, '').replace('export default', 'this.component =')
  const context = { CourseCard: {}, getAction: (url, params) => new Promise((resolve, reject) => requests.push({ url, params, resolve, reject })) }
  vm.runInNewContext(script, context)
  const instance = context.component.data()
  for (const [name, fn] of Object.entries(context.component.methods)) instance[name] = fn.bind(instance)
  return { requests, instance, component: context.component }
}

test('首页只请求一页公开课程，重复点击不并发重发', async () => {
  const { requests, instance } = preview()
  const task = instance.loadCourses()
  instance.loadCourses()
  assert.equal(requests.length, 1)
  assert.equal(requests[0].params.pageNo, 1)
  assert.equal(requests[0].params.pageSize, 3)
  requests[0].resolve({ success: true, result: { records: [{ id: 'course-a', courseName: '课程 A' }] } })
  await task
  assert.equal(instance.courses[0].id, 'course-a')
  assert.equal(instance.loading, false)
})

test('首页课程网络失败后结束加载，重试成功可恢复', async () => {
  const { requests, instance } = preview()
  const failed = instance.loadCourses()
  requests[0].reject(new Error('network unavailable'))
  await failed
  assert.equal(instance.error, true)
  assert.equal(instance.loading, false)
  const retried = instance.loadCourses()
  requests[1].resolve({ success: true, result: { records: [] } })
  await retried
  assert.equal(instance.error, false)
  assert.equal(instance.loading, false)
  assert.equal(instance.courses.length, 0)
})

test('损坏的首页课程响应转为错误状态，不把空记录或非法记录渲染为卡片', async () => {
  for (const result of [null, { records: {} }, { records: [null] }, { records: [{ id: 'a' }] }]) {
    const { requests, instance } = preview()
    const pending = instance.loadCourses()
    requests[0].resolve({ success: true, result })
    await pending
    assert.equal(instance.error, true)
    assert.equal(instance.loading, false)
    assert.equal(instance.courses.length, 0)
  }
})

test('离开首页后迟到的请求不修改已销毁的组件状态', async () => {
  const { requests, instance, component } = preview()
  const pending = instance.loadCourses()
  component.beforeDestroy.call(instance)
  requests[0].resolve({ success: true, result: { records: [{ id: 'late', courseName: '旧课程' }] } })
  await pending
  assert.equal(instance.courses.length, 0)
})
