const assert = require('node:assert/strict')
const { test } = require('node:test')
const { readSource, browserEnvironment, actualComponent } = require('./python-execution-frame/harness.cjs')
const CHANNEL = 'teaching-python-v1'
const runId = '1234567890abcdef1234567890abcdef'
const flush = () => new Promise(resolve => setImmediate(resolve))

function rendererHost (options = {}) {
  const h = browserEnvironment(), configured = [], requests = [], order = []
  const sk = { python2: {}, builtinFiles: { files: {} }, configure: value => configured.push(value) }
  let disposeCalls = 0
  h.context.MutationObserver = class { observe () {} }
  h.context.TeachingPythonRuntime = () => sk
  h.context.TeachingPythonTurtleRenderer = { create: (runtime, node, reply) => ({
    handle (packet) { requests.push(packet); if (options.reply) reply({ type: 'turtle-result', requestId: packet.requestId, value: null }) },
    dispose () { disposeCalls++ }
  }) }
  const terminate = h.context.Worker.prototype.terminate
  h.context.Worker.prototype.terminate = function () { order.push('terminate'); terminate.call(this) }
  h.load('web/public/python/runner.js')
  const channel = new h.context.MessageChannel()
  channel.port1.onmessage = event => { if (event.data.type === 'stopped') order.push('stopped') }
  const start = (code = 'print 42') => {
    h.message(h.context.parent, { channel: CHANNEL, type: 'run', runId, code }, 'http://fixture.test', [channel.port2])
    h.clock.advance(0)
  }
  const fromWorker = (type, fields = {}) => {
    const worker = h.workers[0], transfer = worker.sent[0]
    transfer.ports[0].postMessage({ channel: CHANNEL, type, runId, ...fields })
  }
  const fromParent = (type, fields = {}) => channel.port1.postMessage({ channel: CHANNEL, type, runId, ...fields })
  return { ...h, sk, configured, requests, channel, sent: channel.port2.sent, start, fromWorker, fromParent, order, get disposeCalls () { return disposeCalls } }
}

function coordinator (options) {
  const h = browserEnvironment(options)
  h.load('web/public/python/output.js'); h.load('web/public/python/execution.js')
  const api = h.context.TeachingPythonExecution
  function boot () {
    const frame = [...h.nodes.get('mycanvas').querySelectorAll('iframe')].findLast(value => value.style.display !== 'none')
    assert.ok(frame, 'actual coordinator created a runner frame')
    frame.dispatch('load')
    const transfer = h.posted.findLast(item => item.frame === frame)
    assert.ok(transfer && transfer.ports.length === 1, 'one private port is transferred to the current runner')
    const send = (type, fields = {}) => transfer.ports[0].postMessage({ channel: CHANNEL, type, runId: transfer.data.runId, ...fields })
    send('ready')
    return { frame, transfer, send, port: transfer.ports[0] }
  }
  return { ...h, api, boot, output: () => h.nodes.get('output').textContent }
}

