const assert = require('node:assert/strict')
const { test } = require('node:test')
const { readFileSync } = require('node:fs')
const { resolve } = require('node:path')
const vm = require('node:vm')

function loadHelper () {
  const context = {}
  vm.runInNewContext(readFileSync(resolve(__dirname, '../src/utils/loadPagedRecords.js'), 'utf8')
    .replace('export async function loadPagedRecords', 'this.loadPagedRecords = async function'), context)
  return context.loadPagedRecords
}
test('完整选择器以每页100加载101条，不丢最后一页', async () => {
  const calls = []
  const records = await loadHelper()(async params => {
    calls.push(params)
    return { success: true, result: { total: 101, records: params.pageNo === 1 ? Array.from({ length: 100 }, (_, id) => ({ id })) : [{ id: 100 }] } }
  })
  assert.equal(records.length, 101)
  assert.deepEqual(calls.map(x => [x.pageNo, x.pageSize]), [[1, 100], [2, 100]])
})
test('分页业务失败不会把部分列表误报为完整列表', async () => {
  await assert.rejects(loadHelper()(async params => params.pageNo === 1
    ? { success: true, result: { total: 101, records: Array(100).fill({}) } }
    : { success: false, message: 'failed' }), /failed/)
})
test('短页、空后页或总数变化不会把截断列表误报为完整列表', async () => {
  for (const page of [{ total: 101, records: [] }, { total: 102, records: [{ id: 100 }, { id: 101 }] }]) {
    await assert.rejects(loadHelper()(async params => ({ success: true, result: params.pageNo === 1
      ? { total: 101, records: Array.from({ length: 100 }, (_, id) => ({ id })) }
      : page })), /不完整/)
  }
  await assert.rejects(loadHelper()(async () => ({ success: true, result: { total: 101, records: [{ id: 0 }] } })), /不完整/)
})
test('完整列表拒绝缺失或无效总数及超过页大小的响应', async () => {
  for (const page of [{ records: [] }, { records: [], total: '0' }, { records: [], total: -1 }, { records: [], total: 1.5 }, { records: Array(101).fill({}), total: 101 }]) {
    await assert.rejects(loadHelper()(async () => ({ success: true, result: page })), /不完整/)
  }
})

function news () {
  const requests = []
  const context = { getAction: (url, params) => new Promise(resolve => requests.push({ url, params, resolve })) }
  vm.runInNewContext(readFileSync(resolve(__dirname, '../src/views/home/NewsList.vue'), 'utf8')
    .match(/<script>([\s\S]*?)<\/script>/)[1].replace(/^import.*$/gm, '').replace('export default', 'this.component ='), context)
  const instance = { $route: { query: {} }, $message: { warning () {} } }
  Object.assign(instance, context.component.data.call(instance))
  for (const [name, fn] of Object.entries(context.component.methods)) instance[name] = fn.bind(instance)
  return { instance, requests }
}
test('资讯翻页通过服务端读取指定页并保留总数', async () => {
  const { instance, requests } = news()
  const pending = instance.getCmsList('', 2)
  assert.equal(requests[0].params.pageNo, 2)
  assert.equal(requests[0].params.pageSize, 10)
  requests[0].resolve({ success: true, result: { records: [{ id: 11 }], total: 101 } })
  await pending
  assert.equal(instance.pagination.current, 2)
  assert.equal(instance.pagination.total, 101)
  instance.pagination.onChange(3)
  assert.equal(requests[1].params.pageNo, 3)
})
test('资讯慢响应不会覆盖后打开的页', async () => {
  const { instance, requests } = news()
  const old = instance.getCmsList('', 1), current = instance.getCmsList('', 2)
  requests[1].resolve({ success: true, result: { records: [{ id: 2 }], total: 20 } }); await current
  requests[0].resolve({ success: true, result: { records: [{ id: 1 }], total: 10 } }); await old
  assert.equal(instance.cmsDataSource[0].id, 2)
  assert.equal(instance.pagination.current, 2)
})
