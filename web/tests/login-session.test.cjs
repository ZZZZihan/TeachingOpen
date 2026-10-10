const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { resolve } = require('node:path')
const vm = require('node:vm')
const { test } = require('node:test')
const Vue = require('vue')
const Vuex = require('vuex')
Vue.use(Vuex)
const source = file => readFileSync(resolve(__dirname, '../src', file), 'utf8')
const strip = text => text.replace(/^import .*$/gm, '')
const run = (text, context) => { vm.runInNewContext(text, context); return context }
const helper = run(source('utils/session.js').replace(/export /g, ''), {})
const flush = () => new Promise(resolve => setImmediate(resolve))
const deferred = () => { let resolve, reject; const promise = new Promise((a, b) => { resolve = a; reject = b }); return { promise, resolve, reject } }
const goodCaptcha = { success: true, result: 'data:image/png;base64,fixture' }

function loginHarness (captchaApi = () => Promise.resolve(goodCaptcha)) {
  const script = source('views/user/Login.vue').match(/<script>([\s\S]*?)<\/script>/)[1]
  const context = run(strip(script).replace('export default', 'this.component ='), { ...helper, getLoginCaptcha: captchaApi })
  const calls = []; const navigation = []; let focus = ''
  const pending = deferred()
  const component = new Vue({ ...context.component, beforeCreate () {
    this.$route = { params: {}, query: { redirect: '/courseList?q=one%20two#results' } }
    this.$router = { replace: async path => { navigation.push(path) } }
    this.$store = { getters: { sysConfig: {} }, dispatch: (name, payload) => { calls.push({ name, payload }); return pending.promise } }
  } })
  for (const key of ['username', 'password', 'captcha', 'submitError']) component.$refs[key] = { focus () { focus = key } }
  return { component, calls, navigation, pending, get focus () { return focus } }
}

test('local return paths preserve query/hash, unsafe and login-loop targets fall back', () => {
  for (const input of [undefined, ['//x'], 'https://evil.test', '//evil.test', '/\\evil.test', '/%2f%2fevil.test', '/%255cevil', '/user/login', '/user/session?a=1', '/%75ser/login', '/x/../user/login', '/x/%2e%2e/user/login', '/%zz', '/\n/index']) assert.equal(helper.safeRedirect(input), '/index', String(input))
  for (const input of ['/index', '/courseList?q=one%20two#results', '/teaching/course?id=x']) assert.equal(helper.safeRedirect(input), input)
})
test('login validation moves focus to first missing field without network submission', async () => {
  const h = loginHarness(); await flush(); await h.component.submit(); await Vue.nextTick()
  assert.equal(h.calls.length, 0); assert.equal(h.focus, 'username')
  h.component.username = 'fixture_student_a'; await h.component.submit(); await Vue.nextTick()
  assert.equal(h.focus, 'password'); h.component.$destroy()
})
test('pending login is single-flight, successful login clears password and restores full path', async () => {
  const h = loginHarness(); await flush()
  Object.assign(h.component, { username: ' fixture_student_a ', password: 'fixture-only', captcha: ' ab12 ' })
  const first = h.component.submit(); await h.component.submit()
  assert.equal(h.calls.length, 1); assert.equal(h.calls[0].payload.username, 'fixture_student_a'); assert.equal(h.component.submitting, true)
  h.pending.resolve({ success: true }); await first
  assert.equal(h.component.password, ''); assert.equal(h.navigation[0], '/courseList?q=one%20two#results')
  h.component.$destroy()
})
test('failed login remains on form, retains account, refreshes consumed captcha and announces inline error', async () => {
  let requests = 0
  const h = loginHarness(() => { requests++; return Promise.resolve(goodCaptcha) }); await flush()
  Object.assign(h.component, { username: 'fixture_student_a', password: 'fixture-only', captcha: 'ab12' })
  const pending = h.component.submit(); h.pending.reject({ message: '验证码错误' }); await pending; await Vue.nextTick()
  assert.equal(requests, 2); assert.equal(h.component.captcha, ''); assert.equal(h.component.username, 'fixture_student_a')
  assert.equal(h.component.submitting, false); assert.equal(h.component.submitError, '验证码错误'); assert.equal(h.focus, 'submitError'); assert.equal(h.navigation.length, 0)
  h.component.$destroy()
})
test('captcha connection failure is retryable and stale response cannot replace a newer image', async () => {
  const requests = []
  const h = loginHarness(() => { const d = deferred(); requests.push(d); return d.promise })
  requests[0].reject(new Error('offline')); await flush()
  assert.match(h.component.captchaError, /重试/); assert.equal(h.component.captchaLoading, false)
  h.component.errors = { captcha: '请输入验证码。' }
  const old = h.component.refreshCaptcha(); assert.equal(h.component.errors.captcha, ''); const latest = h.component.refreshCaptcha()
  requests[2].resolve({ success: true, result: 'data:image/png;base64,new' }); await latest
  requests[1].resolve(goodCaptcha); await old
  assert.equal(h.component.captchaImage, 'data:image/png;base64,new'); h.component.$destroy()
})
test('unmounted login ignores late captcha and successful navigation', async () => {
  const d = deferred(); const h = loginHarness(() => d.promise)
  h.component.$destroy(); d.resolve(goodCaptcha); await flush()
  assert.equal(h.component.captchaImage, '')
})
test('network errors give actionable feedback without exposing server stack details', () => {
  assert.match(helper.loginErrorMessage({ isAxiosError: true }), /检查网络/)
  assert.match(helper.loginErrorMessage({ request: {}, message: 'Network Error' }), /检查网络/)
  assert.match(helper.loginErrorMessage({ code: 'ECONNABORTED' }), /超时/)
  assert.equal(helper.loginErrorMessage({ response: { status: 500, data: { message: 'SQL credentials here' } } }), '服务暂时不可用，请稍后重试。')
})

