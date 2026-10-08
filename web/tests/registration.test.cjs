const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { resolve } = require('node:path')
const vm = require('node:vm')
const { test } = require('node:test')
const Vue = require('vue')
const read = path => readFileSync(resolve(__dirname, '../src', path), 'utf8')
const helpers = {}
vm.runInNewContext(read('utils/accountRecovery.js').replace(/export /g, '') + read('utils/registration.js').replace(/export const /g, 'var ').replace(/export /g, ''), helpers)
const valid = { username: 'test_student', realname: '合成学生', password: 'Synthetic8!', confirmPassword: 'Synthetic8!' }
const deferred = () => { let resolve, reject; const promise = new Promise((a, b) => { resolve = a; reject = b }); return { promise, resolve, reject } }
function harness (apis = {}, open = true) {
  const routes = []; let focused = ''
  const context = { ...helpers, registerAccount: async () => ({ success: true }),
    ...apis }
  vm.runInNewContext(read('views/user/Register.vue').match(/<script>([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm, '').replace('export default', 'this.options ='), context)
  const component = new Vue(context.options)
  component.$store = { getters: { sysConfig: { allowReg: open ? '1' : '0' } } }
  component.$router = { replace: async value => routes.push(value) }
  for (const key of [...Object.keys(valid), 'submitError']) component.$refs[key] = { focus () { focused = key } }
  return { component, routes, get focused () { return focused } }
}
test('closed registration makes no signup request', async () => {
  let calls = 0; const h = harness({ registerAccount: () => calls++ }, false)
  Object.assign(h.component, valid); await h.component.submit(); assert.equal(calls, 0); h.component.$destroy()
})
test('invalid account/name/password/confirmation never submits', async () => {
  for (const changed of [{ username: 'ab' }, { username: 'a-bc' }, { realname: ' ' }, { realname: 'x'.repeat(101) }, { realname: '😀' }, { password: 'pass1234' }, { password: 'abc123!中' }, { confirmPassword: 'Synthetic8! ' }]) {
    let calls = 0; const h = harness({ registerAccount: () => calls++ }); Object.assign(h.component, valid, changed)
    await h.component.submit(); await Vue.nextTick(); assert.equal(calls, 0); assert.ok(h.focused); h.component.$destroy()
  }
})
test('registration does not collect a phone number or SMS code', async () => {
  const source = read('views/user/Register.vue')
  assert.doesNotMatch(source, /register-phone|register-code|sendRegistrationCode|smscode/)
  assert.doesNotMatch(read('api/registration.js'), /\/sms|phone/)
  const h = harness(); Object.assign(h.component, valid); await h.component.submit()
  assert.equal(h.routes.length, 1); h.component.$destroy()
})
test('duplicate and transport errors preserve entire form and never navigate', async () => {
  for (const api of [async () => ({ success: false, result: { registrationState: 'duplicate' } }), async () => { throw { isAxiosError: true } }]) {
    const h = harness({ registerAccount: api }); Object.assign(h.component, valid); await h.component.submit()
    for (const key of Object.keys(valid)) assert.equal(h.component[key], valid[key]); assert.equal(h.component.submitting, false); assert.equal(h.routes.length, 0); h.component.$destroy()
  }
})
test('transaction failure preserves form and allows retry', async () => {
  let attempts = 0
  const h = harness({ registerAccount: async () => ({ success: ++attempts > 1, result: { registrationState: 'registration_failed' } }) })
  Object.assign(h.component, valid); await h.component.submit()
  assert.equal(h.component.password, valid.password); assert.equal(h.component.submitting, false); assert.equal(h.routes.length, 0)
  await h.component.submit(); assert.equal(attempts, 2); assert.equal(h.routes.length, 1); h.component.$destroy()
})
test('registration sends explicit fields once and routes with only the username, clearing secrets', async () => {
  const pending = deferred(); const calls = []; const h = harness({ registerAccount: payload => { calls.push(payload); return pending.promise } }); Object.assign(h.component, valid, { username: '  test_student  ' })
  const first = h.component.submit(); await h.component.submit(); assert.equal(calls.length, 1); assert.deepEqual(Object.keys(calls[0]), ['username', 'realname', 'password']); assert.equal(calls[0].username, valid.username)
  pending.resolve({ success: true }); await first; assert.equal(h.routes.length, 1); assert.equal(JSON.stringify(h.routes[0]), JSON.stringify({ name: 'registerResult', params: { username: valid.username } }))
  for (const key of ['password', 'confirmPassword']) assert.equal(h.component[key], ''); h.component.$destroy()
})
test('destroyed signup cannot navigate or retain passwords', async () => {
  const pending = deferred(); const h = harness({ registerAccount: () => pending.promise }); Object.assign(h.component, valid)
  const first = h.component.submit(); h.component.$destroy(); pending.resolve({ success: true }); await first; assert.equal(h.routes.length, 0); assert.equal(h.component.password, '')
})
test('result page only displays a valid account and deep-link refresh does not claim success', () => {
  const context = {}; vm.runInNewContext(read('views/user/RegisterResult.vue').match(/<script>([\s\S]*?)<\/script>/)[1].replace('export default', 'this.options ='), context)
  for (const username of [undefined, { name: 'private' }, '<script>', 'valid_user']) assert.equal(context.options.computed.username.call({ $route: { params: { username } } }), username === 'valid_user' ? username : '')
})
test('arbitrary server messages cannot echo credentials into a page error', () => {
  assert.equal(helpers.registrationError({ message: 'secret-password=private' }, '请重试'), '请重试')
})
