const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { resolve } = require('node:path')
const test = require('node:test')
const vm = require('node:vm')

function harness () {
  const sockets = []
  const timers = new Map()
  let nextTimer = 0
  let token = 'fixture-credential-a'
  let notices = 0
  class Socket {
    constructor (url) { this.url = url; this.readyState = 1; this.sent = []; this.closed = false; sockets.push(this) }
    send (value) { this.sent.push(value) }
    close () { this.closed = true }
    message (value) { if (this.onmessage) this.onmessage({ data: typeof value === 'string' ? value : JSON.stringify(value) }) }
    disconnect (code) { this.onclose({ code }) }
  }
  const ctx = { URL, WebSocket: Socket, setTimeout: (fn, ms) => { const id = ++nextTimer; timers.set(id, { fn, ms }); return id }, clearTimeout: id => timers.delete(id) }
  vm.createContext(ctx)
  const source = readFileSync(resolve(__dirname, '../src/utils/notificationSocket.js'), 'utf8')
  vm.runInContext(source.replace('export function ', 'function ') + '\nthis.create = createNotificationSocket', ctx)
  const start = () => ctx.create({ baseUrl: '/api?ignored=credential', pageUrl: 'https://school.example/index', userId: 'fixture student', getToken: () => token, onNotice: () => notices++ })
  const fire = ms => { for (const [id, timer] of [...timers]) if (timer.ms === ms) { timers.delete(id); timer.fn() } }
  return { ctx, sockets, timers, start, fire, setToken: value => { token = value }, notices: () => notices }
}

test('credential travels only in the first frame; valid acknowledgement enables notices', () => {
  const h = harness(); const connection = h.start(); const s = h.sockets[0]
  assert.equal(s.url, 'wss://school.example/api/websocket/fixture%20student')
  assert.equal(s.sent.length, 0); s.onopen()
  assert.deepEqual(JSON.parse(s.sent[0]), { type: 'authenticate', token: 'fixture-credential-a' })
  s.message({ cmd: 'authenticated' }); s.message({ cmd: 'user' }); s.message({ cmd: 'topic' }); s.message({ cmd: 'heartcheck' })
  assert.equal(h.notices(), 2); connection.stop(); assert.equal(h.timers.size, 0)
})

test('notification before authentication is not accepted', () => {
  const h = harness(); h.start(); const s = h.sockets[0]; s.onopen(); s.message({ cmd: 'user' })
  assert.equal(h.notices(), 0); assert.equal(s.closed, true)
})

test('message syntax cannot execute JavaScript', () => {
  const h = harness(); h.start(); const s = h.sockets[0]; s.onopen(); s.message({ cmd: 'authenticated' })
  s.message('(globalThis.executed = true, {cmd:"user"})')
  assert.equal(h.ctx.executed, undefined); assert.equal(h.notices(), 0); assert.equal(s.closed, true)
})

test('account switch before opening does not send either credential', () => {
  const h = harness(); h.start(); const s = h.sockets[0]; h.setToken('fixture-credential-b'); s.onopen()
  assert.equal(s.sent.length, 0); assert.equal(s.closed, true)
})

test('logout suppresses old-socket notifications and heartbeat', () => {
  const h = harness(); h.start(); const s = h.sockets[0]; s.onopen(); s.message({ cmd: 'authenticated' })
  h.setToken(null); s.message({ cmd: 'user' }); h.fire(20000)
  assert.equal(h.notices(), 0); assert.equal(s.sent.length, 1); assert.equal(s.closed, true)
})

test('network closure reconnects and authenticates the same session again', () => {
  const h = harness(); h.start(); const s = h.sockets[0]; s.onopen(); s.message({ cmd: 'authenticated' }); s.disconnect(1006)
  h.fire(5000); assert.equal(h.sockets.length, 2); h.sockets[1].onopen()
  assert.equal(JSON.parse(h.sockets[1].sent[0]).token, 'fixture-credential-a')
})

test('account change during retry never subscribes using the new credential and old user ID', () => {
  const h = harness(); h.start(); h.sockets[0].disconnect(1006); h.setToken('fixture-credential-b'); h.fire(5000)
  assert.equal(h.sockets.length, 1); assert.equal(h.timers.size, 0)
})

test('policy rejection does not create a reconnect loop', () => {
  const h = harness(); h.start(); h.sockets[0].disconnect(1008); h.fire(5000)
  assert.equal(h.sockets.length, 1); assert.equal(h.timers.size, 0)
})

test('authentication deadline and explicit disposal close sockets and timers', () => {
  const h = harness(); h.start(); h.fire(10000); assert.equal(h.sockets[0].closed, true)
  const active = h.start(); const s = h.sockets[1]; s.onopen(); s.message({ cmd: 'authenticated' }); h.fire(20000)
  assert.equal(s.sent.at(-1), 'HeartBeat'); active.stop(); assert.equal(s.closed, true); assert.equal(h.timers.size, 0)
})

test('missing login state never opens a subscription', () => {
  const h = harness(); h.setToken(null); h.start(); assert.equal(h.sockets.length, 0)
})

test('shipped notification component binds credentials and disposes its optional connection', () => {
  const source = readFileSync(resolve(__dirname, '../src/components/tools/HeaderNotice.vue'), 'utf8').split('<script>')[1].split('</script>')[0]
  let options; let oldStopped = false; let newStopped = false
  const context = { ShowAnnouncement: {}, DynamicNotice: {}, store: { getters: { userInfo: { id: 'fixture_student_a' } } },
    Vue: { ls: { get: () => 'fixture-session' } }, ACCESS_TOKEN: 'token', window: { _CONFIG: { domianURL: '/api' }, location: { href: 'https://school.example/index' } },
    createNotificationSocket: value => { options = value; return { stop: () => { newStopped = true } } } }
  vm.createContext(context)
  vm.runInContext(source.replace(/^\s*import .*$/gm, '').replace('export default', 'this.component ='), context)
  const component = context.component; let loads = 0
  const instance = { noticeConnection: { stop: () => { oldStopped = true } }, loadData: () => loads++ }
  component.methods.initWebSocket.call(instance)
  assert.equal(oldStopped, true); assert.equal(options.userId, 'fixture_student_a'); assert.equal(options.getToken(), 'fixture-session')
  options.onNotice(); assert.equal(loads, 1); component.destroyed.call(instance)
  assert.equal(newStopped, true); assert.equal(instance.stopTimer, true)
})