const keys = ['ACCESS_TOKEN', 'USER_NAME', 'USER_INFO', 'USER_ROLE', 'USER_AUTH', 'SYS_BUTTON_AUTH', 'UI_CACHE_DB_DICT_DATA', 'MENU']
function userHarness () {
  const cache = new Map(keys.map(key => [key, key === 'ACCESS_TOKEN' ? 'fixture-token' : ['stale']]))
  cache.set('SYS_CONFIG', { brandName: 'Keep branding' })
  const session = new Map(keys.map(key => [key, 'stale']))
  const calls = { permission: [], login: [], logout: [] }; let resets = 0
  const context = { Vue: { ls: { get: key => cache.get(key), set: (key, value) => cache.set(key, value), remove: key => cache.delete(key) } },
    sessionStorage: { setItem: (key, value) => session.set(key, value), removeItem: key => session.delete(key) },
    axios: options => { const d = deferred(); calls.permission.push({ ...d, options }); return d.promise },
    login: payload => { const d = deferred(); calls.login.push({ ...d, payload }); return d.promise },
    logout: token => { const d = deferred(); calls.logout.push({ ...d, token }); return d.promise },
    resetRouter: () => { resets++ }, welcome: () => 'welcome', ...Object.fromEntries(keys.map(key => [key, key])) }
  run(strip(source('store/modules/user.js')).replace('export default user', 'this.user = user'), context)
  const store = new Vuex.Store({ modules: { user: context.user }, mutations: { SET_ROUTERS: (state, value) => { state.routes = value } } })
  return { store, cache, session, calls, get resets () { return resets } }
}
test('logout after refresh sends persisted token and synchronously clears roles, routes and button auth even offline', async () => {
  const h = userHarness(); Object.assign(h.store.state.user, { userRole: ['admin'], permissionList: ['old'], permissionsLoaded: true })
  const pending = h.store.dispatch('Logout')
  assert.equal(h.calls.logout[0].token, 'fixture-token'); assert.equal(h.cache.has('ACCESS_TOKEN'), false)
  assert.equal(h.store.state.user.userRole.length, 0); assert.equal(h.store.state.user.permissionsLoaded, false); assert.equal(h.resets, 1)
  for (const key of keys) { assert.equal(h.cache.has(key), false); assert.equal(h.session.has(key), false) }
  assert.equal(h.cache.get('SYS_CONFIG').brandName, 'Keep branding')
  h.calls.logout[0].reject(new Error('offline')); await pending
})
test('empty menus are accepted; malformed permission data does not overwrite existing auth', async () => {
  const h = userHarness(); const p = h.store.dispatch('GetPermissionList')
  assert.equal(h.calls.permission[0].options.params, undefined)
  assert.equal(JSON.stringify(h.calls.permission[0].options).includes('fixture-token'), false)
  h.calls.permission[0].resolve({ success: true, result: { menu: [], auth: [], allAuth: [] } }); await p
  assert.equal(h.store.state.user.permissionList.length, 0); assert.equal(h.session.get('USER_AUTH'), '[]')
  for (const result of [null, { menu: null }, { menu: [], auth: {}, allAuth: [] }]) {
    const bad = h.store.dispatch('GetPermissionList'); const rejected = assert.rejects(bad)
    h.calls.permission.at(-1).resolve({ success: true, result }); await rejected
    assert.equal(h.session.get('USER_AUTH'), '[]'); assert.equal(h.cache.get('ACCESS_TOKEN'), 'fixture-token')
  }
})
test('late permission response after logout cannot restore previous account authority', async () => {
  const h = userHarness(); const p = h.store.dispatch('GetPermissionList'); const rejected = assert.rejects(p)
  await h.store.dispatch('ClearSession')
  h.calls.permission[0].resolve({ success: true, result: { menu: ['old-admin'], auth: ['delete'], allAuth: [] } }); await rejected
  assert.equal(h.store.state.user.permissionList.length, 0); assert.equal(h.session.has('USER_AUTH'), false)
})
test('cancelled login cannot resurrect a session and successful account switch drops stale privileges', async () => {
  const h = userHarness(); const p = h.store.dispatch('Login', {}); const rejected = assert.rejects(p)
  await h.store.dispatch('ClearSession')
  const response = { code: 200, result: { token: 'new-token', userInfo: { username: 'fixture_student_a' }, role: ['student'] } }
  h.calls.login[0].resolve(response); await rejected
  assert.equal(h.cache.has('ACCESS_TOKEN'), false)
  const next = h.store.dispatch('Login', {}); h.calls.login[1].resolve(response); await next
  assert.equal(h.cache.get('ACCESS_TOKEN'), 'new-token'); assert.equal(h.store.state.user.userRole[0], 'student')
  assert.equal(h.store.state.user.permissionList.length, 0)
})

