const assert = require('node:assert/strict')
const { test } = require('node:test')
const { realRenderer, realWorker, flush } = require('./python-execution-frame/runtime-fixture.cjs')
const number = value => ({ kind: Number.isInteger(value) ? 'int' : 'float', value })
const string = value => ({ kind: 'str', value })

test('actual renderer preserves original turtle schema, typed return values, references and undo', async () => {
  const h = realRenderer()
  try {
    const init = await h.request({ op: 'init' })
    assert.deepEqual(Object.fromEntries(Object.entries(init.schema).map(([scope, methods]) => [scope, Object.keys(methods).length])), { module: 73, Turtle: 72, Screen: 26 })
    const created = await h.request({ op: 'create', scope: 'Turtle', args: [string('classic')] })
    assert.equal(created.value.kind, 'ref'); assert.equal(created.value.scope, 'Turtle')
    const turtle = created.value.objectId
    const call = (method, args = []) => h.request({ op: 'call', scope: 'Turtle', objectId: turtle, method, args })
    assert.equal((await call('speed', [number(0)])).error, undefined)
    await call('setundobuffer', [number(100)])
    await call('forward', [number(35.5)])
    const position = (await call('position')).value
    assert.equal(position.kind, 'tuple'); assert.equal(position.items[0].value, 35.5); assert.equal(position.items[1].value, 0)
    await call('undo')
    assert.equal((await call('position')).value.items[0].value, 0)
    const screen = (await call('getscreen')).value
    assert.equal(screen.kind, 'ref'); assert.equal(screen.scope, 'Screen')
    const again = (await h.request({ op: 'create', scope: 'Screen', args: [] })).value
    assert.notEqual(again.objectId, screen.objectId, 'the inherited engine returns distinct Screen Python wrappers')
    const turtles = (await h.request({ op: 'call', scope: 'Screen', objectId: screen.objectId, method: 'turtles', args: [] })).value
    assert.equal(turtles.kind, 'tuple'); assert.ok(turtles.items.some(value => value.objectId === turtle))
  } finally { h.bridge.dispose() }
})

test('actual renderer emits typed timer callback events and disposes pending callbacks', async () => {
  const h = realRenderer()
  await h.request({ op: 'init' })
  const screen = (await h.request({ op: 'create', scope: 'Screen', args: [] })).value.objectId
  const timer = callbackId => h.request({ op: 'call', scope: 'Screen', objectId: screen, method: 'ontimer', args: [{ kind: 'callback', callbackId }, number(100)] })
  assert.equal((await timer(1)).error, undefined)
  await h.pump(() => h.packets.some(packet => packet.type === 'turtle-event' && packet.callbackId === 1))
  const event = h.packets.find(packet => packet.type === 'turtle-event')
  assert.deepEqual(Array.from(event.args), [])
  await timer(2); h.bridge.dispose(); h.clock.advance(1000); await flush()
  assert.equal(h.packets.some(packet => packet.type === 'turtle-event' && packet.callbackId === 2), false)
})

test('actual renderer rejects unsupported or amplified calls and remains usable after each ValueError', async () => {
  const h = realRenderer()
  try {
    await h.request({ op: 'init' })
    const turtle = (await h.request({ op: 'create', scope: 'Turtle', args: [] })).value.objectId
    const call = (method, args = [], fields = {}) => h.request({ op: 'call', scope: 'Turtle', objectId: turtle, method, args, ...fields })
    const bad = [
      ['constructor', []], ['__proto__', []], ['position', [], { scope: 'unknown' }],
      ['position', [], { objectId: 999 }], ['forward', [{ kind: 'int', value: 1.5 }]],
      ['forward', [{ kind: 'float', value: Infinity }]], ['forward', [string('35')]],
      ['forward', [number(1000001)]], ['write', [string('x'.repeat(2049))]],
      ['forward', [{ kind: 'list', items: Array(33).fill(number(1)) }]],
      ['forward', [Array.from({ length: 9 }).reduce(value => ({ kind: 'tuple', items: [value] }), number(1))]],
      ['onclick', [{ kind: 'callback', callbackId: 1025 }]],
      ['circle', [number(50), number(360), number(721)]], ['setundobuffer', [number(101)]],
      ['pensize', [number(257)]], ['dot', [number(257)]],
      ['write', [string('text'), { kind: 'none' }, { kind: 'none' }, { kind: 'tuple', items: [string('Arial'), number(129), string('normal')] }]],
      ['forward', [number(1000000)]]
    ]
    for (const [method, args, fields] of bad) {
      const reply = await call(method, args, fields)
      assert.ok(reply.error, method + ' rejects invalid or excessive parameters')
      assert.equal(reply.error.name, 'ValueError')
      assert.equal((await call('position')).error, undefined, 'valid request still works after rejected ' + method)
    }
  } finally { h.bridge.dispose() }
})

