const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const { execFileSync } = require('node:child_process')

const repository = path.resolve(__dirname, '../../..')
const sourceRef = process.env.PYTHON_EXECUTION_FRAME_SOURCE_REF || ''
function readSource (file) {
  return sourceRef
    ? execFileSync('git', ['show', sourceRef + ':' + file], { cwd: repository, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] })
    : fs.readFileSync(path.join(repository, file), 'utf8')
}

// Only the host browser surfaces are simulated. All tested lifecycle and protocol
// decisions execute the shipped coordinator or runner source, not a test copy.
function browserEnvironment (options = {}) {
  let now = options.now === undefined ? 1000 : options.now, nextTimer = 0
  const timers = new Map(), nodes = new Map(), listeners = {}, frames = [], posted = [], channels = [], workers = [], blobs = new Map()
  const clock = {
    setTimeout (callback, delay) { const id = ++nextTimer; timers.set(id, { callback, at: now + Math.max(0, Number(delay) || 0) }); return id },
    clearTimeout (id) { timers.delete(id) },
    setInterval (callback, delay) { const id = ++nextTimer; timers.set(id, { callback, at: now + Math.max(1, Number(delay) || 1), repeat: Math.max(1, Number(delay) || 1) }); return id },
    advance (milliseconds) {
      const target = now + milliseconds
      let count = 0
      while (true) {
        const entry = [...timers].sort((a, b) => a[1].at - b[1].at).find(([, timer]) => timer.at <= target)
        if (!entry) break
        assert.ok(++count <= 10000, 'timer fixture has a bounded number of callbacks')
        const [id, timer] = entry; timers.delete(id); now = timer.at
        if (timer.repeat) timers.set(id, { ...timer, at: now + timer.repeat })
        timer.callback()
      }
      now = target
    },
    get now () { return now },
    get pending () { return timers.size }
  }
  class Element {
    constructor (tag) {
      this.tagName = tag.toUpperCase(); this.children = []; this.parentNode = null
      this.attributes = {}; this.dataset = {}; this.style = { setProperty (name, value) { this[name] = value } }
      this.classList = { add: value => { this.className += ' ' + value }, remove: value => { this.className = this.className.split(' ').filter(item => item !== value).join(' ') } }
      this.hidden = false; this.value = ''; this.disabled = false; this.ownerDocument = document
      this.events = {}; this.className = ''; this.clientWidth = options.width || 640; this.clientHeight = options.height || 480
      this.width = this.clientWidth; this.height = this.clientHeight
      if (tag === 'canvas') {
        const drawing = { canvas: this, measureText: value => ({ width: String(value).length * 6 }),
          getImageData: () => ({ data: new Uint8ClampedArray(4) }), setLineDash () {},
          save () {}, restore () {}, translate () {}, scale () {}, rotate () {}, transform () {}, setTransform () {},
          clearRect () {}, drawImage () {}, beginPath () {}, closePath () {}, moveTo () {}, lineTo () {}, arc () {}, rect () {},
          fill () {}, stroke () {}, fillText () {}, strokeText () {}, fillRect () {}, strokeRect () {}, putImageData () {} }
        this.getContext = () => drawing
        this.toDataURL = () => 'data:image/png;base64,fixture'
      }
      if (tag === 'iframe') {
        this.srcdoc = ''
        this.contentWindow = { postMessage: (data, origin, ports) => { const item = { frame: this, data, origin, ports }; posted.push(item) } }
        frames.push(this)
      }
    }
    set id (value) { this.attributes.id = String(value); nodes.set(String(value), this) }
    get id () { return this.attributes.id || '' }
    setAttribute (name, value) { this.attributes[name] = String(value); if (name === 'id') this.id = value }
    getAttribute (name) { return this.attributes[name] || null }
    hasAttribute (name) { return Object.prototype.hasOwnProperty.call(this.attributes, name) }
    removeAttribute (name) { delete this.attributes[name] }
    appendChild (node) { node.parentNode = this; this.children.push(node); return node }
    insertBefore (node, reference) {
      if (!reference) return this.appendChild(node)
      assert.ok(this.children.includes(reference), 'insertBefore reference exists')
      node.parentNode = this; this.children.splice(this.children.indexOf(reference), 0, node); return node
    }
    removeChild (node) { this.children.splice(this.children.indexOf(node), 1); node.parentNode = null; return node }
    remove () { if (this.parentNode) this.parentNode.removeChild(this) }
    addEventListener (type, callback) { (this.events[type] || (this.events[type] = [])).push(callback) }
    removeEventListener (type, callback) { this.events[type] = (this.events[type] || []).filter(value => value !== callback) }
    dispatch (type, extra = {}) {
      const event = { target: this, preventDefault () {}, ...extra }
      if (typeof this['on' + type] === 'function') this['on' + type](event)
      for (const callback of this.events[type] || []) callback(event)
    }
    focus () { document.activeElement = this }
    blur () { if (document.activeElement === this) document.activeElement = null }
    getBoundingClientRect () { return { left: 0, top: 0, width: this.clientWidth, height: this.clientHeight } }
    reset () { this.children.forEach(child => { if ('value' in child) child.value = '' }) }
    querySelector (selector) { return find(this, selector)[0] || null }
    querySelectorAll (selector) { return find(this, selector) }
    get firstChild () { return this.children[0] || null }
    get textContent () { return this.children.map(node => node.textContent).join('') }
    set textContent (value) { this.children.forEach(node => { node.parentNode = null }); this.children = []; if (value !== '') this.appendChild(document.createTextNode(String(value))) }
    get innerHTML () { return this.textContent }
    set innerHTML (value) { assert.equal(value, '', 'fixture rejects HTML parsing'); this.textContent = '' }
  }
  function find (root, selector) {
    const match = node => selector[0] === '#' ? node.id === selector.slice(1) : node.tagName && node.tagName.toLowerCase() === selector
    return root.children.flatMap(node => [ ...(match(node) ? [node] : []), ...(node.children ? find(node, selector) : []) ])
  }
  const document = {
    readyState: 'complete', activeElement: null,
    currentScript: { src: 'http://fixture.test/python/execution.js' },
    createElement: tag => new Element(tag),
    createTextNode (value) {
      return { data: String(value), parentNode: null, get textContent () { return this.data }, get length () { return this.data.length },
        appendData (value) { this.data += value }, deleteData (start, count) { this.data = this.data.slice(0, start) + this.data.slice(start + count) } }
    },
    getElementById: id => nodes.get(id) || null,
    querySelector: selector => document.body.querySelector(selector),
    querySelectorAll: selector => document.body.querySelectorAll(selector),
    addEventListener: (type, callback) => { (listeners[type] || (listeners[type] = [])).push(callback) },
    removeEventListener: (type, callback) => { listeners[type] = (listeners[type] || []).filter(value => value !== callback) }
  }
  document.body = new Element('body'); document.head = new Element('head')
  for (const id of ['output', 'mycanvas']) { const node = new Element(id === 'output' ? 'pre' : 'div'); node.id = id; document.body.appendChild(node) }
  const location = new URL('http://fixture.test/python/' + (options.page || 'player') + '.html')
  const NativeDate = Date
  class FixtureDate extends NativeDate { constructor (...args) { super(...(args.length ? args : [now])) } static now () { return now } }
  class FixtureMessageChannel {
    constructor () {
      const port = () => ({ closed: false, onmessage: null, listeners: [], sent: [], start () {}, close () { this.closed = true },
        addEventListener (type, callback) { if (type === 'message') this.listeners.push(callback) },
        removeEventListener (type, callback) { if (type === 'message') this.listeners = this.listeners.filter(value => value !== callback) },
        postMessage (data) {
          this.sent.push(data)
          if (this.closed || this.peer.closed) return
          const event = { data }
          if (this.peer.onmessage) this.peer.onmessage(event)
          for (const callback of this.peer.listeners) callback(event)
        }
      })
      this.port1 = port(); this.port2 = port(); this.port1.peer = this.port2; this.port2.peer = this.port1
      channels.push(this)
    }
  }
  class FixtureWorker {
    constructor (url, options) { this.url = String(url); this.options = options; this.sent = []; this.listeners = {}; this.terminated = false; this.terminateCalls = 0; workers.push(this) }
    postMessage (data, ports) { if (!this.terminated) this.sent.push({ data, ports }) }
    terminate () { this.terminated = true; this.terminateCalls++; this.terminatedAt = now }
    addEventListener (type, callback) { (this.listeners[type] || (this.listeners[type] = [])).push(callback) }
    removeEventListener (type, callback) { this.listeners[type] = (this.listeners[type] || []).filter(item => item !== callback) }
    emit (type, data) {
      if (this.terminated) return
      const event = type === 'message' ? { data } : { message: String(data), preventDefault () {} }
      if (typeof this['on' + type] === 'function') this['on' + type](event)
      for (const callback of this.listeners[type] || []) callback(event)
    }
  }
  class FixtureURL extends URL {
    static createObjectURL (blob) { const url = 'blob:http://fixture.test/' + (blobs.size + 1); blobs.set(url, blob); return url }
    static revokeObjectURL (url) { blobs.delete(url) }
  }
  class FixtureImage extends Element {
    constructor () { super('img'); this.width = 64; this.height = 64; this.complete = true }
    set src (value) { this._src = value; clock.setTimeout(() => { if (this.onload) this.onload({ target: this }) }, 0) }
    get src () { return this._src || '' }
  }
  const context = {
    document, location, URL: FixtureURL, URLSearchParams, Blob, WeakMap, Map, Set,
    Date: FixtureDate, MessageChannel: FixtureMessageChannel, Worker: FixtureWorker, Image: FixtureImage, performance: { now: () => now }, console: { log () {}, warn () {}, error () {} },
    crypto: { getRandomValues: bytes => { for (let i = 0; i < bytes.length; i++) bytes[i] = i + frames.length * 13 + 1; return bytes } },
    setTimeout: clock.setTimeout, clearTimeout: clock.clearTimeout,
    setInterval: clock.setInterval, clearInterval: clock.clearTimeout,
    addEventListener: document.addEventListener, removeEventListener: document.removeEventListener,
    innerWidth: options.width || 640, innerHeight: options.height || 480,
    requestAnimationFrame: callback => clock.setTimeout(() => callback(now), 16), cancelAnimationFrame: clock.clearTimeout,
    parent: { postMessage: data => posted.push({ data, fromRunner: true }) },
    prompt () { throw new Error('Native prompt must not be used') }
  }
  context.window = context; context.self = context
  vm.createContext(context)
  // Keep native intrinsics in the tested realm. Injecting the outer Promise into
  // a different VM makes the inherited core-js shim reject it during detection.
  context.Promise = vm.runInContext('Promise', context)
  function load (file) { vm.runInContext(readSource(file), context, { filename: file, timeout: 1000 }) }
  function message (source, data, origin = 'null', ports = []) {
    for (const callback of listeners.message || []) callback({ source, data, origin, ports })
  }
  return { context, document, nodes, frames, posted, channels, workers, blobs, listeners, clock, load, message }
}

