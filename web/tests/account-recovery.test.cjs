const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { resolve } = require('node:path')
const vm = require('node:vm')
const { test } = require('node:test')
const Vue = require('vue')
const source = file => readFileSync(resolve(__dirname, '../src', file), 'utf8')
const run = (text, context) => { vm.runInNewContext(text, context); return context }
const helper = run(source('utils/accountRecovery.js').replace(/export /g, ''), {})
const flush = () => new Promise(resolve => setImmediate(resolve))
const deferred = () => { let resolve, reject; const promise = new Promise((a, b) => { resolve = a; reject = b }); return { promise, resolve, reject } }
const ok = { success: true }
const image = { success: true, result: 'data:image/png;base64,fixture' }
const user = { username: 'synthetic_student', maskedPhone: '138****0000' }
function harness (step, apis = {}, props = {}) {
  const timers = new Set(); let focus = ''; const events = []
  const context = { Step1: {}, Step2: {}, Step3: {}, Step4: {}, ...helper, getRecoveryCaptcha: () => Promise.resolve(image), checkRecoveryCaptcha: () => Promise.resolve(ok), queryRecoveryAccount: () => Promise.resolve({ success: true, result: { username: user.username, phone: user.maskedPhone } }), sendRecoverySms: () => Promise.resolve(ok), verifyRecoveryPhone: () => Promise.resolve(ok), changeRecoveryPassword: () => Promise.resolve(ok),
    setInterval: fn => { timers.add(fn); return fn }, clearInterval: id => timers.delete(id), ...apis }
  const script = source('views/user/' + step + '.vue').match(/<script>([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm, '').replace('export default', 'this.component =')
  run(script, context)
  const component = new Vue({ ...context.component, propsData: { userList: { ...user }, ...props } })
  for (const key of ['account', 'captcha', 'phone', 'smscode', 'password', 'confirmPassword', 'submitError']) component.$refs[key] = { focus () { focus = key } }
  for (const event of ['nextStep', 'prevStep', 'verificationInvalid']) component.$on(event, data => events.push({ event, data }))
  return { component, events, timers, get focus () { return focus } }
}

test('phone and password validation match mainland phone and printable ASCII 8–64 contract', () => {
  for (const phone of ['13800000000', '19900000000']) assert.equal(helper.isMainlandPhone(phone), true)
  for (const phone of ['138****0000', '1380000000', '+8613800000000', '12800000000']) assert.equal(helper.isMainlandPhone(phone), false)
  for (const password of ['abcd123!', 'ABCD123!', 'a1!'.repeat(21) + 'a']) assert.equal(helper.passwordProblem(password), '')
  for (const password of ['abcd123', 'abcdefgh!', '1234567!', 'abcd123! '.trimEnd() + ' ', 'abc123!中', 'abc123!😊', 'a1!'.repeat(22), 'abcd123[']) assert.ok(helper.passwordProblem(password), password)
})
test('recovery errors never surface arbitrary stack or payload messages', () => {
  assert.equal(helper.recoveryError({ message: 'password=secret' }, '请重试'), '请重试')
  assert.match(helper.recoveryError({ isAxiosError: true }, 'x'), /检查网络/)
  assert.match(helper.recoveryError({ code: 'ECONNABORTED' }, 'x'), /超时/)
  assert.match(helper.recoveryError({ response: { status: 500, data: { message: 'private' } } }, 'x'), /暂时不可用/)
})
test('Step1 missing input makes no account request and focuses account', async () => {
  let calls = 0; const h = harness('Step1', { queryRecoveryAccount: () => { calls++; return Promise.resolve(ok) } }); await flush()
  await h.component.nextStep(); await Vue.nextTick(); assert.equal(calls, 0); assert.equal(h.focus, 'account'); h.component.$destroy()
})
test('Step1 verifies real CAPTCHA once before lookup, keeps masked phone only as hint', async () => {
  const calls = []; const pending = deferred()
  const h = harness('Step1', { checkRecoveryCaptcha: body => { calls.push(['captcha', body]); return pending.promise }, queryRecoveryAccount: body => { calls.push(['lookup', body]); return Promise.resolve({ success: true, result: { username: user.username, phone: user.maskedPhone } }) } }); await flush()
  Object.assign(h.component, { account: '13800000000', captcha: ' aB12 ' })
  const first = h.component.nextStep(); await h.component.nextStep(); assert.equal(calls.length, 1); pending.resolve(ok); await first
  assert.equal(calls[0][1].captcha, 'aB12'); assert.equal(calls[1][1].phone, '13800000000')
  assert.equal(h.events[0].data.enteredPhone, '13800000000'); assert.equal(h.events[0].data.maskedPhone, user.maskedPhone); assert.equal(h.events[0].data.phone, undefined); assert.equal(h.component.captcha, ''); h.component.$destroy()
})
test('Step1 numeric school account remains eligible for username lookup', async () => {
  let values; const h = harness('Step1', { queryRecoveryAccount: body => { values = body; return Promise.resolve({ success: true, result: { username: '20261005' } }) } }); await flush()
  Object.assign(h.component, { account: '20261005', captcha: 'ab12' }); await h.component.nextStep(); assert.equal(values.username, '20261005'); h.component.$destroy()
})
test('Step1 CAPTCHA/lookup failures recover loading and refresh image', async () => {
  for (const api of ['checkRecoveryCaptcha', 'queryRecoveryAccount']) {
    let images = 0
    const h = harness('Step1', { getRecoveryCaptcha: () => { images++; return Promise.resolve(image) }, [api]: () => Promise.reject({ isAxiosError: true }) }); await flush()
    Object.assign(h.component, { account: 'student', captcha: 'ab12' }); await h.component.nextStep()
    assert.equal(h.component.submitting, false); assert.equal(h.component.captcha, ''); assert.equal(images, 2); assert.match(h.component.submitError, /检查网络/); assert.equal(h.events.length, 0); h.component.$destroy()
  }
})
test('Step1 stale CAPTCHA image and destroyed lookup cannot advance', async () => {
  const images = []
  const h = harness('Step1', { getRecoveryCaptcha: () => { const d = deferred(); images.push(d); return d.promise } })
  const latest = h.component.refreshCaptcha(); images[1].resolve({ success: true, result: 'data:image/png;base64,new' }); await latest
  images[0].resolve(image); await flush(); assert.equal(h.component.captchaImage, 'data:image/png;base64,new'); h.component.$destroy()
  const pending = deferred(); const b = harness('Step1', { queryRecoveryAccount: () => pending.promise }); await flush(); Object.assign(b.component, { account: 'student', captcha: 'ab12' }); const next = b.component.nextStep(); await flush()
  b.component.$destroy(); pending.resolve({ success: true, result: user }); await next; assert.equal(b.events.length, 0)
})
test('Step1 changing account while lookup pending prevents old advancement', async () => {
  const pending = deferred(); const h = harness('Step1', { queryRecoveryAccount: () => pending.promise }); await flush()
  Object.assign(h.component, { account: 'old', captcha: 'ab12' }); const next = h.component.nextStep(); await flush(); h.component.account = 'new'; h.component.accountChanged()
  pending.resolve({ success: true, result: user }); await next; assert.equal(h.events.length, 0); assert.equal(h.component.submitting, false); h.component.$destroy()
})
test('Step2 mask is never a default phone or transmitted mobile, failed send is immediately retryable', async () => {
  const calls = []; let fail = true
  const h = harness('Step2', { sendRecoverySms: body => { calls.push(body); return fail ? Promise.reject({ isAxiosError: true }) : Promise.resolve(ok) } })
  assert.equal(h.component.phone, ''); await h.component.getCaptcha(); assert.equal(calls.length, 0)
  h.component.phone = '13800000000'; await h.component.getCaptcha(); assert.equal(h.component.sending, false); assert.equal(h.component.remaining, 0); assert.equal(h.timers.size, 0)
  fail = false; await h.component.getCaptcha(); assert.equal(calls.length, 2); assert.deepEqual(JSON.parse(JSON.stringify(calls[1])), { mobile: '13800000000', smsmode: '2', username: user.username }); assert.equal(h.component.remaining, 600); assert.equal(h.timers.size, 1)
  h.component.$destroy(); assert.equal(h.timers.size, 0)
})
test('Step2 business send failure starts no cooldown; pending duplicate send runs once', async () => {
  const pending = deferred(); let calls = 0
  const h = harness('Step2', { sendRecoverySms: () => { calls++; return pending.promise } }); h.component.phone = '13800000000'
  const next = h.component.getCaptcha(); await h.component.getCaptcha(); assert.equal(calls, 1); pending.resolve({ success: false }); await next
  assert.equal(h.component.sending, false); assert.equal(h.component.remaining, 0); assert.match(h.component.submitError, /短信未能发送/); h.component.$destroy()
})
test('Step2 verifies real entered phone and sends entered code to Step3 without relying on result', async () => {
  let body; const h = harness('Step2', { verifyRecoveryPhone: values => { body = values; return Promise.resolve({ success: true, result: 'do-not-use' }) } })
  Object.assign(h.component, { phone: '13800000000', smscode: '123456' }); await h.component.nextStep()
  assert.deepEqual(JSON.parse(JSON.stringify(body)), { username: user.username, phone: '13800000000', smscode: '123456' }); assert.equal(h.events[0].data.smscode, '123456'); assert.equal(h.events[0].data.phone, '13800000000'); assert.equal(h.component.smscode, ''); h.component.$destroy()
})
test('Step2 validation and network failure always restore controls and keep errors on form', async () => {
  let calls = 0; const h = harness('Step2', { verifyRecoveryPhone: () => { calls++; return Promise.reject({ isAxiosError: true }) } })
  await h.component.nextStep(); assert.equal(h.component.verifying, false); assert.equal(calls, 0)
  h.component.phone = '13800000000'; await h.component.nextStep(); assert.equal(h.component.verifying, false); assert.equal(calls, 0)
  h.component.smscode = '123456'; await h.component.nextStep(); assert.equal(h.component.verifying, false); assert.equal(calls, 1); assert.match(h.component.submitError, /检查网络/); h.component.$destroy()
})
test('Step2 edit phone, return and destroy discard late send/verify responses and timers', async () => {
  for (const api of ['sendRecoverySms', 'verifyRecoveryPhone']) {
    for (const action of ['phoneChanged', 'prevStep', '$destroy']) {
      const pending = deferred(); const h = harness('Step2', { [api]: () => pending.promise }); Object.assign(h.component, { phone: '13800000000', smscode: '123456' })
      const next = api === 'sendRecoverySms' ? h.component.getCaptcha() : h.component.nextStep()
      if (action === 'phoneChanged') h.component.phone = '13900000000'
      h.component[action](); pending.resolve(ok); await next
      assert.equal(h.events.filter(e => e.event === 'nextStep').length, 0); assert.equal(h.component.remaining, 0); assert.equal(h.timers.size, 0); h.component.$destroy()
    }
  }
})
test('Step2 returning from Step3 preserves only remaining resend cooldown', () => {
  const h = harness('Step2', {}, { userList: { ...user, enteredPhone: '13800000000', smscode: 'old', resendAt: Date.now() + 29000 } })
  assert.equal(h.component.phone, '13800000000'); assert.equal(h.component.smscode, ''); assert.ok(h.component.remaining <= 29); h.component.$destroy(); assert.equal(h.timers.size, 0)
})
test('Step3 exact confirmation and invalid passwords make no request', async () => {
  let calls = 0; const h = harness('Step3', { changeRecoveryPassword: () => { calls++; return Promise.resolve(ok) } }, { userList: { ...user, phone: '13800000000', smscode: '123456' } })
  Object.assign(h.component, { password: 'abcd123!', confirmPassword: 'abcd123! ' }); await h.component.nextStep(); assert.equal(calls, 0); assert.match(h.component.errors.confirmPassword, /不一致/)
  Object.assign(h.component, { password: 'abc123!中', confirmPassword: 'abc123!中' }); await h.component.nextStep(); assert.equal(calls, 0); h.component.$destroy()
})
test('Step3 POST payload includes all verification fields; single submission clears passwords and emits no code', async () => {
  const pending = deferred(); const calls = []; const h = harness('Step3', { changeRecoveryPassword: body => { calls.push(body); return pending.promise } }, { userList: { ...user, phone: '13800000000', smscode: '123456' } })
  Object.assign(h.component, { password: 'abcd123!', confirmPassword: 'abcd123!' }); const next = h.component.nextStep(); await h.component.nextStep(); assert.equal(calls.length, 1)
  assert.deepEqual(JSON.parse(JSON.stringify(calls[0])), { username: user.username, phone: '13800000000', smscode: '123456', password: 'abcd123!' }); pending.resolve(ok); await next
  assert.equal(h.component.password, ''); assert.equal(h.component.confirmPassword, ''); assert.equal(h.events[0].data.smscode, undefined); assert.equal(h.events[0].data.username, user.username); h.component.$destroy()
})
test('Step3 uncertain/consumed failure clears passwords and requires verification before any retry', async () => {
  for (const outcome of [() => Promise.reject({ isAxiosError: true }), () => Promise.resolve({ success: false, code: 500, message: 'sensitive' })]) {
    let calls = 0; const h = harness('Step3', { changeRecoveryPassword: () => { calls++; return outcome() } }, { userList: { ...user, phone: '13800000000', smscode: '123456' } })
    Object.assign(h.component, { password: 'abcd123!', confirmPassword: 'abcd123!' }); await h.component.nextStep(); assert.equal(h.component.submitting, false); assert.equal(h.component.password, ''); assert.equal(h.component.confirmPassword, ''); assert.equal(h.component.verificationRequired, true); assert.match(h.component.submitError, /重新获取验证码/)
    await h.component.nextStep(); assert.equal(calls, 1); assert.equal(h.events[0].event, 'verificationInvalid'); h.component.prevStep(); assert.equal(h.events[1].event, 'prevStep'); h.component.$destroy()
  }
})
test('Step3 return/destroy ignores late successful password response', async () => {
  for (const action of ['prevStep', '$destroy']) {
    const pending = deferred(); const h = harness('Step3', { changeRecoveryPassword: () => pending.promise }, { userList: { ...user, phone: '13800000000', smscode: '123456' } })
    Object.assign(h.component, { password: 'abcd123!', confirmPassword: 'abcd123!' }); const next = h.component.nextStep(); h.component[action](); pending.resolve(ok); await next
    assert.equal(h.events.filter(e => e.event === 'nextStep').length, 0); assert.equal(h.component.password, ''); h.component.$destroy()
  }
})
test('parent clears phone/code after success, returning clears code, and success screen has explicit login with no timer', () => {
  const h = harness('Alteration'); h.component.accountFound(user); h.component.phoneVerified({ ...user, phone: '13800000000', smscode: '123456' }); h.component.verifyAgain(); assert.equal(h.component.userList.smscode, ''); assert.equal(h.component.userList.phone, ''); assert.equal(h.component.userList.enteredPhone, '13800000000')
  h.component.phoneVerified({ ...user, phone: '13800000000', smscode: '123456' }); h.component.passwordChanged({ username: user.username }); assert.equal(h.component.currentTab, 3); assert.deepEqual(JSON.parse(JSON.stringify(h.component.userList)), { username: user.username }); h.component.$destroy()
  const success = source('views/user/Step4.vue'); assert.match(success, /返回登录/); assert.doesNotMatch(success, /setInterval|setTimeout/)
})
test('recovery API uses POST JSON for code and password, no sensitive query strings or console logging', async () => {
  const calls = []; const text = source('api/accountRecovery.js').replace(/^import .*$/gm, '').replace(/export const /g, 'this.'); const context = run(text, { axios: options => { calls.push(options); return Promise.resolve(ok) } })
  await context.changeRecoveryPassword({ password: 'fixture-only', smscode: '123456' }); await context.verifyRecoveryPhone({ smscode: '123456' }); await context.sendRecoverySms({ mobile: '13800000000' })
  for (const call of calls) { assert.equal(call.method, 'post'); assert.equal(call.params, undefined); assert.equal(call.localError, true); assert.equal(call.skipSession, true); assert.equal(call.timeout, 15000); assert.doesNotMatch(call.url, /fixture-only|123456/) }
  for (const file of ['Step1', 'Step2', 'Step3', 'Step4']) assert.doesNotMatch(source('views/user/' + file + '.vue'), /console\./)
})

test('Step2 active-code business response preserves entered code and gives accurate recovery feedback', async () => {
  const h = harness('Step2', { sendRecoverySms: () => Promise.resolve({ success: false, code: 400, recoveryState: 'code_active' }) })
  Object.assign(h.component, { phone: '13800000000', smscode: '123456' }); await h.component.getCaptcha()
  assert.equal(h.component.smscode, '123456'); assert.equal(h.component.remaining, 0); assert.equal(h.component.sending, false); assert.match(h.component.submitError, /仍有效或正在发送/); assert.doesNotMatch(h.component.submitError, /检查手机号/); h.component.$destroy()
})
test('Step3 stable reset state differentiates unknown from committed and never claims uncertain update failed', async () => {
  for (const state of ['reset_unknown', 'reset_committed']) {
    const h = harness('Step3', { changeRecoveryPassword: () => Promise.resolve({ success: false, code: 500, recoveryState: state }) }, { userList: { ...user, phone: '13800000000', smscode: '123456' } })
    Object.assign(h.component, { password: 'abcd123!', confirmPassword: 'abcd123!' }); await h.component.nextStep()
    assert.match(h.component.submitError, /新密码登录/); assert.doesNotMatch(h.component.submitError, /密码未能更新/); if (state === 'reset_committed') assert.match(h.component.submitError, /密码已更新/); else assert.match(h.component.submitError, /未能确认/); h.component.$destroy()
  }
})
test('consumed or uncertain reset clears inherited resend cooldown before returning to phone verification', () => {
  const parent = harness('Alteration'); parent.component.accountFound(user); parent.component.phoneVerified({ ...user, phone: '13800000000', smscode: '123456', resendAt: Date.now() + 500000 })
  parent.component.clearVerification(); parent.component.verifyAgain()
  const phone = harness('Step2', {}, { userList: parent.component.userList }); assert.equal(phone.component.remaining, 0); assert.equal(phone.component.smscode, ''); assert.equal(phone.component.resendAt, 0); phone.component.$destroy(); parent.component.$destroy()
})