for (const bundle of ['app', 'appPlayer']) {
  test(bundle + ' actual runit delegates current code into opaque frame and actual clear destroys it', () => {
    const h = coordinator(), host = actualComponent(bundle, h).instance
    host.code = 'print "downloaded player"'; host.runit()
    const run = h.boot(), expected = bundle === 'app' ? 'print("fresh Ace")' : 'print "downloaded player"'
    assert.equal(run.transfer.data.code, expected)
    assert.deepEqual(Object.keys(run.transfer.data).sort(), ['channel', 'code', 'runId', 'type'])
    assert.equal(run.frame.getAttribute('sandbox'), 'allow-scripts')
    assert.equal(run.frame.getAttribute('referrerpolicy'), 'no-referrer')
    assert.equal(h.api.getState().state, 'running')
    assert.match(run.frame.srcdoc, /frame-src &#?[^;]*|frame-src 'none'/)
    assert.ok(!run.frame.srcdoc.includes(expected), 'student code never appears in executable HTML')
    run.send('output', { text: '<b>literal & 中文</b>' }); assert.equal(h.output(), '<b>literal & 中文</b>')
    host.clear()
    assert.equal(run.frame.parentNode, h.nodes.get('mycanvas'), 'clear awaits confirmed Worker termination before frame removal')
    run.send('stopped')
    assert.equal(run.frame.parentNode, null); assert.equal(h.output(), '')
    assert.equal(h.api.getState().state, 'idle')
    run.send('output', { text: 'STALE_AFTER_CLEAR' }); assert.equal(h.output(), '')
  })
}

test('repeat Run keeps one computation host until old termination ack and starts only the latest queued code', async () => {
  const h = coordinator()
  h.api.run('print "first"'); const first = h.boot(), firstId = h.api.getState().runId
  first.send('input', { requestId: '1', prompt: 'old prompt' })
  h.api.run('print "second"'); const lastId = h.api.run('print "latest"')
  assert.equal(h.api.getState().runId, firstId)
  assert.equal(h.nodes.get('mycanvas').querySelectorAll('iframe').length, 1, 'no second computation host before old termination is confirmed')
  assert.equal(h.nodes.get('python-execution-input-form').hidden, true)
  first.send('output', { text: 'STALE' }); first.send('done')
  assert.equal(h.output(), ''); assert.equal(h.api.getState().state, 'stopping')
  first.send('stopped'); await flush()
  const second = h.boot()
  assert.equal(h.api.getState().runId, lastId); assert.equal(first.frame.parentNode, null)
  assert.equal(second.transfer.data.code, 'print "latest"')
  second.send('output', { text: 'fresh' }); const stopping = h.api.stop()
  assert.equal(second.frame.parentNode, h.nodes.get('mycanvas'))
  second.send('stopped'); await stopping
  assert.equal(second.frame.parentNode, null); assert.equal(h.api.getState().state, 'stopped')
  second.send('output', { text: 'STALE' }); assert.equal(h.output(), 'fresh')
  h.api.clear(); assert.equal(h.output(), '')
})

test('actual coordinator and trusted host keep rapid reruns queued throughout Worker retirement cooldown', async () => {
  const parent = coordinator(), renderer = rendererHost()
  parent.api.run('print "old"')
  const old = parent.nodes.get('mycanvas').querySelector('iframe')
  const createdFrames = parent.frames.length
  old.dispatch('load')
  const transfer = parent.posted.find(item => item.frame === old)
  renderer.message(renderer.context.parent, transfer.data, 'http://fixture.test', transfer.ports)
  renderer.clock.advance(0)
  renderer.workers[0].sent[0].ports[0].postMessage({ channel: CHANNEL, type: 'ready', runId: transfer.data.runId })
  assert.equal(parent.api.getState().state, 'running')
  parent.api.run('print "discarded"'); const latest = parent.api.run('print "latest"')
  assert.equal(renderer.workers[0].terminateCalls, 1)
  assert.equal(old.parentNode, parent.nodes.get('mycanvas'))
  renderer.clock.advance(2499); parent.clock.advance(2499); await flush()
  assert.equal(parent.frames.length, createdFrames); assert.equal(parent.api.getState().state, 'stopping')
  renderer.clock.advance(1); parent.clock.advance(1); await flush()
  assert.equal(old.parentNode, null); assert.equal(parent.nodes.get('mycanvas').querySelectorAll('iframe').length, 1)
  const current = parent.boot()
  assert.equal(current.transfer.data.code, 'print "latest"'); assert.equal(parent.api.getState().runId, latest)
  parent.api.stop(); current.send('stopped')
})

test('public window messages cannot forge output, input or done; private protocol rejects malformed and oversized fields', () => {
  const h = coordinator(); h.api.run('print 42'); const run = h.boot(), id = h.api.getState().runId
  for (const type of ['output', 'input', 'done', 'error', 'graphics', 'callback-start', 'callback-done']) {
    h.message(run.frame.contentWindow, { channel: CHANNEL, type, runId: id, text: 'FORGED', requestId: '1', prompt: 'FORGED' })
  }
  assert.equal(h.output(), ''); assert.equal(h.api.getState().state, 'running')
  assert.equal(h.nodes.get('python-execution-input-form').hidden, true)
  for (const invalid of [
    { channel: CHANNEL, type: 'output', runId: 'old', text: 'WRONG_ID' },
    { channel: 'other', type: 'output', runId: id, text: 'WRONG_CHANNEL' },
    { channel: CHANNEL, type: 'output', runId: id, text: {} },
    { channel: CHANNEL, type: 'output', runId: id, text: 'x'.repeat(2049) },
    { channel: CHANNEL, type: 'input', runId: id, requestId: {}, prompt: 'bad' },
    { channel: CHANNEL, type: 'input', runId: id, requestId: '1', prompt: 'x'.repeat(2049) },
    { channel: CHANNEL, type: 'error', runId: id, text: 'x'.repeat(2049) }
  ]) run.port.postMessage(invalid)
  assert.equal(h.output(), ''); assert.equal(h.api.getState().state, 'running')
  assert.equal(h.nodes.get('python-execution-input-form').hidden, true)
  run.send('output', { text: '<img src=x onerror=alert(1)>' }); assert.equal(h.output(), '<img src=x onerror=alert(1)>')
  assert.equal(h.nodes.get('output').children.length, 1)
})

test('parent gives completed turtle callbacks 30s, pauses for input and does not reset an active callback budget', () => {
  const h = coordinator(); h.api.run('import turtle'); const run = h.boot()
  run.send('done'); h.clock.advance(40000)
  assert.equal(h.api.getState().state, 'completed')
  run.send('callback-start', { requestId: '1' })
  assert.equal(h.api.getState().state, 'running'); assert.equal(h.api.getState().remainingMs, 30000)
  h.clock.advance(5000); run.send('input', { requestId: '2', prompt: 'callback input' })
  assert.equal(h.api.getState().remainingMs, 25000)
  h.clock.advance(40000); assert.equal(h.api.getState().state, 'waiting-input')
  assert.equal(h.api.getState().remainingMs, 25000)
  h.nodes.get('python-execution-input').value = 'continue'
  h.nodes.get('python-execution-input-form').dispatch('submit')
  h.clock.advance(1000); run.send('callback-done', { requestId: '1' })
  assert.equal(h.api.getState().state, 'completed')
  h.clock.advance(40000); assert.equal(h.api.getState().state, 'completed', 'idle drawing does not consume a computation budget')
  run.send('callback-start', { requestId: '3' }); h.clock.advance(29000)
  run.send('callback-start', { requestId: '4' })
  assert.equal(h.api.getState().remainingMs, 1000, 'overlapping callbacks share the existing budget')
  run.send('callback-done', { requestId: '3' })
  h.clock.advance(1000); assert.equal(h.api.getState().state, 'stopping')
  assert.equal(h.channels[0].port1.sent.at(-1).type, 'stop')
  run.send('stopped'); assert.equal(h.api.getState().state, 'timeout')
})

test('callbacks during main execution share its remaining budget and a 33rd pending callback ends the run', () => {
  const h = coordinator(); h.api.run('import turtle'); const run = h.boot()
  h.clock.advance(5000); run.send('callback-start', { requestId: '1' }); run.send('done')
  assert.equal(h.api.getState().state, 'running')
  assert.equal(h.api.getState().remainingMs, 25000)
  h.clock.advance(24999); assert.equal(h.api.getState().state, 'running')
  h.clock.advance(1); run.send('stopped'); assert.equal(h.api.getState().state, 'timeout')
  h.api.run('import turtle'); const next = h.boot(); next.send('done')
  for (let id = 1; id <= 32; id++) next.send('callback-start', { requestId: String(id) })
  assert.equal(h.api.getState().state, 'running')
  next.send('callback-start', { requestId: '33' }); assert.equal(h.api.getState().state, 'stopping')
  next.send('stopped'); assert.equal(h.api.getState().state, 'error')
})

test('main completion during callback input is retained and callback completion stops the resumed budget', () => {
  const h = coordinator(); h.api.run('import turtle'); const run = h.boot()
  run.send('callback-start', { requestId: '1' })
  run.send('input', { requestId: '2', prompt: 'callback input before main finished' })
  run.send('done'); assert.equal(h.api.getState().state, 'waiting-input')
  h.clock.advance(40000)
  h.nodes.get('python-execution-input').value = 'resume'
  h.nodes.get('python-execution-input-form').dispatch('submit')
  run.send('callback-done', { requestId: '1' }); assert.equal(h.api.getState().state, 'completed')
  h.clock.advance(40000); assert.equal(h.api.getState().state, 'completed')
})

test('parent output cap preserves normal slow small messages and bounds display after saturation', () => {
  const h = coordinator(); h.api.run('print 42'); const run = h.boot()
  for (let i = 0; i < 100; i++) { run.send('output', { text: 'x' }); h.clock.advance(20) }
  assert.equal(h.output(), 'x'.repeat(100), 'normal slow output is not cut off after an arbitrary message count')
  for (let i = 0; i < 100; i++) run.send('output', { text: 'y'.repeat(2048) })
  const output = require('../public/python/output.js')
  assert.equal(h.output().length, output.maxUnits + output.notice.length)
  const snapshot = h.output()
  for (let i = 0; i < 1000; i++) run.send('output', { text: 'ignored' })
  assert.equal(h.output(), snapshot)
})

test('input form pauses the remaining computation budget, sends only typed text and cancel destroys the runner', () => {
  const h = coordinator(); h.api.run('name = raw_input()'); const run = h.boot()
  h.clock.advance(5000); run.send('input', { requestId: '1', prompt: '<b>姓名：</b>' })
  assert.equal(h.api.getState().state, 'waiting-input'); assert.equal(h.api.getState().remainingMs, 25000)
  assert.equal(h.nodes.get('python-execution-input-prompt').textContent, '<b>姓名：</b>')
  h.clock.advance(60000)
  assert.equal(run.frame.parentNode, h.nodes.get('mycanvas')); assert.equal(h.api.getState().remainingMs, 25000)
  const form = h.nodes.get('python-execution-input-form'), input = h.nodes.get('python-execution-input')
  input.value = 'x'.repeat(4097); form.dispatch('submit')
  assert.equal(h.api.getState().state, 'waiting-input')
  input.value = '中文 + % <b>'; form.dispatch('submit')
  const reply = h.channels[0].port1.sent.find(message => message.type === 'input-result')
  assert.equal(reply.value, '中文 + % <b>'); assert.equal(reply.requestId, '1')
  assert.deepEqual(Object.keys(reply).sort(), ['channel', 'requestId', 'runId', 'type', 'value'])
  assert.equal(form.hidden, true); assert.equal(h.api.getState().state, 'running')
  h.clock.advance(24999); assert.equal(h.api.getState().state, 'running')
  h.clock.advance(1); assert.equal(h.api.getState().state, 'stopping')
  run.send('stopped'); assert.equal(h.api.getState().state, 'timeout'); assert.equal(run.frame.parentNode, null)
  h.api.run('raw_input()'); const next = h.boot(); next.send('input', { requestId: '1', prompt: 'cancel' })
  h.nodes.get('python-execution-input-cancel').dispatch('click')
  assert.equal(h.api.getState().state, 'stopping'); next.send('stopped')
  assert.equal(next.frame.parentNode, null); assert.equal(form.hidden, true)
  assert.equal(h.api.getState().state, 'stopped')
})

test('load failure, compute timeout and immutable five-minute lifetime each clean up the actual frame', () => {
  const h = coordinator()
  h.api.run('print 42'); const loading = h.nodes.get('mycanvas').querySelector('iframe')
  h.clock.advance(10000); assert.equal(h.api.getState().state, 'error'); assert.equal(loading.parentNode, null)
  h.api.run('print 42'); const running = h.boot()
  h.clock.advance(30000); assert.equal(h.api.getState().state, 'stopping'); running.send('stopped')
  assert.equal(h.api.getState().state, 'timeout'); assert.equal(running.frame.parentNode, null)
  h.api.run('import turtle'); const drawing = h.boot(); drawing.send('graphics'); drawing.send('done')
  assert.equal(h.api.getState().state, 'completed')
  h.clock.advance(299999); assert.equal(drawing.frame.parentNode, h.nodes.get('mycanvas'))
  // A completed turtle remains interactive until the independent lifetime ends.
  drawing.send('done'); drawing.send('input', { requestId: '1', prompt: 'cannot extend lifetime' })
  h.clock.advance(1); assert.equal(h.api.getState().state, 'stopping'); drawing.send('stopped')
  assert.equal(h.api.getState().state, 'expired'); assert.equal(drawing.frame.parentNode, null)
})

test('invalid code and unsupported isolation produce explicit errors with no legacy same-origin execution', () => {
  const h = coordinator()
  assert.equal(h.api.run('x'.repeat(256001)), null)
  assert.equal(h.nodes.get('mycanvas').querySelector('iframe'), null)
  assert.equal(h.api.getState().state, 'error')
  h.context.MessageChannel = undefined
  const host = actualComponent('app', h).instance
  assert.doesNotThrow(() => host.runit())
  assert.equal(h.nodes.get('mycanvas').querySelector('iframe'), null)
  assert.equal(h.api.getState().state, 'error')
  assert.match(h.nodes.get('python-execution-status').textContent, /浏览器/)
})

test('Stop without trusted ack preserves the host, reports failure and retries; Clear cancels queued rerun', async () => {
  const h = coordinator(); h.api.run('print 42'); const run = h.boot()
  let resolved = false
  const stopping = h.api.stop().then(() => { resolved = true })
  h.message(run.frame.contentWindow, { channel: CHANNEL, type: 'stopped', runId: run.transfer.data.runId })
  run.port.postMessage({ channel: CHANNEL, type: 'stopped', runId: 'old' })
  h.clock.advance(3999); await flush()
  assert.equal(h.api.getState().state, 'stopping')
  h.clock.advance(1); await flush()
  assert.equal(resolved, false); assert.equal(h.api.getState().state, 'stop-error')
  assert.equal(run.frame.parentNode, h.nodes.get('mycanvas'))
  const before = h.channels[0].port1.sent.filter(packet => packet.type === 'stop').length
  h.api.stop(); assert.equal(h.channels[0].port1.sent.filter(packet => packet.type === 'stop').length, before + 1)
  h.clock.advance(3999); assert.equal(h.api.getState().state, 'stopping', 'a retry gets a fresh acknowledgment wait')
  h.clock.advance(1); assert.equal(h.api.getState().state, 'stop-error'); assert.equal(resolved, false)
  run.send('stopped'); await stopping; assert.equal(run.frame.parentNode, null)
  h.api.run('print "old"'); const next = h.boot()
  h.api.run('print "queued must not run"')
  const clearing = h.api.clear(); next.send('stopped'); await clearing; await flush()
  assert.equal(h.nodes.get('mycanvas').querySelector('iframe'), null)
  assert.equal(h.api.getState().state, 'idle'); assert.equal(h.api.getState().pendingRunId, null)
})

test('trusted renderer host validates bootstrap and transfers student code into one Worker only', () => {
  const h = rendererHost(), payload = { channel: CHANNEL, type: 'run', runId, code: 'print 42' }
  for (const invalid of [
    { source: {}, data: payload, ports: [h.channel.port2] },
    { source: h.context.parent, data: { ...payload, runId: 'wrong' }, ports: [h.channel.port2] },
    { source: h.context.parent, data: { ...payload, code: 'x'.repeat(256001) }, ports: [h.channel.port2] },
    { source: h.context.parent, data: { ...payload, code: {} }, ports: [h.channel.port2] },
    { source: h.context.parent, data: payload, ports: [] }
  ]) h.message(invalid.source, invalid.data, 'http://fixture.test', invalid.ports)
  h.clock.advance(0); assert.equal(h.workers.length, 0)
  h.start(); assert.equal(h.workers.length, 1)
  const worker = h.workers[0], transfer = worker.sent[0]
  assert.equal(transfer.data.code, 'print 42'); assert.equal(transfer.ports.length, 1)
  assert.ok(worker.url.startsWith('blob:'))
  assert.equal(h.configured[0].output, undefined, 'the trusted renderer never receives a student output/input execution callback')
  assert.equal(h.sk.TurtleGraphics.width, 640); assert.equal(h.sk.TurtleGraphics.height, 480)
  h.fromWorker('ready'); h.fromParent('start')
  assert.equal(h.channels[1].port1.sent[0].type, 'start')
  h.start('print 99'); assert.equal(h.workers.length, 1, 'bootstrap cannot create additional computation Workers')
})

test('trusted host calls Worker.terminate, closes results and waits 2500ms before its own stopped ack', () => {
  const h = rendererHost(); h.start(); const worker = h.workers[0]
  h.fromWorker('stopped'); worker.emit('message', { channel: CHANNEL, type: 'stopped', runId })
  assert.equal(h.sent.some(packet => packet.type === 'stopped'), false)
  h.fromParent('stop', { runId: 'old' }); assert.equal(worker.terminated, false)
  h.fromParent('stop')
  assert.equal(worker.terminated, true); assert.deepEqual(h.order, ['terminate'])
  assert.equal(h.disposeCalls, 1); assert.equal(h.blobs.size, 0)
  h.fromWorker('output', { text: 'STALE' }); assert.equal(h.sent.some(packet => packet.text === 'STALE'), false)
  h.fromParent('stop'); assert.equal(worker.terminateCalls, 1, 'idempotent Stop ack does not require re-running computation')
  h.clock.advance(2499); assert.deepEqual(h.order, ['terminate'])
  h.clock.advance(1); assert.deepEqual(h.order, ['terminate', 'stopped'])
  h.fromParent('stop'); assert.equal(h.order.filter(value => value === 'stopped').length, 2)
})

test('trusted host rejects malformed, duplicated, deeply nested RPC and a 33rd pending request', () => {
  const cases = [
    { requestId: 0, op: 'init' }, { requestId: 1, op: 'call', scope: 'module', method: 'write', args: [{ kind: 'str', value: 'x'.repeat(2049) }] },
    { requestId: 1, op: 'call', args: Array(33).fill(null) },
    { requestId: 1, op: 'call', args: [{ value: NaN }] },
    { requestId: 1, op: 'call', args: [Array.from({ length: 9 }).reduce(value => ({ kind: 'list', items: [value] }), { kind: 'none' })] }
  ]
  for (const packet of cases) {
    const h = rendererHost(); h.start(); h.fromWorker('turtle-request', packet)
    assert.equal(h.workers[0].terminated, true); assert.equal(h.requests.length, 0)
    assert.ok(h.sent.some(value => value.type === 'error'))
  }
  const duplicate = rendererHost(); duplicate.start()
  duplicate.fromWorker('turtle-request', { requestId: 1, op: 'init' })
  duplicate.fromWorker('turtle-request', { requestId: 1, op: 'init' })
  assert.equal(duplicate.workers[0].terminated, true); assert.equal(duplicate.requests.length, 1)
  const pending = rendererHost(); pending.start()
  for (let id = 1; id <= 33; id++) pending.fromWorker('turtle-request', { requestId: id, op: 'init' })
  assert.equal(pending.requests.length, 32); assert.equal(pending.workers[0].terminated, true)
})

test('trusted host limits completed RPC rate and recovers by explicit stop acknowledgment after errors', () => {
  const h = rendererHost({ reply: true }); h.start()
  for (let id = 1; id <= 501; id++) h.fromWorker('turtle-request', { requestId: id, op: 'init' })
  assert.equal(h.requests.length, 500); assert.equal(h.workers[0].terminated, true)
  assert.ok(h.sent.some(value => value.type === 'error'))
  h.fromParent('stop'); h.clock.advance(2500)
  assert.equal(h.sent[h.sent.length - 1].type, 'stopped')
})

test('trusted turtle initialization exposes an event surface before lazy drawing; Worker graphics cannot forge it', () => {
  const h = rendererHost({ reply: true }); h.start()
  h.fromWorker('graphics'); assert.equal(h.sent.some(packet => packet.type === 'graphics'), false)
  h.fromWorker('turtle-request', { requestId: 1, op: 'init' })
  assert.equal(h.sent.filter(packet => packet.type === 'graphics').length, 1)
  h.fromWorker('turtle-request', { requestId: 2, op: 'init' })
  assert.equal(h.sent.filter(packet => packet.type === 'graphics').length, 1)
})

test('runner loader registers the inherited bundles without mounting Vue and executes actual Python2 in its own realm', async () => {
  const h = browserEnvironment(), text = []
  h.load('web/public/python/runner-loader.js')
  h.load('web/public/python/static/js/vendor.js')
  h.load('web/public/python/static/js/app.js')
  assert.equal(h.context.Sk, undefined, 'registration does not eagerly execute the engine or either Vue entry')
  const sk = h.context.TeachingPythonRuntime()
  assert.ok(sk.builtinFiles.files['src/lib/turtle.js'])
  assert.equal(h.context.TeachingPythonRuntime, undefined); assert.equal(h.context.webpackJsonp, undefined)
  sk.configure({ output: value => text.push(value), read: name => sk.builtinFiles.files[name], __future__: sk.python2, execLimit: 500, yieldLimit: 100 })
  await sk.misceval.asyncToPromise(() => sk.importMainWithBody('<stdin>', false, 'print 6 * 7\nprint sum(range(10000))\n', true))
  assert.equal(text.join(''), '42\n49995000\n')
  assert.equal(h.document.body.children.length, 2, 'no Vue entry mounted into the fixture')
})

test('both public entry points load coordinator before the component bundles and expose no fallback runtime runner', () => {
  for (const page of ['index', 'player']) {
    const html = readSource('web/public/python/' + page + '.html')
    assert.ok(html.indexOf('./execution.js') >= 0)
    const entry = './static/js/' + (page === 'index' ? 'app' : 'appPlayer') + '.js'
    assert.ok(html.indexOf(entry) >= 0)
    assert.ok(html.indexOf('./execution.js') < html.indexOf(entry))
  }
})

module.exports = { CHANNEL, runId, flush }
