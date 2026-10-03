const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const { execFileSync } = require('node:child_process')
const { browserEnvironment } = require('../python-execution-frame/harness.cjs')
const repository = path.resolve(__dirname, '../../..')
const sourceRef = process.env.PYTHON_SOURCE_LOADING_REF || ''
const flush = () => new Promise(resolve => setImmediate(resolve))
function source (file) {
  return sourceRef ? execFileSync('git', ['show', sourceRef + ':' + file], { cwd: repository, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] }) : fs.readFileSync(path.join(repository, file), 'utf8')
}
function environment (options = {}) {
  const h = browserEnvironment(), requests = [], writes = [], applied = [], locks = []
  h.context.location = new URL(options.href || '/python/player.html?queryEncoding=uri&url=%2Ffixtures%2Fseed.py', 'http://fixture.test')
  h.context.AbortController = AbortController; h.context.FormData = FormData
  h.context.getUserToken = () => ''
  h.context.history = { replaceState (state, title, url) { h.context.location = new URL(url, h.context.location.href) } }
  function response (request, body, status = 200, mime = 'text/plain; charset=utf-8') {
    if (request.transport === 'fetch') request.resolve({ ok: status >= 200 && status < 300, status, headers: { get: () => mime }, text: () => Promise.resolve(body) })
    else if (status >= 400) request.reject({ status })
    else request.resolve(body, 'success', { getResponseHeader: () => mime })
  }
  h.context.fetch = (url, settings) => new Promise((resolve, reject) => {
    const request = { transport: 'fetch', url: String(url), settings, resolve, reject }
    requests.push(request)
    settings.signal.addEventListener('abort', () => { const error = new Error('aborted'); error.name = 'AbortError'; reject(error) }, { once: true })
    if (options.autoResponse) response(request, options.body === undefined ? 'print 42\n' : options.body)
  })
  h.context.$ = { ajax (settings) {
    if (settings.url.startsWith('/api')) {
      const body = settings.data instanceof FormData ? settings.data : settings.data && JSON.parse(settings.data)
      writes.push({ ...settings, body })
      let result
      if (settings.url.includes('studentWorkInfo')) result = { id: 'seed-work', workType: 4, workName: 'Synthetic saved title', workFileKey_url: '/fixtures/seed.py?revision=1&label=a+b', additionalId: 'task-fixture', ...(options.work || {}) }
      else if (settings.url.includes('getCurrentConfig')) result = { uploadType: 'local' }
      else if (settings.url.endsWith('/upload')) { settings.success({ success: true, message: 'fixture/1.py' }); return }
      else if (settings.url.endsWith('/add')) result = { id: 'file-1', filePath: body.filePath }
      else if (settings.url.endsWith('/submit')) result = { id: body.id || 'new-work' }
      else throw new Error('Unexpected fixture API path ' + settings.url)
      settings.success({ code: 0, success: true, result }); return
    }
    const request = { transport: 'ajax', url: settings.url, settings, resolve: settings.success, reject: settings.error }
    requests.push(request)
    if (options.autoResponse) response(request, options.body === undefined ? 'print 42\n' : options.body)
  } }
  function load (file) { vm.runInContext(source(file), h.context, { filename: file, timeout: 1000 }) }
  function host (bundle = 'appPlayer', editorType = options.editorType || 'ace') {
    const text = source('web/public/python/static/js/' + bundle + '.js'), marker = 'c={name:"PythonEditor"'
    assert.equal(text.split(marker).length - 1, 1)
    const begin = text.indexOf(marker) + 2, end = text.indexOf(',p={render:', begin)
    Object.assign(h.context, { o: { a: {} }, s: { a: {} }, u: {}, r: {}, a: { a: { get (url) {
      return new Promise((resolve, reject) => { const request = { transport: 'axios', url, settings: {}, resolve: body => resolve({ data: body }), reject }; requests.push(request); if (options.autoResponse) response(request, options.body === undefined ? 'print 42\n' : options.body) })
    } } } })
    vm.runInContext('component=' + text.slice(begin, end), h.context)
    const component = h.context.component, instance = { ...component.data(), $message: { error () {}, success () {} } }, watches = {}
    const renderBegin = end + ',p='.length, renderEnd = text.indexOf('staticRenderFns:[]}', renderBegin) + 'staticRenderFns:[]}'.length
    vm.runInContext('view=' + text.slice(renderBegin, renderEnd), h.context)
    const view = h.context.view
    const child = { code: options.initialCode || '', $watch: (name, callback) => { watches['child:' + name] = callback } }
    const raw = { value: child.code, readOnly: false,
      getValue () { return this.value },
      setValue (value) { this.value = value; child.code = value; instance.code = value; applied.push(value); if (watches['child:code']) watches['child:code']() },
      setReadOnly (value) { this.readOnly = value; locks.push(value) },
      setOption (name, value) { if (name === 'readOnly') { this.readOnly = value; locks.push(value) } },
      getOption (name) { return name === 'readOnly' ? this.readOnly : undefined }
    }
    if (editorType === 'ace') child.editor = raw; else child.coder = raw
    child.getCodeContent = () => child.code
    // Preserve the inherited 300ms setter. A helper must not declare readiness
    // while this old timer can still overwrite a later user edit.
    child.setCodeContent = value => h.clock.setTimeout(() => raw.setValue(value), 300)
    instance.code = child.code; instance.$refs = { codeEditor: child }
    instance.$set = (target, name, value) => { target[name] = value }
    instance.$watch = (name, callback) => { watches[name] = callback }
    instance.$nextTick = callback => h.clock.setTimeout(callback, 0)
    instance._self = { _c: (tag, data, children) => ({ tag, data: Array.isArray(data) ? {} : data || {}, children: Array.isArray(data) ? data : children || [] }) }
    instance._v = value => String(value); instance._s = value => String(value); instance._e = () => null
    for (const [name, method] of Object.entries(component.methods)) instance[name] = method.bind(instance)
    return { component, instance, raw, child, watches, render: () => view.render.call(instance) }
  }
  async function pump (predicate, limit = 250) {
    for (let step = 0; step < limit && !predicate(); step++) { await flush(); h.clock.advance(10) }
    assert.ok(predicate(), 'bounded source fixture reached expected state')
  }
  function installNodes (html) {
    for (const match of html.matchAll(/<(span|button|div)\b[^>]*\bid=(?:"([^"]+)"|'([^']+)'|([^\s>]+))/g)) {
      const id = match[2] || match[3] || match[4]
      if (!h.nodes.has(id)) { const node = h.document.createElement(match[1]); node.id = id; h.document.body.appendChild(node) }
    }
  }
  return { ...h, requests, writes, applied, locks, response, load, host, pump, installNodes }
}
function page (name, options = {}) {
  const h = environment({ href: '/python/' + name + '.html?queryEncoding=uri&url=%2Ffixtures%2Fseed.py', ...options })
  const html = source('web/public/python/' + name + '.html')
  h.installNodes(html)
  const scripts = [...html.matchAll(/<script\b[^>]*\bsrc=(?:"([^"]+)"|'([^']+)'|([^\s>]+))/g)].map(match => match[1] || match[2] || match[3])
  const bundles = scripts.filter(value => /^\.\/static\/js\/app(?:Player)?\.js$/.test(value)).map(value => value.includes('appPlayer') ? 'appPlayer' : 'app')
  for (const script of scripts) {
    if (['./persistence.js', './source-loading.js', './editor-bridge.js', './output.js', './execution.js'].includes(script)) h.load('web/public/python/' + script.slice(2))
  }
  const hosts = bundles.map(bundle => ({ bundle, ...h.host(bundle) }))
  function start () { for (const value of hosts) { if (value.component.created) value.component.created.call(value.instance); if (value.component.mounted) value.component.mounted.call(value.instance) } h.clock.advance(0) }
  const phase = () => h.nodes.get('persistence-status')?.dataset.phase
  return { ...h, html, scripts, bundles, hosts, start, phase, actual: () => hosts.find(value => value.bundle === (name === 'index' ? 'app' : 'appPlayer')) }
}
module.exports = { repository, sourceRef, source, flush, environment, page }