test('derived circle steps and moving text are bounded before original methods can allocate animation chains', async () => {
  const h = realRenderer()
  try {
    await h.request({ op: 'init' })
    const turtle = (await h.request({ op: 'create', scope: 'Turtle', args: [] })).value.objectId
    const call = (method, args = []) => h.request({ op: 'call', scope: 'Turtle', objectId: turtle, method, args })
    let circles = 0, writes = 0
    // Instrument the original raw methods. Huge cases must never enter them;
    // allowed boundaries only count the call, without allocating a long chain.
    const proto = h.sk.TurtleGraphics.raw.Turtle.prototype
    proto.$circle = function () { circles++ }
    proto.$write = function () { writes++ }
    await call('speed', [number(0)]); await call('degrees', [number(1)])
    assert.equal((await call('circle', [number(0), number(65.4)])).error, undefined)
    assert.equal(circles, 1, 'derived 720-step boundary reaches the original method')
    assert.match((await call('circle', [number(0), number(65.5)])).error.message, /720/)
    assert.equal(circles, 1, 'derived 721-step case is rejected before entering the original method')
    await call('degrees', [number(0.001)])
    assert.match((await call('circle', [number(1), number(3600)])).error.message, /720/)
    assert.equal(circles, 1, '40-million-step old-engine case never runs')
    assert.equal((await call('circle', [number(1), number(3600), number(720)])).error, undefined)
    assert.equal(circles, 2, 'explicit bounded steps remain available with small degree units and speed zero')
    const text = [string('moving text'), { kind: 'bool', value: true }, string('left'), { kind: 'tuple', items: [string('Arial'), number(12), string('normal')] }]
    assert.equal((await call('write', text)).error, undefined); assert.equal(writes, 1)
    await call('speed', [number(0.500001)])
    assert.match((await call('write', text)).error.message, /2048/)
    assert.equal(writes, 1, 'near-zero animation speed cannot enter original moving write')
  } finally { h.bridge.dispose() }
})

test('actual Worker start handshake gates finite Python2 execution and batches bounded literal output', async () => {
  const h = realWorker('print 6 * 7\nprint "<b>literal & 中文</b>"\nprint "x" * 100000\n', { renderer: false, thenables: true })
  try {
    assert.ok(h.packets.some(packet => packet.type === 'ready'))
    h.clock.advance(200); await flush(); assert.equal(h.output(), '')
    h.send('start', { runId: 'old' }); h.clock.advance(0); assert.equal(h.output(), '')
    h.start(); h.start()
    await h.pump(() => h.packets.some(packet => packet.type === 'done'))
    assert.equal(h.errors().length, 0)
    assert.ok(h.output().startsWith('42\n<b>literal & 中文</b>\n'))
    assert.ok(h.output().length <= 20001)
    assert.ok(h.packets.filter(packet => packet.type === 'output').every(packet => typeof packet.text === 'string' && packet.text.length <= 2048))
    assert.equal(h.packets.filter(packet => packet.type === 'done').length, 1)
    assert.equal(h.context.Worker, undefined); assert.equal(h.context.SharedWorker, undefined); assert.equal(h.context.importScripts, undefined)
  } finally { h.dispose() }
})

test('actual Worker input accepts only the current typed response and compensates Skulpt execution time after long wait', async () => {
  const h = realWorker('name = raw_input("姓名：")\nprint name\nprint sum(range(10000))\n', { renderer: false })
  try {
    h.start(); await h.pump(() => h.packets.some(packet => packet.type === 'input'))
    const input = h.packets.find(packet => packet.type === 'input'), sk = h.context.Sk
    const before = +sk.execStart
    h.clock.advance(60000)
    for (const fields of [{ requestId: 'old', value: 'STALE' }, { requestId: input.requestId, value: {} }, { requestId: input.requestId, value: 'x'.repeat(4097) }]) h.send('input-result', fields)
    await flush(); assert.equal(h.packets.some(packet => packet.type === 'resumed'), false)
    h.send('input-result', { requestId: input.requestId, value: '中文 + % <b>' })
    assert.ok(+sk.execStart >= before + 60000, 'the inherited Skulpt timeout origin moves by the actual input wait')
    await h.pump(() => h.packets.some(packet => packet.type === 'done') || h.errors().length)
    assert.equal(h.errors().length, 0); assert.equal(h.output(), '中文 + % <b>\n49995000\n')
    assert.equal(h.packets.filter(packet => packet.type === 'resumed').length, 1)
  } finally { h.dispose() }
})