function actualComponent (bundle, environment) {
  const source = readSource('web/public/python/static/js/' + bundle + '.js')
  const marker = 'c={name:"PythonEditor"'
  assert.equal(source.split(marker).length - 1, 1, 'locate one actual bundled PythonEditor')
  const start = source.indexOf(marker) + 2, end = source.indexOf(',p={render:', start)
  assert.ok(end > start, 'locate actual bundled component end')
  const context = environment.context
  context.o = { a: {} }; context.s = { a: {} }; context.r = {}; context.a = { a: {} }
  context.u = new Proxy({}, { get () { throw new Error('Parent Skulpt must not execute') }, set () { throw new Error('Parent Skulpt must not execute') } })
  vm.runInContext('component=' + source.slice(start, end), context)
  const notifications = [], component = context.component
  const instance = {
    ...component.data(), $message: { success: text => notifications.push({ success: text }), error: text => notifications.push({ error: text }) },
    $refs: { codeEditor: { getCodeContent: () => 'print("fresh Ace")', setCodeContent () {} } },
    $nextTick: callback => callback()
  }
  for (const [name, method] of Object.entries(component.methods)) instance[name] = method.bind(instance)
  return { component, instance, notifications }
}

module.exports = { repository, sourceRef, readSource, browserEnvironment, actualComponent }
