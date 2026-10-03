const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const { execFileSync } = require('node:child_process')

const repository = path.resolve(__dirname, '../../..')
const sourceRef = process.env.PYTHON_PREVIEW_SOURCE_REF || ''
const origin = 'http://preview.test'

function readSource (file) {
  return sourceRef
    ? execFileSync('git', ['show', sourceRef + ':' + file], { cwd: repository, encoding: 'utf8' })
    : fs.readFileSync(path.join(repository, file), 'utf8')
}

function legacyPlayer (bundle, href) {
  const source = readSource('web/public/python/static/js/' + bundle + '.js')
  const marker = 'c={name:"PythonEditor"'
  assert.equal(source.split(marker).length - 1, 1, 'locate one actual bundled PythonEditor')
  const start = source.indexOf(marker) + 2
  const end = source.indexOf(',p={render:', start)
  assert.ok(end > start, 'locate actual bundled component end')
  const requested = [], applied = [], events = [], ticks = []
  const location = new URL(href, origin)
  const document = { addEventListener: (name, callback) => events.push({ name, callback }) }
  const context = {
    component: null, URL, URLSearchParams, window: { location, document }, document,
    o: { a: {} }, s: { a: {} }, u: {}, r: {}, console: { log () {} },
    a: { a: { get: url => { requested.push(url); return Promise.resolve({ data: 'print("URL fixture loaded")\n' }) } } }
  }
  vm.createContext(context)
  vm.runInContext(readSource('web/public/python/persistence.js'), context)
  // Execute the component object from the shipped bundle; no parser is reproduced here.
  vm.runInContext('component=' + source.slice(start, end), context)
  const component = context.component
  const instance = {
    ...component.data(),
    $refs: { codeEditor: { setCodeContent: text => applied.push(text) } },
    $nextTick: callback => ticks.push(callback)
  }
  for (const [name, method] of Object.entries(component.methods)) instance[name] = method.bind(instance)
  return {
    component, instance, requested, applied, events, ticks,
    start () { component.created.call(instance); component.mounted.call(instance) }
  }
}

function player (bundle, href) {
  if (sourceRef) return legacyPlayer(bundle, href)
  // Each component is exercised through its own shipped HTML/helper entry. The
  // shared URL parser is still executed from the actual bundled method.
  const h = require('../python-source-loading/harness.cjs').page(bundle === 'app' ? 'index' : 'player', { href: new URL(href, origin).href, autoResponse: true, body: 'print("URL fixture loaded")\n' })
  const host = h.actual()
  return {
    ...host, applied: h.applied,
    get requested () { return h.requests.map(value => value.url) },
    async start () { h.start(); await h.pump(() => ['ready', 'load-error'].includes(h.phase())) }
  }
}

function caller (name, currentOrigin = origin) {
  const files = {
    teacher: 'web/src/views/teaching/modules/TeachingWorkPreviewModal.vue',
    course: 'web/src/views/account/course/modules/UnitViewModal.vue',
    community: 'web/src/views/home/WorkDetail.vue'
  }
  const source = readSource(files[name])
  const script = source.match(/<script>([\s\S]*?)<\/script>/)[1]
    .replace(/^\s*import [^\n]*$/gm, '').replace('export default', 'component =')
  const context = {
    component: null, URL, URLSearchParams, window: { location: { origin: currentOrigin } },
    Vue: {}, mapGetters: () => ({}), QrCode: {}, Keyboard: {}, Header: {}, Footer: {}, UserEnter: {},
    moment () {}, getAction () {}, postAction () {}, getFileAccessHttpUrl: value => value,
    getFilePrevew: value => value
  }
  vm.createContext(context); vm.runInContext(script, context)
  const component = context.component
  const instance = { ...component.data(), $emit () {}, $refs: {} }
  for (const [key, method] of Object.entries(component.methods)) instance[key] = method.bind(instance)
  for (const [key, getter] of Object.entries(component.computed || {})) {
    Object.defineProperty(instance, key, { get: () => getter.call(instance) })
  }
  return {
    component, instance,
    link (file) {
      if (name === 'course') {
        instance.unit = { id: 'fixture-unit', courseWorkType: '4', courseCase: file }
        return instance.caseUrl
      }
      instance.previewCode({ id: 'fixture-work', workName: 'URL fixture', workType: '4', workFileKey_url: file })
      return instance.frameHref
    }
  }
}

module.exports = { caller, origin, player, readSource, repository, sourceRef }
