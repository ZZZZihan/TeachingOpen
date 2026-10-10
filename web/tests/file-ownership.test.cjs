const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { resolve } = require('node:path')
const { test } = require('node:test')
const vm = require('node:vm')

for (const file of ['public/js/common.js', 'public/scratchjr/js/common.js']) {
  test(`${file}: upload credentials retain prefix without logging tokens and clear stale state`, () => {
    let request, calls = 0
    const logs = []
    const context = { console: { log (...values) { logs.push(values) } },
      localStorage: { getItem: () => JSON.stringify({ value: 'synthetic-session' }) },
      $: { ajax: opts => { request = opts; calls++; opts.success({ success: true, code: 200, result: 'synthetic-upload', keyPrefix: 'user-upload/a/' }) } } }
    context.window = context
    vm.createContext(context)
    vm.runInContext(readFileSync(resolve(__dirname, '..', file), 'utf8'), context)
    context.getSysConfig = () => 'qiniu'
    assert.equal(context.getQiniuToken(), 'synthetic-upload')
    assert.equal(context.qiniuUploadPrefix, 'user-upload/a/')
    const headers = {}
    request.beforeSend({ setRequestHeader: (name, value) => { headers[name] = value } })
    assert.deepEqual(headers, { 'X-Access-Token': 'synthetic-session' })
    context.$.ajax = opts => opts.success({ success: false, code: 510 })
    assert.equal(context.getQiniuToken(), undefined)
    assert.equal(context.qiniuUploadPrefix, '')
    context.$.ajax = () => { calls++ }
    context.getSysConfig = () => 'local'
    assert.equal(context.getQiniuToken(), undefined)
    assert.equal(calls, 1)
    assert.equal(JSON.stringify(logs).includes('synthetic-upload'), false)
    assert.equal(JSON.stringify(logs).includes('synthetic-session'), false)
  })
}

test('editor object upload uses the server prefix and reports missing credentials', () => {
  const uploads = []
  const context = { console, qn_token: 'synthetic-upload',
    qiniu: { region: { z0: 'z0' }, upload: (...args) => { uploads.push(args); return { subscribe () {} } } } }
  context.window = context
  vm.createContext(context)
  vm.runInContext(readFileSync(resolve(__dirname, '../public/js/common.js'), 'utf8'), context)
  context.getSysConfig = () => 'z0'
  context.qiniuUploadPrefix = 'user-upload/a/'
  context.upload2Qiniu('blob', 'python/unique.py', 'project', {})
  assert.equal(uploads[0][1], 'user-upload/a/python/unique.py')
  assert.equal(uploads[0][2], 'synthetic-upload')
  context.qiniuUploadPrefix = ''
  let failed = false
  context.upload2Qiniu('blob', 'python/unique.py', 'project', { error: () => { failed = true } })
  assert.equal(failed, true)
  assert.equal(uploads.length, 1)
})

test('JUpload waits for the prefix and uses distinct keys for repeated filenames', async () => {
  const source = readFileSync(resolve(__dirname, '../src/components/jeecg/JUpload.vue'), 'utf8')
  const context = { Vue: { ls: { get: () => ({uploadType:'qiniu'}) } }, SYS_CONFIG:'config', ACCESS_TOKEN:'token',
    window: { _CONFIG: { domianURL:'' } }, console, component: null }
  vm.createContext(context)
  vm.runInContext(source.match(/<script>([\s\S]*?)<\/script>/)[1].replace(/^\s*import .*$/gm, '').replace('export default', 'component ='), context)
  const selected = []
  const state = { ...context.component.data.call({ $store: { getters: { sysConfig: {} } } }),
    active: true, disabled: false, session: 0, fileType: 'file', maxFileSize: 10, uploadTarget: 'qiniu',
    $set: (object, key, value) => { object[key] = value }, $delete: (object, key) => { delete object[key] },
    $message: { error () {} }, $emit: (event, key) => { if (event === 'selected') selected.push(key) } }
  for (const [key, method] of Object.entries(context.component.methods)) state[key] = method.bind(state)
  state.getQiniuToken = () => Promise.resolve('user-upload/a/')
  await Promise.all(['one', 'two'].map(uid => state.beforeUpload( { uid, name: 'same.py', size: 20, type: 'text/plain' })))
  assert.equal(selected.length, 2)
  assert.notEqual(selected[0], selected[1])
  assert.ok(selected.every(key => key.startsWith('user-upload/a/') && key.endsWith('.py')))
  state.getQiniuToken = () => Promise.reject(new Error('offline'))
  await assert.rejects(state.beforeUpload( { uid: 'three', name: 'same.py', size: 20, type: 'text/plain' }))
  assert.equal(state.uploadKey.three, undefined)
  assert.equal(selected.length, 2)
})
