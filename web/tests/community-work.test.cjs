const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { resolve } = require('node:path')
const { test } = require('node:test')
const vm = require('node:vm')

for (const file of ['public/js/common.js', 'public/scratchjr/js/common.js']) {
  test(`${file}：本人作品读取携带令牌，匿名播放器不发送空令牌`, () => {
    for (const token of ['synthetic-token', null]) {
      let options
      const context = { localStorage: { getItem: () => token ? JSON.stringify({ value: token }) : null },
        $: { ajax: value => { options = value } }, console }
      context.window = context
      vm.createContext(context)
      vm.runInContext(readFileSync(resolve(__dirname, '..', file), 'utf8'), context)
      let loaded
      context.getWorkInfo('synthetic-work', value => { loaded = value })
      const headers = {}
      options.beforeSend({ setRequestHeader: (name, value) => { headers[name] = value } })
      assert.equal(options.url, '/api/teaching/teachingWork/studentWorkInfo')
      assert.equal(options.data.workId, 'synthetic-work')
      assert.deepEqual(headers, token ? { 'X-Access-Token': token } : {})
      options.success({ code: 0, result: { id: 'synthetic-work' } })
      assert.equal(loaded.id, 'synthetic-work')
      loaded = undefined
      options.success({ code: 510, success: false, result: null })
      assert.equal(loaded, undefined)
    }
  })
}

test('作品评论权限失败或网络失败保留列表并允许重试同一页', async () => {
  const source = readFileSync(resolve(__dirname, '../src/views/home/WorkDetail.vue'), 'utf8')
  const method = source.slice(source.indexOf('    workComments() {'), source.indexOf('    comment() {'))
  for (const failure of [{ success: false, code: 510, result: null }, new Error('offline')]) {
    const calls = []
    let response = failure
    const context = { getAction: (url, params) => {
      calls.push(params.page)
      return response instanceof Error ? Promise.reject(response) : Promise.resolve(response)
    } }
    vm.createContext(context)
    const methods = vm.runInContext('({' + method + '})', context)
    const state = { workId: 'synthetic-work', commentsPage: 1, loadingMore: false,
      comments: [{ id: 'existing' }], $message: { info () {} } }
    methods.workComments.call(state)
    await new Promise(resolve => setImmediate(resolve))
    assert.equal(state.loadingMore, false)
    assert.equal(state.commentsPage, 1)
    assert.deepEqual(state.comments, [{ id: 'existing' }])
    response = { success: true, result: [{ id: 'next' }] }
    methods.workComments.call(state)
    await new Promise(resolve => setImmediate(resolve))
    assert.equal(state.loadingMore, false)
    assert.equal(state.commentsPage, 2)
    assert.deepEqual(calls, [2, 2])
    assert.deepEqual(state.comments, [{ id: 'existing' }, { id: 'next' }])
  }
})
