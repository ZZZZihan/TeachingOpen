const assert = require('node:assert/strict')
const { test } = require('node:test')
const { readFileSync } = require('node:fs')
const { resolve } = require('node:path')
const vm = require('node:vm')
const pick = require('lodash/pick')

test('个人设置实际保存方法只发送允许字段，不重发完整登录资料', async () => {
  const writes = []
  const context = { AvatarModal: {}, JUpload: {}, moment: () => {}, pick,
    putAction: (url, body) => { writes.push({ url, body }); return Promise.resolve({ success: true }) },
    console: { log () {} } }
  vm.runInNewContext(readFileSync(resolve(__dirname, '../src/views/account/settings/BaseSetting.vue'), 'utf8')
    .match(/<script>([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm, '').replace('export default', 'this.component ='), context)
  const fullAccount = { id: 'self', username: 'account', password: 'never-send', salt: 'never-send',
    phone: '13912345678', departIds: 'school', status: 1, realname: '旧名称' }
  const instance = { userInfo: fullAccount, form: { validateFields: (fields, callback) => callback(null, {
    realname: '新名称', avatar: 'safe-avatar', sex: 1, email: 'test@example.test', birthday: null,
    phone: '13900000000', password: 'unexpected', status: 2
  }) }, url: { editUser: '/teaching/user/edit' }, $message: { success () {}, warning () {} }, $emit () {} }
  context.component.methods.handleSubmit.call(instance)
  await new Promise(resolve => setImmediate(resolve))
  assert.equal(writes[0].url, '/teaching/user/edit')
  assert.deepEqual(JSON.parse(JSON.stringify(writes[0].body)), {
    id: 'self', realname: '新名称', avatar: 'safe-avatar', sex: 1, email: 'test@example.test', birthday: null
  })
  assert.equal(fullAccount.realname, '旧名称')
  assert.equal(instance.confirmLoading, false)
})

const Schema = require('async-validator').default
const flush = () => new Promise(resolve => setImmediate(resolve))

function profile ({ email = 'candidate@example.test', duplicateReply = { success: true }, saveReply = { success: true } } = {}) {
  const writes = [], probes = [], warnings = [], events = [], validations = []
  const context = { AvatarModal: {}, JUpload: {}, moment: () => {}, pick,
    window: { _CONFIG: { domianURL: '' } }, console: { log () {} },
    duplicateCheck: params => { probes.push(params); return duplicateReply instanceof Error ? Promise.reject(duplicateReply) : Promise.resolve(duplicateReply) },
    putAction: (url, body) => { writes.push({ url, body }); return saveReply instanceof Error ? Promise.reject(saveReply) : Promise.resolve(saveReply) } }
  vm.runInNewContext(readFileSync(resolve(__dirname, '../src/views/account/settings/BaseSetting.vue'), 'utf8')
    .match(/<script>([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm, '').replace('export default', 'this.component ='), context)
  const instance = { $form: { createForm: () => ({}) }, $message: { success () {}, warning: value => warnings.push(value) }, $emit: name => events.push(name) }
  for (const [name, method] of Object.entries(context.component.methods)) instance[name] = method.bind(instance)
  Object.assign(instance, context.component.data.call(instance))
  instance.userInfo = { id: 'self' }
  const values = { realname: '新名称', avatar: 'safe-avatar', sex: 2, email, birthday: null, phone: 'legacy-noneditable-number' }
  instance.form = {
    validateFields (fields, callback) {
      validations.push(Array.from(fields))
      // Use Ant Design's validation dependency with the real form's rules.
      const descriptor = {}
      fields.forEach(field => { if (instance.validatorRules[field]) descriptor[field] = instance.validatorRules[field].rules })
      new Schema(descriptor).validate(values, errors => callback(errors, values))
    },
    getFieldsValue () { throw new Error('Submitting unvalidated values is forbidden') }
  }
  return { instance, values, writes, probes, warnings, events, validations }
}

test('格式错误及超长邮箱被实际表单规则拒绝，提交不发出写请求', async () => {
  for (const email of ['abc', 'u\uFEFFser@example.test', 'u\u0085ser@example.test', '"u\u0001ser"@example.test', 'name@', ' user@example.test', 'user@example.test\n', 'a'.repeat(101) + '@example.test']) {
    const h = profile({ email })
    h.instance.handleSubmit()
    await flush()
    assert.equal(h.writes.length, 0, email)
    assert.equal(h.events.length, 0)
    assert.equal(h.instance.confirmLoading, false)
  }
})

test('合法邮箱等待实际查重成功后才保存，重复点击不重复提交', async () => {
  const h = profile()
  h.instance.handleSubmit()
  h.instance.handleSubmit()
  assert.equal(h.writes.length, 0)
  assert.equal(h.instance.confirmLoading, true)
  await flush()
  assert.equal(h.writes.length, 1)
  assert.deepEqual(JSON.parse(JSON.stringify(h.probes)), [{ purpose: 'profile_email', fieldVal: h.values.email, dataId: 'self' }])
  assert.deepEqual(h.validations, [['realname', 'avatar', 'birthday', 'sex', 'email']])
  assert.deepEqual(h.events, ['ok'])
  assert.equal(h.instance.confirmLoading, false)
})

test('空邮箱保持可选契约，无需查重且允许保存', async () => {
  for (const email of ['', undefined, null]) {
    const h = profile({ email })
    // The default value applies only when no explicit field value was provided.
    h.values.email = email
    h.instance.handleSubmit()
    await flush()
    assert.equal(h.probes.length, 0)
    assert.equal(h.writes.length, 1)
    assert.equal(h.instance.confirmLoading, false)
  }
})

test('查重重复、权限拒绝或网络失败均阻止保存，并结束等待状态', async () => {
  for (const duplicateReply of [{ success: false, code: 500 }, { success: false, code: 403 }, new Error('offline')]) {
    const h = profile({ duplicateReply })
    h.instance.handleSubmit()
    await flush()
    assert.equal(h.probes.length, 1)
    assert.equal(h.writes.length, 0)
    assert.equal(h.instance.confirmLoading, false)
  }
})

test('写入失败可重新提交，生日与账户原对象不被修改', async () => {
  for (const saveReply of [{ success: false, message: '保存失败' }, new Error('offline')]) {
    const h = profile({ saveReply })
    const birthday = { format: value => { assert.equal(value, 'YYYY-MM-DD'); return '2000-01-02' } }
    h.values.birthday = birthday
    h.instance.handleSubmit()
    await flush()
    assert.equal(h.writes[0].body.birthday, '2000-01-02')
    assert.equal(h.values.birthday, birthday)
    assert.equal(h.instance.confirmLoading, false)
    assert.equal(h.warnings.length, 1)
    assert.equal(h.events.length, 0)
    h.instance.handleSubmit()
    await flush()
    assert.equal(h.writes.length, 2)
  }
})
