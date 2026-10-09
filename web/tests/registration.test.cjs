const assert = require('node:assert/strict')
const fs = require('node:fs')
const vm = require('node:vm')
const path = require('node:path')
const { test } = require('node:test')
const Vue = require('vue')
const source = file => fs.readFileSync(path.join(__dirname, '../src/', file), 'utf8')
const helpers = {}; vm.runInNewContext(source('utils/accountRecovery.js').replace(/export /g, ''), helpers)
function harness (postAction) {
  const context = { ...helpers, postAction }
  vm.runInNewContext(source('views/user/Register.vue').match(/<script>([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm, '').replace('export default', 'this.component ='), context)
  const component = new Vue(context.component); const routes = []
  component.$router = { push: route => { routes.push(route); return Promise.resolve() } }
  return { component, routes }
}
const valid = { phone: '13900000001', password: 'Synthetic8!', confirmation: 'Synthetic8!', realname: ' 张同学 ', school: ' 测试学校 ', identity: 'teacher' }
test('blank registration has no identity default and does not make network requests', async () => {
  let calls = 0; const h = harness(() => { calls++; }); assert.equal(h.component.form.identity, '')
  await h.component.submit(); assert.equal(calls, 0); assert.equal(Object.keys(h.component.errors).length, 6)
})
test('success sends only registration fields, clears credentials and navigates without password', async () => {
  let body; const h = harness((url, data) => { assert.equal(url, '/sys/user/register'); body = data; return Promise.resolve({ success: true }) })
  Object.assign(h.component.form, valid); await h.component.submit()
  assert.equal(body.realname, '张同学'); assert.equal(body.school, '测试学校'); assert.equal(body.identity, 'teacher'); assert.equal(Object.keys(body).length, 5)
  assert.equal(h.component.form.password, ''); assert.equal(h.component.form.confirmation, '')
  assert.equal(h.routes.length, 1); assert.equal(h.routes[0].params.phone, valid.phone); assert.equal(h.routes[0].params.password, undefined)
})
test('duplicate submit is guarded and API failure permits retry', async () => {
  let resolve; let calls = 0; const h = harness(() => { calls++; return new Promise(done => { resolve = done }) }); Object.assign(h.component.form, valid)
  const pending = h.component.submit(); await h.component.submit(); assert.equal(calls, 1)
  resolve({ success: false, message: '手机号已注册' }); await pending
  assert.equal(h.component.submitting, false); assert.equal(h.component.submitError, '手机号已注册'); assert.equal(h.routes.length, 0)
})
