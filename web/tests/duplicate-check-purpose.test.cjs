const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const babel = require('@babel/core')

const root = path.resolve(__dirname, '..')
const read = file => fs.readFileSync(path.join(root, file), 'utf8')
const flush = () => new Promise(resolve => setImmediate(resolve))
const plain = value => JSON.parse(JSON.stringify(value))

// Execute the product SFC scripts and real shared validator with controlled API responses.
function mount(file, reply = { success: true, code: 200 }) {
  const calls = [], callbacks = []
  const duplicateCheck = params => {
    calls.push(plain(params))
    return reply instanceof Error ? Promise.reject(reply) : Promise.resolve(reply)
  }
  const source = read(file)
  const script = source.match(/<script>([\s\S]*?)<\/script>/)[1]
  const context = {
    component: null, duplicateCheck, api: { duplicateCheck },
    Vue: { ls: { get() {} } }, window: { _CONFIG: { domianURL: '' } },
    console: { log() {} }, FormTypes: {}, JEditableTable: {}, JEditor: {},
    moment: value => value, pick: object => object, failedSymbol: Symbol('failure'), alwaysResolve: () => {},
    Promise, setTimeout: callback => { callback(); return 1 }, clearTimeout() {},
    URL, document: { body: { clientWidth: 1024 } }
  }
  // Unrelated imported components and APIs are inert; duplicateCheck keeps the tested transport.
  for (const match of script.matchAll(/import\s+([^\n]+?)\s+from\s+['"][^'"]+['"]/g)) {
    const imported = match[1].replace(/[{}]/g, '').split(',').map(name => name.trim())
    for (const name of imported) if (!(name in context) && /^[A-Za-z_$][\w$]*$/.test(name)) context[name] = {}
  }
  vm.createContext(context)
  const utility = read('src/utils/util.js').match(/export function validateDuplicateValue\s*\([\s\S]*?\n\}/)[0]
  vm.runInContext(utility.replace('export ', ''), context)
  const executable = script.replace(/^\s*import [^\n]*$/gm, '').replace('export default', 'component =')
  vm.runInContext(babel.transformSync(executable, {
    babelrc: false, configFile: false,
    plugins: [require.resolve('@vue/babel-plugin-transform-vue-jsx')]
  }).code, context)
  const i = {
    $form: { createForm: () => ({}) }, $refs: {}, $nextTick() {},
    $message: {}, $emit() {}, _isDestroyed: false
  }
  for (const [name, fn] of Object.entries(context.component.methods || {})) i[name] = fn.bind(i)
  Object.assign(i, context.component.data.call(i))
  i.model = { id: 'edited-id' }; i.userId = 'edited-id'; i.userInfo = { id: 'own-id' }; i.visible = true
  return { i, calls, callbacks, callback: value => callbacks.push(value), source }
}

const direct = [
  ['src/views/system/modules/UserModal.vue', 'validateUsername', 'user_username', 'candidate'],
  ['src/views/system/modules/UserModal.vue', 'validatePhone', 'user_phone', '13900000002'],
  ['src/views/system/modules/UserModal.vue', 'validateEmail', 'user_email', 'candidate@example.invalid'],
  ['src/views/system/modules/UserModal.vue', 'validateWorkNo', 'user_work_no', 'work-001'],
  ['src/views/system/modules/RoleModal.vue', 'validateRoleCode', 'role_code', 'candidate'],
  ['src/views/system/modules/DictModal.vue', 'validateDictCode', 'dict_code', 'candidate'],
  ['src/views/system/modules/PermissionModal.vue', 'validatePerms', 'permission_perms', 'candidate'],
  ['src/views/system/modules/SysDepartRoleModal.vue', 'validateRoleCode', 'depart_role_code', 'candidate'],
  ['src/views/modules/message/modules/SysMessageTemplateModal.vue', 'validateTemplateCode', 'message_template_code', 'candidate'],
  ['src/views/account/settings/BaseSetting.vue', 'validatePhone', 'profile_phone', '13900000002'],
  ['src/views/account/settings/BaseSetting.vue', 'validateEmail', 'profile_email', 'candidate@example.invalid']
]
const rules = [
  ['src/views/system/modules/SysPositionModal.vue', 'code', 'position_code'],
  ['src/views/system/modules/SysFillRuleModal.vue', 'ruleCode', 'fill_rule_code'],
  ['src/views/system/modules/SysCheckRuleModal.vue', 'ruleCode', 'check_rule_code'],
  ['src/views/system/modules/SysDataSourceModal.vue', 'code', 'data_source_code']
]

for (const [file, method, purpose, value] of direct) {
  test(`${purpose}: real form sends named purpose and exact persisted exclusion`, async () => {
    const h = mount(file)
    h.i[method]({}, value, h.callback)
    await flush()
    assert.deepEqual(h.calls, [{ purpose, fieldVal: value, dataId: purpose.startsWith('profile_') ? 'own-id' : 'edited-id' }])
    assert.deepEqual(h.callbacks, [undefined])
  })
  test(`${purpose}: duplicate, permission rejection and network failure complete validation`, async () => {
    for (const reply of [{ success: false, code: 500, message: '已有记录' }, { success: false, code: 403, message: '权限已收回' }, new Error('offline')]) {
      const h = mount(file, reply)
      h.i[method]({}, value, h.callback)
      await flush()
      assert.equal(h.callbacks.length, 1)
      assert.ok(typeof h.callbacks[0] === 'string' ? h.callbacks[0].length : h.callbacks[0].message.length)
    }
  })
}

for (const [file, field, purpose] of rules) {
  test(`${purpose}: real form rule uses shared named validator and completes failures`, async () => {
    for (const reply of [{ success: true, code: 200 }, { success: false, code: 403, message: '权限已收回' }, new Error('offline')]) {
      const h = mount(file, reply)
      h.i.validatorRules[field].rules.find(rule => typeof rule.validator === 'function').validator({}, 'candidate', h.callback)
      await flush()
      assert.deepEqual(h.calls, [{ purpose, fieldVal: 'candidate', dataId: 'edited-id' }])
      assert.equal(h.callbacks.length, 1)
      if (reply.success === true) assert.equal(h.callbacks[0], undefined)
      else assert.ok(typeof h.callbacks[0] === 'string' ? h.callbacks[0].length : h.callbacks[0].message.length)
    }
  })
}

test('user creation keeps no persisted exclusion and optional empty work number makes no probe', async () => {
  const h = mount('src/views/system/modules/UserModal.vue')
  h.i.userId = ''
  h.i.validateUsername({}, 'candidate', h.callback)
  await flush()
  assert.deepEqual(h.calls, [{ purpose: 'user_username', fieldVal: 'candidate', dataId: '' }])
  h.i.validateWorkNo({}, '', h.callback)
  await flush()
  assert.equal(h.calls.length, 1)
  assert.deepEqual(h.callbacks, [undefined, undefined])
})

test('user editor discards duplicate validation callback after session changes', async () => {
  const h = mount('src/views/system/modules/UserModal.vue')
  h.i.validateUsername({}, 'candidate', h.callback)
  h.i.sessionVersion++
  await flush()
  assert.deepEqual(h.callbacks, [])
})
