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
  const method = source.slice(source.indexOf('      beforeUpload(file){'), source.indexOf('      //上传完毕后文件列表发送变化'))
  let sequence = 0
  const context = { FILE_TYPE_IMG: 1, UPLOAD_TARGET_QINIU: 'qiniu', uuidGenerator: () => 'unique' + (++sequence) }
  vm.createContext(context)
  const methods = vm.runInContext('({' + method + '})', context)
  const selected = []
  const state = { fileType: 2, maxFileSize: 10, uploadTarget: 'qiniu', uploadKey: {},
    getQiniuToken: () => Promise.resolve('user-upload/a/'), $emit: (_, key) => selected.push(key) }
  await Promise.all(['one', 'two'].map(uid => methods.beforeUpload.call(state, { uid, name: 'same.py', size: 20, type: 'text/plain' })))
  assert.equal(selected.length, 2)
  assert.notEqual(selected[0], selected[1])
  assert.ok(selected.every(key => key.startsWith('user-upload/a/') && key.endsWith('.py')))
  state.getQiniuToken = () => Promise.reject(new Error('offline'))
  await assert.rejects(methods.beforeUpload.call(state, { uid: 'three', name: 'same.py', size: 20, type: 'text/plain' }))
  assert.equal(state.uploadKey.three, undefined)
  assert.equal(selected.length, 2)
})