function requestHarness () {
  let token = 'fixture-token'; let clears = 0
  const hooks = {}; const notices = []; const errors = []; const navigations = []
  const context = { Vue: { ls: { get: () => token } }, ACCESS_TOKEN: 'token', window: { _CONFIG: {} },
    store: { dispatch: name => { assert.equal(name, 'ClearSession'); clears++; token = null } },
    router: { currentRoute: { fullPath: '/teaching/work?id=123#editor' }, push: path => navigations.push(path) },
    axios: { create: () => ({ interceptors: { request: { use: fn => { hooks.request = fn } }, response: { use: (ok, err) => { hooks.error = err } } } }) },
    Modal: { confirm: options => { notices.push(options); return { destroy () {} } } }, notification: { error: options => errors.push(options) }, safeRedirect: helper.safeRedirect }
  run(strip(source('utils/request.js')).replace(/export \{[^}]+\}/, ''), context)
  const rejection = (status = 401, options = {}) => hooks.error({ config: { headers: { 'X-Access-Token': 'fixture-token' }, ...options }, response: { status, data: {} } }).catch(() => {})
  return { hooks, rejection, notices, errors, navigations, setToken: value => { token = value }, get clears () { return clears } }
}
test('parallel expired requests produce one notice, keep page until choice, and retain return URL', async () => {
  const h = requestHarness(); await Promise.all([h.rejection(), h.rejection(), h.rejection()])
  assert.equal(h.clears, 1); assert.equal(h.notices.length, 1); assert.equal(h.navigations.length, 0)
  h.notices[0].onOk(); assert.equal(h.navigations[0].query.redirect, '/teaching/work?id=123#editor')
  assert.match(h.notices[0].content, /复制尚未保存/)
})
test('late 401 from previous account cannot clear a new session', async () => {
  const h = requestHarness(); h.setToken('new-token'); await h.rejection()
  assert.equal(h.clears, 0); assert.equal(h.notices.length, 0)
})
test('login errors stay local; 403 does not log out; menu 401 clears without duplicate modal', async () => {
  const h = requestHarness(); await h.rejection(401, { skipSession: true, localError: true })
  assert.equal(h.clears, 0); assert.equal(h.errors.length, 0)
  await h.rejection(403); assert.equal(h.clears, 0); assert.equal(h.errors.length, 1)
  await h.rejection(401, { skipSessionNotice: true }); assert.equal(h.clears, 1); assert.equal(h.notices.length, 0)
})
test('auth requests do not attach stale token; logout retains explicit token', () => {
  const h = requestHarness()
  assert.equal(h.hooks.request({ skipSession: true, method: 'post' }).headers['X-Access-Token'], undefined)
  assert.equal(h.hooks.request({ skipSession: true, method: 'post', headers: { 'X-Access-Token': 'logout-token' } }).headers['X-Access-Token'], 'logout-token')
})

