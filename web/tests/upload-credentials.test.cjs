const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const Vue = require('vue')
const compiler = require('vue-template-compiler')
const uploadTransport = require('ant-design-vue/lib/vc-upload/src/request').default
Vue.config.silent = true

function harness () {
  let token = 'synthetic-initial-session'
  const requests = []
  const fakeWindow = { _CONFIG: { domianURL: 'https://api.example.test/api' },
    XMLHttpRequest: class {
      constructor () { this.headers = {}; this.upload = {}; this.withCredentials = false; requests.push(this) }
      open (method, action) { this.method = method; this.action = action }
      setRequestHeader (name, value) { this.headers[name] = value }
      send (data) { this.data = data }
      abort () { this.aborted = true }
    },
    FormData: class { constructor () { this.fields = [] } append (...args) { this.fields.push(args) } }
  }
  const context = { Vue: { ls: { get: key => key === 'session' ? token : { uploadType: 'local' } } },
    ACCESS_TOKEN: 'session', SYS_CONFIG: 'config', window: fakeWindow, uploadTransport, console: { log () {} } }
  const source = fs.readFileSync(path.join(__dirname, '../src/components/jeecg/JUpload.vue'), 'utf8')
  vm.createContext(context)
  vm.runInContext(source.match(/<script>([\s\S]*?)<\/script>/)[1].replace(/^\s*import .*$/gm, '')
    .replace('export default', 'component ='), context)
  const template = compiler.compile(source.slice(source.indexOf('<template>') + 10, source.indexOf('\n<script>')).replace(/<\/template>\s*$/, ''))
  assert.equal(template.errors.length, 0)
  const component = new Vue({ ...context.component, render: new Function(template.render),
    staticRenderFns: template.staticRenderFns.map(code => new Function(code)), propsData: { uploadTarget: 'local' },
    beforeCreate () { this.$store = { getters: { sysConfig: { staticDomain: '', qiniuDomain: '', qiniuArea: 'z0' } } } }
  })
  function control (node) {
    if (node.tag === 'a-upload') return node
    for (const child of node.children || []) { const found = control(child); if (found) return found }
  }
  return { component, requests, rotate: value => { token = value }, send (action, data = {}) {
    const bound = control(component._render()).data.attrs.customRequest
    assert.equal(typeof bound, 'function', 'actual component template must use credential-bound transport')
    const previous = global.window
    global.window = fakeWindow
    try {
      return bound({ action, method: 'POST', filename: 'file', file: {}, data,
        headers: { 'X-Access-Token': 'synthetic-stale-option' }, withCredentials: true,
        onSuccess () {}, onError () {} })
    } finally { global.window = previous }
  } }
}

test('local upload reads the current token when the real XHR is sent', () => {
  const h = harness()
  h.rotate('synthetic-refreshed-session')
  const request = h.send(h.component.uploadAction.local)
  assert.equal(h.requests[0].headers['X-Access-Token'], 'synthetic-refreshed-session')
  assert.equal(h.requests[0].withCredentials, false)
  request.abort()
  assert.equal(h.requests[0].aborted, true, 'the upload cancel contract is preserved')
  h.rotate(null)
  h.send(h.component.uploadAction.local)
  assert.equal('X-Access-Token' in h.requests[1].headers, false)
})

test('Qiniu and other third-party destinations never receive a platform session', () => {
  const h = harness()
  for (const target of ['qiniu', 'oss', 'cos', 'unknown']) {
    h.component.uploadTarget = target
    h.send('https://storage.example.test/upload', { token: 'synthetic-storage-only' })
    const sent = h.requests.at(-1)
    assert.equal('X-Access-Token' in sent.headers, false, target)
    assert.equal(sent.withCredentials, false, target)
    assert.ok(sent.data.fields.some(([key, value]) => key === 'token' && value === 'synthetic-storage-only'))
  }
})

test('a delayed third-party destination cannot gain credentials after switching to local', () => {
  const h = harness()
  h.component.uploadTarget = 'local'
  for (const action of ['https://storage.example.test/upload', '//upload-z0.qiniup.com', h.component.uploadAction.local + '?redirect=1']) {
    h.send(action)
    assert.equal('X-Access-Token' in h.requests.at(-1).headers, false)
  }
})
