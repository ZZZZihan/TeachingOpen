const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { resolve } = require('node:path')
const { test } = require('node:test')
const vm = require('node:vm')

function filters () {
  const requests = []
  const script = readFileSync(resolve(__dirname, '../src/views/home/modules/CourseFilters.vue'), 'utf8')
    .match(/<script>([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm, '').replace('export default', 'this.component =')
  const context = { ajaxGetDictItems: code => new Promise((resolve, reject) => requests.push({ code, resolve, reject })) }
  vm.runInNewContext(script, context)
  const instance = { ...context.component.data.call({ courseName: '' }), $set: (object, key, value) => { object[key] = value } }
  for (const [name, fn] of Object.entries(context.component.methods)) instance[name] = fn.bind(instance)
  return { instance, requests, component: context.component }
}
const success = text => ({ success: true, result: [{ value: 1, text }] })

test('筛选选项并发读取，重复重试不会重复发送请求', async () => {
  const { instance, requests } = filters()
  const pending = instance.loadOptions()
  instance.loadOptions()
  assert.deepEqual(requests.map(r => r.code), ['course_category', 'course_type'])
  requests[0].resolve(success('分类'))
  requests[1].resolve(success('性质'))
  await pending
  assert.equal(instance.categoryOptions[0].value, '1')
  assert.equal(instance.typeOptions[0].text, '性质')
  assert.equal(instance.loadingOptions, false)
})

test('一个字典失败不丢弃另一个，重试可以恢复失败项', async () => {
  const { instance, requests } = filters()
  const first = instance.loadOptions()
  requests[0].reject(new Error('offline'))
  requests[1].resolve(success('可用性质'))
  await first
  assert.equal(instance.optionErrors.category, true)
  assert.equal(instance.optionErrors.type, false)
  assert.equal(instance.typeOptions[0].text, '可用性质')
  assert.equal(instance.loadingOptions, false)
  const retry = instance.loadOptions()
  requests[2].resolve(success('恢复分类'))
  requests[3].resolve(success('可用性质'))
  await retry
  assert.equal(instance.optionErrors.category, false)
  assert.equal(instance.categoryOptions[0].text, '恢复分类')
})

test('异常字典数据显示可重试错误，不作为有效选项呈现', async () => {
  for (const result of [null, {}, [{ text: '缺少值' }], [{ value: 1 }], [null]]) {
    const { instance, requests } = filters()
    const pending = instance.loadOptions()
    requests[0].resolve({ success: true, result })
    requests[1].resolve(success('正常'))
    await pending
    assert.equal(instance.optionErrors.category, true)
    assert.equal(instance.categoryOptions.length, 0)
    assert.equal(instance.loadingOptions, false)
  }
})

test('页面销毁后迟到的字典成功或失败不修改界面状态', async () => {
  const { instance, requests, component } = filters()
  const pending = instance.loadOptions()
  component.beforeDestroy.call(instance)
  requests[0].resolve(success('迟到'))
  requests[1].reject(new Error('late failure'))
  await pending
  assert.equal(instance.categoryOptions.length, 0)
  assert.equal(Object.keys(instance.optionErrors).length, 0)
})