function guardHarness () {
  let token = 'fixture-token'; let guard; const requests = []; const routes = []
  const state = { user: { permissionsLoaded: false } }; let done = 0
  const context = { Vue: { ls: { get: () => token } }, ACCESS_TOKEN: 'token', safeRedirect: helper.safeRedirect,
    router: { beforeEach: fn => { guard = fn }, afterEach: () => {}, onError: () => {}, addRoutes: data => routes.push(data) },
    store: { state, commit: (key, value) => { if (key === 'SET_PERMISSIONS_LOADED') state.user.permissionsLoaded = value }, dispatch: () => { const d = deferred(); requests.push(d); return d.promise } },
    generateIndexRouter: data => data, NProgress: { configure () {}, start () {}, done () { done++ } } }
  run(strip(source('permission.js')), context)
  const navigate = async path => { const outcomes = []; await guard({ path: path.split(/[?#]/)[0], fullPath: path, query: {} }, { query: {} }, v => outcomes.push(v)); return outcomes }
  return { navigate, requests, routes, state, setToken: value => { token = value }, get done () { return done } }
}
test('public routes remain usable while permission service is unavailable', async () => {
  const h = guardHarness(); assert.deepEqual(await h.navigate('/courseList?q=test'), [undefined]); assert.equal(h.requests.length, 0)
})
test('protected cold entry keeps query/hash, loads once even with concurrent navigation and empty menu', async () => {
  const h = guardHarness(); const a = h.navigate('/teaching/course?id=x#unit'); const b = h.navigate('/teaching/course?id=x#unit')
  assert.equal(h.requests.length, 1); h.requests[0].resolve({ result: { menu: [] } })
  const result = await a; await b
  assert.equal(result[0].path, '/teaching/course?id=x#unit'); assert.equal(h.routes.length, 1)
  assert.deepEqual(await h.navigate('/teaching/course?id=x#unit'), [undefined])
})
test('permission failure finishes navigation on recovery page, keeps session, retries fresh request', async () => {
  const h = guardHarness(); const p = h.navigate('/teaching/course?id=x#unit'); h.requests[0].reject(new Error('offline'))
  const result = await p; assert.equal(result[0].path, '/user/session'); assert.equal(result[0].query.redirect, '/teaching/course?id=x#unit')
  assert.deepEqual(await h.navigate('/user/session'), [undefined])
  const retry = h.navigate('/teaching/course?id=x#unit'); assert.equal(h.requests.length, 2)
  h.requests[1].resolve({ result: { menu: [] } }); await retry
})
test('auth failure redirects to login and changed-account response cannot register old routes', async () => {
  const h = guardHarness(); const a = h.navigate('/teaching/course?id=x'); h.setToken(null); h.requests[0].reject(new Error('401'))
  assert.equal((await a)[0].path, '/user/login'); assert.equal(h.routes.length, 0)
  h.setToken('account-b'); const b = h.navigate('/teaching/course'); h.setToken('account-c'); h.requests[1].resolve({ result: { menu: ['old'] } })
  assert.equal((await b)[0], false); assert.equal(h.routes.length, 0)
})