test('actual Python turtle proxies preserve kwargs, tuples, object identity and caught renderer errors', async () => {
  const h = realWorker('import turtle\nt = turtle.Turtle()\nt.speed(0)\nt.forward(25.5)\nprint t.position()\ns = turtle.Screen()\nprint t.getscreen() is s\nprint t in s.turtles()\nt.write("中文", move=True, align="center", font=("Arial", 12, "normal"))\ntry:\n    t.pensize(257)\nexcept ValueError:\n    print "caught limit"\nprint t.pensize()\nprint "finished"\n')
  try {
    h.start(); await h.pump(() => h.packets.some(packet => packet.type === 'done') || h.errors().length)
    assert.equal(h.errors().length, 0); assert.match(h.output(), /^\(25\.5, 0\.0\)\nFalse\nTrue\n/)
    assert.match(h.output(), /caught limit\n.*\nfinished\n/)
    const write = h.packets.find(packet => packet.type === 'turtle-request' && packet.method === 'write')
    assert.equal(write.args[1].kind, 'bool'); assert.equal(write.args[1].value, true)
    assert.equal(write.args[3].kind, 'tuple')
    assert.equal(h.renderer.packets.some(packet => packet.type === 'turtle-result' && packet.error), true)
  } finally { h.dispose() }
})

test('actual post-main turtle callback runs in Worker with a fresh budget, can wait for input and resume drawing', async () => {
  const h = realWorker('import turtle\ns = turtle.Screen()\ndef click(x, y):\n    name = raw_input("callback:")\n    turtle.speed(0)\n    turtle.goto(x, y)\n    print name, turtle.position()\ns.onclick(click)\nprint "registered"\n')
  try {
    h.start(); await h.pump(() => h.packets.some(packet => packet.type === 'done') || h.errors().length)
    assert.equal(h.errors().length, 0)
    const registration = h.packets.find(packet => packet.type === 'turtle-request' && packet.method === 'onclick')
    assert.equal(registration.args[0].kind, 'callback')
    h.clock.advance(40000)
    h.send('turtle-event', { callbackId: registration.args[0].callbackId, args: [number(13.5), number(7)] })
    await h.pump(() => h.packets.some(packet => packet.type === 'input'))
    const input = h.packets.find(packet => packet.type === 'input')
    h.clock.advance(60000); h.send('input-result', { requestId: input.requestId, value: 'callback resumed' })
    await h.pump(() => h.output().includes('callback resumed'))
    assert.equal(h.errors().length, 0); assert.match(h.output(), /callback resumed \(13\.5, 7\.0\)/)
    await h.pump(() => h.packets.some(packet => packet.type === 'callback-done'))
    const start = h.packets.find(packet => packet.type === 'callback-start'), done = h.packets.find(packet => packet.type === 'callback-done')
    assert.match(start.requestId, /^[0-9]+$/); assert.equal(start.requestId, done.requestId)
    assert.equal(h.packets.filter(packet => packet.type === 'callback-start').length, 1)
    assert.equal(h.packets.filter(packet => packet.type === 'callback-done').length, 1)
  } finally { h.dispose() }
})

test('actual Worker serializes turtle events behind main input and bounds the pending event queue', async () => {
  const h = realWorker('import turtle\ns=turtle.Screen()\ndef click(x,y):\n    name=raw_input("event:")\n    print "event " + name\ns.onclick(click)\nprint raw_input("main:")\n')
  try {
    h.start(); await h.pump(() => h.packets.some(packet => packet.type === 'input'))
    const registration = h.packets.find(packet => packet.type === 'turtle-request' && packet.method === 'onclick')
    const event = () => h.send('turtle-event', { callbackId: registration.args[0].callbackId, args: [number(0), number(0)] })
    event(); event(); event(); await flush()
    assert.equal(h.packets.filter(packet => packet.type === 'callback-start').length, 0, 'main input holds queued event callbacks')
    h.send('input-result', { requestId: h.packets.find(packet => packet.type === 'input').requestId, value: 'main continued' })
    for (let id = 0; id < 3; id++) {
      await h.pump(() => h.packets.filter(packet => packet.type === 'input').length >= id + 2)
      assert.equal(h.packets.filter(packet => packet.type === 'callback-start').length, id + 1)
      const input = h.packets.filter(packet => packet.type === 'input')[id + 1]
      h.send('input-result', { requestId: input.requestId, value: String(id) })
    }
    await h.pump(() => h.packets.filter(packet => packet.type === 'callback-done').length === 3)
    assert.equal(h.errors().length, 0); assert.match(h.output(), /event 0\nevent 1\nevent 2\n/)
    event(); await h.pump(() => h.packets.filter(packet => packet.type === 'input').length === 5)
    for (let id = 0; id < 33; id++) event()
    assert.equal(h.errors().length, 1); assert.match(h.errors()[0], /32/)
  } finally { h.dispose() }
})
