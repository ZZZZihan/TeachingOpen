const assert = require('node:assert/strict')
const fs = require('node:fs')
const vm = require('node:vm')
const path = require('node:path')
const { test } = require('node:test')
const Vue = require('vue')
const compiler = require('vue-template-compiler')
const source = file => fs.readFileSync(path.join(__dirname, '../src/', file), 'utf8')
const helpers = {}; vm.runInNewContext(source('utils/accountRecovery.js').replace(/export /g, ''), helpers)
function harness (postAction, propsData = {}) {
  const context = { ...helpers, postAction }
  vm.runInNewContext(source('views/user/Register.vue').match(/<script>([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm, '').replace('export default', 'this.component ='), context)
  const component = new Vue({ ...context.component, propsData }); const routes = []
  component.$router = { push: route => { routes.push(route); return Promise.resolve() } }
  return { component, routes }
}
const valid = { phone: '13900000001', password: 'Synthetic8!', confirmation: 'Synthetic8!', realname: ' 张同学 ', school: ' 测试学校 ' }
test('student and teacher registration accept 8–64 printable characters without a required character mix', async () => {
  for (const teacherRegistration of [false, true]) {
    for (const password of ['abcdefgh', '12345678', 'learn123', '[]{}|~!?', 'a'.repeat(64)]) {
      let sent; const h = harness((url, body) => { sent = { url, body }; return Promise.resolve({ success: true }) }, { teacherRegistration })
      Object.assign(h.component.form, valid, { password, confirmation: password }); await h.component.submit()
      assert.equal(sent.url, teacherRegistration ? '/sys/user/register/teacher' : '/sys/user/register')
      assert.equal(sent.body.password, password); assert.equal(h.routes.length, 1)
    }
  }
})
test('registration rejects missing, short, long and unsupported passwords before requesting either endpoint', async () => {
  for (const teacherRegistration of [false, true]) {
    for (const password of ['', 'abc1234', 'a'.repeat(65), 'abcd123 ', 'abcd1234\n', 'abcd1234\r', 'abcd1234\r\n', '密码abcd123', 'abcd123😊']) {
      let calls = 0; const h = harness(() => { calls++ }, { teacherRegistration })
      Object.assign(h.component.form, valid, { password, confirmation: password }); await h.component.submit()
      assert.equal(calls, 0); assert.ok(h.component.errors.password); assert.equal(h.component.form.password, password)
    }
  }
})
test('simple registration passwords still require matching confirmation', async () => {
  let calls = 0; const h = harness(() => { calls++ })
  Object.assign(h.component.form, valid, { password: 'learn123', confirmation: 'learn124' }); await h.component.submit()
  assert.equal(calls, 0); assert.ok(h.component.errors.confirmation); assert.equal(h.component.errors.password, undefined)
})
test('student and teacher registration render their own titles without identity selection or removed explanatory copy', () => {
  const template = compiler.parseComponent(source('views/user/Register.vue')).template.content
  const compiled = compiler.compile(template)
  assert.deepEqual(compiled.errors, [])
  function content (teacherRegistration) {
    const h = harness(() => {}, { teacherRegistration })
    h.component.$options.render = new Function(compiled.render)
    h.component.$options.staticRenderFns = compiled.staticRenderFns.map(fn => new Function(fn))
    const nodes = []
    function visit (node) { nodes.push(node); for (const child of node.children || []) visit(child) }
    visit(h.component._render())
    assert.equal(nodes.some(node => node.tag === 'input' && node.data.attrs.type === 'radio'), false)
    const text = nodes.map(node => node.text || '').join('')
    assert.doesNotMatch(text, /姓名将脱敏展示|学校和身份将展示在首页|教师身份用于个人资料|教学管理权限由管理员开通/)
    return text
  }
  const student = content(false)
  assert.match(student, /创建学生账号/); assert.doesNotMatch(student, /教师/)
  const teacher = content(true)
  assert.match(teacher, /创建教师账号/)
})
test('blank student registration validates required fields without an identity selection', async () => {
  let calls = 0; const h = harness(() => { calls++; }); assert.equal(h.component.teacherRegistration, false)
  await h.component.submit(); assert.equal(calls, 0); assert.equal(Object.keys(h.component.errors).length, 5)
})
test('success sends only registration fields, clears credentials and navigates without password', async () => {
  let body; const h = harness((url, data) => { assert.equal(url, '/sys/user/register'); body = data; return Promise.resolve({ success: true }) })
  Object.assign(h.component.form, valid, { identity: 'teacher' }); await h.component.submit()
  assert.equal(body.realname, '张同学'); assert.equal(body.school, '测试学校'); assert.equal(body.identity, undefined); assert.equal(Object.keys(body).length, 4)
  assert.equal(h.component.form.password, ''); assert.equal(h.component.form.confirmation, '')
  assert.equal(h.routes.length, 1); assert.equal(h.routes[0].params.phone, valid.phone); assert.equal(h.routes[0].params.password, undefined)
})
test('dedicated teacher entry registers through its own endpoint without client-selected identity or roles', async () => {
  let body; const h = harness((url, data) => { assert.equal(url, '/sys/user/register/teacher'); body = data; return Promise.resolve({ success: true }) }, { teacherRegistration: true })
  Object.assign(h.component.form, valid, { identity: 'student', role: 'teacher' }); await h.component.submit()
  assert.equal(h.routes.length, 1); assert.equal(body.identity, undefined); assert.equal(body.role, undefined)
  assert.equal(h.component.form.password, ''); assert.equal(h.component.form.confirmation, '')
})
test('duplicate submit is guarded and API failure permits retry', async () => {
  let resolve; let calls = 0; const h = harness(() => { calls++; return new Promise(done => { resolve = done }) }); Object.assign(h.component.form, valid)
  const pending = h.component.submit(); await h.component.submit(); assert.equal(calls, 1)
  resolve({ success: false, message: '手机号已注册' }); await pending
  assert.equal(h.component.submitting, false); assert.equal(h.component.submitError, '手机号已注册'); assert.equal(h.routes.length, 0)
})
