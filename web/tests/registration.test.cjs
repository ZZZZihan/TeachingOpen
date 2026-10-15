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
const valid = { username: ' learner_2026 ', password: 'Synthetic8!', confirmation: 'Synthetic8!', realname: ' 张同学 ', school: ' 测试学校 ' }
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
  assert.equal(body.username, 'learner_2026'); assert.equal(body.phone, undefined); assert.equal(body.realname, '张同学'); assert.equal(body.school, '测试学校'); assert.equal(body.identity, undefined); assert.equal(Object.keys(body).length, 4)
  assert.equal(h.component.form.password, ''); assert.equal(h.component.form.confirmation, '')
  assert.equal(h.routes.length, 1); assert.equal(h.routes[0].params.username, valid.username.trim()); assert.equal(h.routes[0].params.password, undefined)
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
  resolve({ success: false, message: '用户名已注册' }); await pending
  assert.equal(h.component.submitting, false); assert.equal(h.component.submitError, '用户名已注册'); assert.equal(h.routes.length, 0)
})

test('both registration routes validate username boundaries before making requests', async () => {
  for (const teacherRegistration of [false, true]) {
    for (const username of ['', '  ', 'ab', 'a'.repeat(101), '用户123', 'user name', 'user/name', 'user\nname', 'user😊']) {
      let calls = 0; const h = harness(() => { calls++ }, { teacherRegistration })
      Object.assign(h.component.form, valid, { username }); await h.component.submit()
      assert.equal(calls, 0, username); assert.ok(h.component.errors.username); assert.equal(h.component.form.username, username)
    }
    for (const username of ['abc', '20261015', 'User_01@school.edu-test', 'a'.repeat(100), '  learner_01  ']) {
      let body; const h = harness((url, data) => { body = data; return Promise.resolve({ success: true }) }, { teacherRegistration })
      Object.assign(h.component.form, valid, { username }); await h.component.submit()
      assert.equal(body.username, username.trim()); assert.equal(body.phone, undefined)
      assert.equal(h.routes[0].params.username, username.trim())
    }
  }
})
test('registration failures preserve all input and allow a corrected username retry', async () => {
  for (const failure of [() => Promise.resolve({ success: false, message: '用户名已注册' }), () => Promise.reject({ isAxiosError: true })]) {
    let calls = 0
    const h = harness(() => ++calls === 1 ? failure() : Promise.resolve({ success: true }))
    Object.assign(h.component.form, valid); await h.component.submit()
    assert.deepEqual(JSON.parse(JSON.stringify(h.component.form)), valid)
    assert.equal(h.component.submitting, false); assert.ok(h.component.submitError); assert.equal(h.routes.length, 0)
    h.component.form.username = 'another_learner'; await h.component.submit()
    assert.equal(calls, 2); assert.equal(h.routes[0].params.username, 'another_learner'); assert.equal(h.component.form.password, '')
  }
})
test('registration result forwards the chosen username to login without credentials', () => {
  const context = {}
  vm.runInNewContext(source('views/user/RegisterResult.vue').match(/<script>([\s\S]*?)<\/script>/)[1].replace('export default', 'this.component ='), context)
  const compiled = compiler.compile(compiler.parseComponent(source('views/user/RegisterResult.vue')).template.content)
  assert.deepEqual(compiled.errors, [])
  const component = new Vue(context.component)
  component.$route = { params: { username: 'chosen_learner', password: 'must-not-forward' } }
  component.$options.render = new Function(compiled.render)
  component.$options.staticRenderFns = compiled.staticRenderFns.map(fn => new Function(fn))
  const nodes = []
  function visit (node) { nodes.push(node); for (const child of node.children || []) visit(child) }
  visit(component._render())
  const link = nodes.find(node => node.data && node.data.attrs && node.data.attrs.to && node.data.attrs.to.name === 'login')
  assert.deepEqual(JSON.parse(JSON.stringify(link.data.attrs.to)), { name: 'login', params: { username: 'chosen_learner' } })
  assert.match(nodes.map(node => node.text || '').join(''), /chosen_learner/)
  component.$destroy()
})
