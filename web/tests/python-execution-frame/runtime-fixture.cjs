const assert = require('node:assert/strict')
const { browserEnvironment } = require('./harness.cjs')
const CHANNEL = 'teaching-python-v1'
const RUN_ID = '1234567890abcdef1234567890abcdef'
const flush = () => new Promise(resolve => setImmediate(resolve))

function registerRuntime (h) {
  for (const file of ['runner-loader.js', 'static/js/vendor.js', 'static/js/app.js']) h.load('web/public/python/' + file)
}

// This runs the shipped engine and renderer. Canvas drawing is a no-op surface;
// returned Python values, method dispatch and callback packets are real.
function realRenderer () {
  const h = browserEnvironment(), packets = []
  registerRuntime(h)
  const sk = h.context.TeachingPythonRuntime()
  sk.TurtleGraphics = { target: 'mycanvas', width: 640, height: 480, allowUndo: true }
  h.load('web/public/python/turtle-renderer.js')
  let onPacket = packet => packets.push(packet), requestId = 0
  const bridge = h.context.TeachingPythonTurtleRenderer.create(sk, h.nodes.get('mycanvas'), packet => onPacket(packet))
  async function pump (predicate, limit = 200) {
    for (let step = 0; step < limit && !predicate(); step++) { await flush(); h.clock.advance(10) }
    assert.ok(predicate(), 'bounded fixture reached expected renderer response')
  }
  async function request (fields) {
    const id = ++requestId
    bridge.handle({ type: 'turtle-request', requestId: id, ...fields })
    await pump(() => packets.some(packet => packet.type === 'turtle-result' && packet.requestId === id))
    return packets.find(packet => packet.type === 'turtle-result' && packet.requestId === id)
  }
  return { ...h, sk, bridge, packets, pump, request, set onPacket (callback) { onPacket = callback } }
}

// The Worker realm has no document/parent and executes the real worker entry and
// fixed turtle module. Only transport and timers are controlled by this fixture.
function realWorker (code, options = {}) {
  const h = browserEnvironment(), packets = [], renderer = options.renderer === false ? null : realRenderer()
  delete h.context.document
  delete h.context.parent
  registerRuntime(h)
  if (options.thenables) {
    const runtime = h.context.TeachingPythonRuntime
    h.context.TeachingPythonRuntime = () => {
      const sk = runtime(), original = sk.misceval.asyncToPromise
      sk.misceval.asyncToPromise = function (...args) {
        const promise = original.apply(this, args)
        return { then: (resolve, reject) => promise.then(resolve, reject) }
      }
      return sk
    }
  }
  h.load('web/public/python/worker-turtle.js')
  h.load('web/public/python/worker.js')
  const channel = new h.context.MessageChannel()
  const send = (type, fields = {}) => channel.port1.postMessage({ channel: CHANNEL, type, runId: RUN_ID, ...fields })
  if (renderer) renderer.onPacket = packet => {
    renderer.packets.push(packet)
    send(packet.type, packet)
  }
  channel.port1.onmessage = event => {
    packets.push(event.data)
    if (renderer && event.data.type === 'turtle-request') renderer.bridge.handle(event.data)
  }
  h.message(undefined, { channel: CHANNEL, type: 'run', runId: RUN_ID, code }, 'null', [channel.port2])
  h.clock.advance(0)
  async function pump (predicate, limit = 300) {
    for (let step = 0; step < limit && !predicate(); step++) {
      await flush(); h.clock.advance(10); if (renderer) renderer.clock.advance(10)
    }
    assert.ok(predicate(), 'bounded fixture reached expected Worker event; packets=' + JSON.stringify(packets.map(packet => ({ type: packet.type, text: packet.text }))))
  }
  function start () { send('start'); h.clock.advance(0) }
  return { ...h, renderer, packets, channel, send, start, pump,
    output: () => packets.filter(packet => packet.type === 'output').map(packet => packet.text).join(''),
    errors: () => packets.filter(packet => packet.type === 'error').map(packet => packet.text),
    dispose: () => { channel.port1.close(); channel.port2.close(); if (renderer) renderer.bridge.dispose() }
  }
}

module.exports = { CHANNEL, RUN_ID, flush, registerRuntime, realRenderer, realWorker }
