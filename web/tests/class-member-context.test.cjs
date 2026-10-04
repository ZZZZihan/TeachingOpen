const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const cp = require('node:child_process')
const vm = require('node:vm')
const babel = require('@babel/core')

const root = path.resolve(__dirname, '..')
const sourceRef = process.env.SOURCE_REF || ''
const files = {
  panel: 'src/views/system/modules/DeptUserInfo.vue',
  selector: 'src/views/system/modules/SelectUserModal.vue',
  editor: 'src/views/system/modules/UserModal.vue',
  roles: 'src/views/system/modules/DeptRoleUserModal.vue'
}
const read = file => sourceRef
  ? cp.execFileSync('git', ['show', `${sourceRef}:web/${file}`], { cwd: root, encoding: 'utf8' })
  : fs.readFileSync(path.join(root, file), 'utf8')
const plain = value => JSON.parse(JSON.stringify(value))
const flush = () => new Promise(resolve => setImmediate(resolve))
const dept = key => ({ id: `class-${key}`, departName: `合成班 ${key}`, orgCategory: '3' })
const user = (key, suffix = '') => ({ id: `user-${key}${suffix}`, username: `student-${key}${suffix}`, realname: `合成学生 ${key}${suffix}`, userIdentity: '1', avatar: `avatar-${key}${suffix}` })
const page = (records, total = records.length) => ({ success: true, result: { records, total } })
const roles = key => [{ id: `role-${key}`, roleName: `角色 ${key}`, roleCode: 'student' }]

// Execute actual SFC scripts and inherited methods, with controlled server responses,
// confirmation callbacks, Vue nextTick, timers and Antd form validation. No HTTP or browser.
// Observe abandoned old-code Promise chains without changing the product's error behavior.
function observed(promise) {
  promise.catch(() => {})
  return {
    then: (...args) => observed(promise.then(...args)),
    catch: (...args) => observed(promise.catch(...args)),
    finally: (...args) => observed(promise.finally(...args))
  }
}
function environment() {
  const calls = [], notices = [], confirms = [], ticks = [], timers = [], events = [], transports = []
  const request = method => (url, data) => observed(new Promise((resolve, reject) => {
    calls.push({ method, url, data: plain(data || {}), resolve, reject })
  }))
  return { calls, notices, confirms, ticks, timers, events, transports, request }
}
function mount(kind, env = environment()) {
  const values = {}, fields = [], validations = [], localEvents = [], listeners = {}
  const form = {
    resetFields() { for (const key of Object.keys(values)) delete values[key] },
    setFieldsValue(value) { fields.push(plain(value)); Object.assign(values, value) },
    getFieldValue: key => values[key],
    validateFields(...args) { const callback = args.find(value => typeof value === 'function'); if (callback) validations.push(callback) },
    isFieldsTouched: () => false
  }
  const context = {
    component: null, JeecgListMixin: null, SelectUserModal: {}, UserModal: {}, DeptRoleUserModal: {},
    JEllipsis: {}, JImageUpload: {}, departWindow: {}, JSelectPosition: {},
    console: { log() {} }, Vue: { ls: { get: () => undefined } }, ACCESS_TOKEN: 'synthetic-unused',
    filterObj: null, URL, Promise,
    setTimeout(callback) { env.timers.push(callback); return env.timers.length }, clearTimeout() {},
    pick: (object, ...keys) => Object.fromEntries(keys.filter(key => key in object).map(key => [key, object[key]])),
    moment: value => ({ format: () => value }), disabledAuthFilter: () => false,
    getAction: env.request('GET'), postAction: env.request('POST'), deleteAction: env.request('DELETE'),
    httpAction: (url, data, method) => env.request(method.toUpperCase())(url, data),
    addUser: env.request('POST').bind(null, '/sys/user/add'), editUser: env.request('PUT').bind(null, '/sys/user/edit'),
    queryMySubRole: env.request('GET').bind(null, '/sys/role/queryMySubRole'), queryUserRole: env.request('GET').bind(null, '/sys/user/queryUserRole'),
    duplicateCheck: env.request('GET').bind(null, '/sys/duplicate/check'), initDictOptions: env.request('GET'),
    uploadRequest(options) { env.transports.push(options); return { abort() {} } },
    downFile: env.request('DOWNLOAD'), getFileAccessHttpUrl: value => value,
    document: { body: { clientWidth: 1024 } }, window: { _CONFIG: { domianURL: '' }, innerWidth: 1024 }
  }
  vm.createContext(context)
  vm.runInContext(read('src/utils/util.js').match(/export function filterObj\(obj\) \{[\s\S]*?\n\}/)[0].replace('export ', ''), context)
  if (kind === 'panel') {
    const script = read('src/mixins/JeecgListMixin.js').replace(/^import .*$/gm, '').replace('export const JeecgListMixin =', 'JeecgListMixin =')
    vm.runInContext(babel.transformSync(script, { cwd: root, babelrc: false, configFile: false, presets: [[require.resolve('@vue/babel-preset-app'), { useBuiltIns: false }]] }).code, context)
  }
  const source = read(files[kind])
  vm.runInContext(source.match(/<script>([\s\S]*?)<\/script>/)[1].replace(/^\s*import [^\n]*$/gm, '').replace('export default', 'component ='), context)
  const component = context.component, definitions = [...(component.mixins || []), component]
  const instance = {
    $refs: {}, $form: { createForm: () => form }, $set(object, key, value) { object[key] = value }, $delete(object, key) { delete object[key] },
    $nextTick(callback) { if (callback) env.ticks.push({ owner: instance, callback }); else return Promise.resolve() },
    $message: Object.fromEntries(['success', 'warning', 'error', 'info'].map(type => [type, text => env.notices.push({ owner: instance, type, text })])),
    $warning(value) { env.notices.push({ owner: instance, type: 'warning', text: value.title }) },
    $confirm(value) { env.confirms.push({ ...value, owner: instance }); return { destroy() {} } },
    $emit(name, ...args) { localEvents.push({ name, args }); env.events.push({ owner: instance, name, args }); listeners[name]?.(...args) }
  }
  for (const definition of definitions) for (const [key, fn] of Object.entries(definition.methods || {})) instance[key] = fn.bind(instance)
  for (const definition of definitions) Object.assign(instance, definition.data?.call(instance) || {})
  for (const definition of definitions) for (const [key, fn] of Object.entries(definition.computed || {})) Object.defineProperty(instance, key, { configurable: true, get: () => (typeof fn === 'function' ? fn : fn.get).call(instance) })
  const h = { i: instance, component, source, values, fields, validations, form, events: localEvents, listeners, env,
    created() { for (const definition of definitions) definition.created?.call(instance) },
    ticks() { for (const tick of env.ticks.splice(0)) tick.callback() },
    timers() { for (const callback of env.timers.splice(0)) callback() },
    validate(error = null, supplied = values) { assert.ok(validations.length, 'actual form requested validation'); validations.shift()(error, { ...supplied }) },
    destroy() { for (const definition of definitions) definition.beforeDestroy?.call(instance); instance._isDestroyed = true }
  }
  if (kind === 'panel') {
    h.selector = mount('selector', env); h.editor = mount('editor', env); h.roles = mount('roles', env)
    instance.$refs.selectUserModal = h.selector.i; instance.$refs.modalForm = h.editor.i; instance.$refs.deptRoleUser = h.roles.i
    h.selector.listeners.selectFinished = (...args) => instance.selectOK(...args)
    h.editor.listeners.ok = (...args) => instance.modalFormOk(...args)
  }
  return h
}
const calls = (h, method, suffix = '') => h.env.calls.filter(call => call.method === method && (!suffix || call.url.endsWith(suffix)))
const memberReads = h => calls(h, 'GET', '/departUserList')
const writes = h => h.env.calls.filter(call => call.method !== 'GET' || call.url.endsWith('/removeAll'))
async function ready(h, key, rows = [user(key)]) {
  h.i.open(dept(key)); memberReads(h).at(-1).resolve(page(rows)); await flush()
}
function select(h, rows) { h.i.onSelectChange(rows.map(row => row.id), rows) }
function displayed(h, record) { return h.i.dataSource.find(row => row.id === record.id) || record }
function rowPrompt(h, record) {
  record = displayed(h, record)
  if (/@click(?:\.prevent)?="confirmDelete\(record\)"/.test(h.source)) { h.i.confirmDelete(record); return h.env.confirms.at(-1) }
  assert.match(h.source, /@confirm="\(\) => handleDelete\(record.id\)"/, 'execute the actual rendered row cancellation binding')
  return { onOk: () => h.i.handleDelete(record.id) }
}
function openSelector(h) {
  const count = calls(h, 'GET', '/sys/user/list').length
  h.i.handleAddUserDepart()
  // Old parent simply exposes the already mounted selector. Run its actual list method
  // when the opening path itself does not issue a read, as its created hook does.
  if (calls(h, 'GET', '/sys/user/list').length === count) h.selector.i.loadData(1)
  return calls(h, 'GET', '/sys/user/list').at(-1)
}
async function selectorReady(h, rows) { openSelector(h).resolve(page(rows)); await flush() }
async function complete(h, call, response = { success: true, message: '合成成功' }) { call.resolve(response); await flush() }
async function settleEditorReads(h, key, since = 0) {
  for (const call of h.env.calls.slice(since).filter(value => value.method === 'GET')) {
    if (call.url.endsWith('/queryMySubRole')) call.resolve({ success: true, result: roles(key) })
    else if (call.url.endsWith('/queryUserRole')) call.resolve({ success: true, result: [`role-${key}`] })
    else if (call.url.endsWith('/userDepartList')) call.resolve({ success: true, result: [{ key: `class-${key}`, title: `班 ${key}` }] })
  }
  await flush(); h.ticks(); h.timers(); await flush()
}
async function editorReady(h, key, mode = 'edit') {
  const since = h.env.calls.length
  if (mode === 'add') h.i.handleAdd(); else h.i.handleEdit(displayed(h, user(key)))
  await settleEditorReads(h.editor, key, since)
  // The visible role select is user controlled. Old add() does not auto-select the
  // student role after its asynchronous catalog arrives; choose it as an ordinary user does.
  if (mode === 'add' && !h.editor.i.selectedRole.length) h.editor.i.selectedRole = [`role-${key}`]
}
async function settleRoleReads(h, key, since = 0) {
  for (const call of h.env.calls.slice(since).filter(value => value.method === 'GET')) {
    if (call.url.endsWith('/getDeptRoleList')) call.resolve({ success: true, result: roles(key) })
    else if (call.url.endsWith('/getDeptRoleByUserId')) call.resolve({ success: true, result: [{ droleId: `role-${key}` }] })
  }
  await flush()
}
function importFile(key) { return { uid: `file-${key}`, name: `students-${key}.xlsx`, type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' } }
function prepareImport(h, file) {
  const binding = h.source.match(/:before-upload="([A-Za-z0-9_]+)"/) || h.source.match(/:beforeUpload="([A-Za-z0-9_]+)"/)
  if (binding) return h.i[binding[1]](file)
  h.i.handleImportExcel({ file: { ...file, status: 'uploading' }, fileList: [file] })
  return true
}
function transportImport(h, file) {
  const options = { file, action: h.i.url.importStudentUrl, onError() {}, onSuccess() {}, onProgress() {} }
  const binding = h.source.match(/:customRequest="([A-Za-z0-9_]+)"/) || h.source.match(/:custom-request="([A-Za-z0-9_]+)"/)
  if (binding) h.i[binding[1]](options)
  else h.env.transports.push(options) // Antd default transport uses this actual action prop.
  return options
}

test('opening B clears A selected users, stale list and pagination before B response', async () => {
  const h = mount('panel'); await ready(h, 'a'); select(h, [user('a')]); h.i.ipagination.current = 4; h.i.ipagination.total = 99
  h.i.open(dept('b')); assert.deepEqual(plain(h.i.selectedRowKeys), []); assert.deepEqual(plain(h.i.selectionRows), [])
  assert.deepEqual(plain(h.i.dataSource), []); assert.equal(h.i.ipagination.current, 1); assert.equal(h.i.ipagination.total, 0)
  assert.equal(memberReads(h).at(-1).data.depId, 'class-b'); memberReads(h).at(-1).resolve(page([user('b')])); await flush()
  h.i.batchDel(); assert.equal(writes(h).length, 0); assert.equal(h.env.confirms.length, 0)
})
for (const operation of ['batchDel', 'handleRemoveAll', 'row']) {
  for (const transition of ['switch B', 'reopen A', 'clear']) {
    test(`${operation} captured in A cannot dispatch after ${transition}`, async () => {
      const h = mount('panel'); await ready(h, 'a'); select(h, [user('a')])
      const old = operation === 'row' ? rowPrompt(h, user('a')) : (h.i[operation](), h.env.confirms.at(-1))
      assert.ok(old, 'A action creates an actionable confirmation')
      if (transition === 'clear') h.i.clearList(); else await ready(h, transition === 'switch B' ? 'b' : 'a')
      await old.onOk(); assert.equal(writes(h).length, 0)
    })
  }
}
for (const operation of ['batchDel', 'handleRemoveAll', 'row']) {
  test(`control: normal B ${operation} preserves the backend contract and refreshes B`, async () => {
    const h = mount('panel'); await ready(h, 'b'); select(h, [user('b')])
    const prompt = operation === 'row' ? rowPrompt(h, user('b')) : (h.i[operation](), h.env.confirms.at(-1))
    prompt.onOk(); assert.equal(writes(h).length, 1); const write = writes(h)[0]
    if (operation === 'batchDel') { assert.equal(write.method, 'DELETE'); assert.equal(write.url, '/sys/user/deleteUserInDepartBatch'); assert.equal(write.data.depId, 'class-b'); assert.deepEqual(write.data.userIds.split(',').filter(Boolean), ['user-b']) }
    else if (operation === 'handleRemoveAll') { assert.equal(write.method, 'GET'); assert.equal(write.url, '/sys/sysDepart/removeAll'); assert.deepEqual(write.data, { id: 'class-b' }) }
    else { assert.equal(write.method, 'DELETE'); assert.equal(write.url, '/sys/user/deleteUserInDepart'); assert.deepEqual(write.data, { depId: 'class-b', userId: 'user-b' }) }
    await complete(h, write); assert.equal(memberReads(h).at(-1).data.depId, 'class-b')
  })
}
test('changed user selection invalidates a bulk confirmation before dispatch', async () => {
  const h = mount('panel'); await ready(h, 'a', [user('a'), user('a', '-other')]); select(h, [user('a')]); h.i.batchDel(); const old = h.env.confirms.at(-1)
  select(h, [user('a', '-other')]); await old.onOk(); assert.equal(writes(h).length, 0)
})
test('late A checkbox event cannot inject foreign user IDs into B cancellation', async () => {
  const h = mount('panel'); await ready(h, 'a'); await ready(h, 'b'); select(h, [user('a')]); h.i.batchDel()
  for (const prompt of h.env.confirms) await prompt.onOk()
  assert.equal(writes(h).length, 0); assert.deepEqual(plain(h.i.selectedRowKeys), [])
})
for (const operation of ['batchDel', 'handleRemoveAll', 'row']) {
  test(`B ${operation} ignores repeated clicks and duplicate confirmation callbacks`, async () => {
    const h = mount('panel'); await ready(h, 'b'); select(h, [user('b')])
    const prompt = operation === 'row' ? rowPrompt(h, user('b')) : (h.i[operation](), h.env.confirms.at(-1))
    if (operation !== 'row') { h.i[operation](); assert.equal(h.env.confirms.length, 1) }
    prompt.onOk(); prompt.onOk(); assert.equal(writes(h).length, 1)
  })
}
test('older A confirmation cannot release or submit an active B confirmation', async () => {
  const h = mount('panel'); await ready(h, 'a'); h.i.handleRemoveAll(); const old = h.env.confirms.at(-1)
  await ready(h, 'b'); select(h, [user('b')]); h.i.batchDel(); const current = h.env.confirms.at(-1)
  old.onCancel?.(); old.onOk(); h.i.batchDel(); assert.equal(writes(h).length, 0); assert.equal(h.env.confirms.length, 2)
  current.onOk(); assert.equal(writes(h).length, 1); assert.equal(writes(h)[0].data.depId, 'class-b')
})
test('late A list success cannot overwrite B user list or count', async () => {
  const h = mount('panel'); h.i.open(dept('a')); const a = memberReads(h).at(-1); h.i.open(dept('b')); const b = memberReads(h).at(-1)
  b.resolve(page([user('b')], 12)); await flush(); a.resolve(page([user('a')], 99)); await flush()
  assert.deepEqual(plain(h.i.dataSource), [user('b')]); assert.equal(h.i.ipagination.total, 12); assert.equal(h.i.loading, false)
})
test('newer member query within B wins when older response arrives last', async () => {
  const h = mount('panel'); await ready(h, 'b'); h.i.loadData(); const old = memberReads(h).at(-1); h.i.loadData(); const current = memberReads(h).at(-1)
  current.resolve(page([user('b', '-new')], 2)); await flush(); old.resolve(page([user('b', '-old')], 9)); await flush()
  assert.equal(h.i.dataSource[0].id, 'user-b-new'); assert.equal(h.i.ipagination.total, 2)
})
for (const failure of ['network', 'business']) {
  test(`late A list ${failure} cannot publish a notice or unlock B pending read`, async () => {
    const h = mount('panel'); h.i.open(dept('a')); const a = memberReads(h).at(-1); h.i.open(dept('b')); const b = memberReads(h).at(-1); const notices = h.env.notices.length
    if (failure === 'network') a.reject(new Error('synthetic offline')); else a.resolve({ success: false, message: 'SQL secret' })
    await flush(); assert.equal(h.i.loading, true); assert.equal(h.env.notices.length, notices)
    b.resolve(page([user('b')])); await flush(); assert.equal(h.i.dataSource[0].id, 'user-b')
  })
  test(`current B member list ${failure} resets busy state and can retry in B`, async () => {
    const h = mount('panel'); await ready(h, 'b'); h.i.loadData(); const request = memberReads(h).at(-1)
    if (failure === 'network') request.reject(new Error('synthetic offline')); else request.resolve({ success: false, message: 'SQL secret' })
    await flush(); assert.equal(h.i.loading, false); assert.ok(h.i.listError || h.env.notices.some(value => ['error', 'warning'].includes(value.type)))
    assert.doesNotMatch(String(h.i.listError || '') + h.env.notices.map(value => value.text).join(''), /SQL secret/)
    h.i.loadData(); assert.equal(memberReads(h).at(-1).data.depId, 'class-b'); memberReads(h).at(-1).resolve(page([user('b')])); await flush(); assert.equal(h.i.dataSource[0].id, 'user-b')
  })
}
for (const disposal of ['clear', 'destroy']) {
  test(`late member list after ${disposal} cannot repopulate an inactive panel`, async () => {
    const h = mount('panel'); h.i.open(dept('a')); const old = memberReads(h).at(-1); if (disposal === 'clear') h.i.clearList(); else h.destroy()
    const rows = plain(h.i.dataSource), notices = h.env.notices.length; old.resolve(page([user('a')])); await flush()
    assert.deepEqual(plain(h.i.dataSource), rows); assert.equal(h.env.notices.length, notices)
  })
}
test('malformed member rows never enter selection or cancellation and allow a valid retry', async () => {
  const h = mount('panel'); h.i.open(dept('b')); memberReads(h).at(-1).resolve(page([null])); await flush()
  assert.deepEqual(plain(h.i.dataSource), []); assert.equal(h.i.loading, false); assert.ok(h.i.listError)
  h.i.batchDel(); assert.equal(writes(h).length, 0); h.i.loadData(); memberReads(h).at(-1).resolve(page([user('b')])); await flush(); assert.equal(h.i.dataSource[0].id, 'user-b')
})
for (const operation of ['batchDel', 'handleRemoveAll', 'row']) {
  for (const success of [true, false]) {
    test(`already dispatched A ${operation} response (${success}) cannot refresh or deselect B`, async () => {
      const h = mount('panel'); await ready(h, 'a'); select(h, [user('a')]); const prompt = operation === 'row' ? rowPrompt(h, user('a')) : (h.i[operation](), h.env.confirms.at(-1))
      prompt.onOk(); const write = writes(h).at(-1); await ready(h, 'b'); select(h, [user('b')]); const reads = memberReads(h).length, notices = h.env.notices.length
      await complete(h, write, { success, message: '合成回应' }); assert.equal(memberReads(h).length, reads); assert.equal(h.env.notices.length, notices)
      assert.deepEqual(plain(h.i.selectedRowKeys), ['user-b']); assert.equal(h.i.dataSource[0].id, 'user-b')
    })
  }
}
test('selector reopened in B clears A selected users, table and query before its response', async () => {
  const h = mount('panel'); await ready(h, 'a'); await selectorReady(h, [user('a')]); select(h.selector, [user('a')]); h.selector.i.dataSource2 = [user('a')]
  h.selector.i.queryParam.username = 'A only'; h.selector.i.ipagination.current = 4; h.selector.i.ipagination.total = 99
  await ready(h, 'b'); openSelector(h)
  assert.deepEqual(plain(h.selector.i.selectedRowKeys), []); assert.deepEqual(plain(h.selector.i.dataSource1), []); assert.deepEqual(plain(h.selector.i.dataSource2), [])
  assert.equal(h.selector.i.ipagination.current, 1); assert.equal(h.selector.i.ipagination.total, 0); assert.equal(calls(h, 'GET', '/sys/user/list').at(-1).data.username, undefined)
})
test('old selector emission from A cannot add A users to B', async () => {
  const h = mount('panel'); await ready(h, 'a'); await selectorReady(h, [user('a')]); select(h.selector, [user('a')])
  h.selector.listeners.selectFinished = null; h.selector.i.handleOk(); const old = h.selector.events.find(value => value.name === 'selectFinished'); assert.ok(old)
  await ready(h, 'b'); h.i.selectOK(...old.args); assert.equal(calls(h, 'POST').length, 0)
})
test('control: a normal B selector confirmation adds only selected B users and refreshes B', async () => {
  const h = mount('panel'); await ready(h, 'b'); await selectorReady(h, [user('b')]); select(h.selector, [user('b')]); h.selector.i.handleOk()
  assert.equal(calls(h, 'POST').length, 1); assert.equal(calls(h, 'POST')[0].url, '/sys/user/editSysDepartWithUser'); assert.deepEqual(calls(h, 'POST')[0].data, { depId: 'class-b', userIdList: ['user-b'] })
  await complete(h, calls(h, 'POST')[0]); assert.equal(memberReads(h).at(-1).data.depId, 'class-b')
})
test('late A selector list cannot replace the B selectable-user table', async () => {
  const h = mount('panel'); await ready(h, 'a'); const a = openSelector(h); await ready(h, 'b'); const b = openSelector(h)
  b.resolve(page([user('b')], 12)); await flush(); a.resolve(page([user('a')], 99)); await flush()
  assert.deepEqual(plain(h.selector.i.dataSource1), [user('b')]); assert.equal(h.selector.i.ipagination.total, 12)
})
test('selector cannot emit IDs absent from its current displayed users', async () => {
  const h = mount('panel'); await ready(h, 'b'); await selectorReady(h, [user('b')]); select(h.selector, [user('a')]); h.selector.i.handleOk()
  assert.equal(calls(h, 'POST').length, 0); assert.deepEqual(plain(h.selector.i.selectedRowKeys), [])
})

test('a repeated selector OK or replayed B emission cannot dispatch duplicate additions', async () => {
  const h = mount('panel'); await ready(h, 'b'); await selectorReady(h, [user('b')]); select(h.selector, [user('b')]); h.selector.i.handleOk()
  const event = h.selector.events.find(value => value.name === 'selectFinished'); assert.ok(event)
  h.selector.i.handleOk(); h.i.selectOK(...event.args); assert.equal(calls(h, 'POST').length, 1)
})
test('B selector list failure blocks a stale selection and recovers on its next read', async () => {
  const h = mount('panel'); await ready(h, 'b'); await selectorReady(h, [user('b')]); select(h.selector, [user('b')]); h.selector.i.loadData()
  calls(h, 'GET', '/sys/user/list').at(-1).reject(new Error('synthetic offline')); await flush(); h.selector.i.handleOk()
  assert.equal(calls(h, 'POST').length, 0); assert.equal(h.selector.i.loading, false); assert.ok(h.selector.i.loadError)
  h.selector.i.loadData(); calls(h, 'GET', '/sys/user/list').at(-1).resolve(page([user('b')])); await flush(); select(h.selector, [user('b')]); h.selector.i.handleOk()
  assert.equal(calls(h, 'POST').length, 1); assert.equal(calls(h, 'POST')[0].data.depId, 'class-b')
})
test('legacy selector add() preserves its ordinary array event contract', async () => {
  const h = mount('selector'); h.i.add(); h.i.loadData(1); calls(h, 'GET', '/sys/user/list').at(-1).resolve(page([user('b')])); await flush()
  select(h, [user('b')]); h.i.handleOk(); const event = h.events.find(value => value.name === 'selectFinished')
  assert.deepEqual(plain(event.args), [['user-b']]); assert.equal(h.i.visible, false)
})
test('legacy selector direct visible entry still emits an array and clears a previous session', async () => {
  const h = mount('selector'); h.i.visible = true
  const watch = h.component.watch?.visible; if (watch) (typeof watch === 'function' ? watch : watch.handler).call(h.i, true, false)
  h.i.loadData(1); calls(h, 'GET', '/sys/user/list').at(-1).resolve(page([user('a')])); await flush(); select(h, [user('a')]); h.i.handleCancel()
  h.i.visible = true; if (watch) (typeof watch === 'function' ? watch : watch.handler).call(h.i, true, false)
  assert.deepEqual(plain(h.i.selectedRowKeys), [])
  h.i.loadData(1); calls(h, 'GET', '/sys/user/list').at(-1).resolve(page([user('b')])); await flush(); select(h, [user('b')]); h.i.handleOk()
  assert.deepEqual(plain(h.events.find(value => value.name === 'selectFinished').args), [['user-b']])
})
for (const failure of ['network', 'business']) {
  test(`B bulk cancellation ${failure} releases its lock and accepts a fresh confirmation`, async () => {
    const h = mount('panel'); await ready(h, 'b'); select(h, [user('b')]); h.i.batchDel(); h.env.confirms.at(-1).onOk(); const write = calls(h, 'DELETE').at(-1)
    if (failure === 'network') write.reject(new Error('synthetic offline')); else write.resolve({ success: false, message: 'SQL secret' })
    await flush(); assert.equal(Boolean(h.i.mutationLoading), false)
    h.i.batchDel(); const prompt = h.env.confirms.at(-1); prompt.onOk(); assert.equal(calls(h, 'DELETE').length, 2); assert.equal(calls(h, 'DELETE')[1].data.depId, 'class-b')
  })
}
for (const mode of ['add', 'edit']) {
  test(`A user ${mode} validation completing after switch B cannot submit or close B's editor`, async () => {
    const h = mount('panel'); await ready(h, 'a'); await editorReady(h, 'a', mode); h.editor.i.handleSubmit(); assert.equal(h.editor.validations.length, 1)
    await ready(h, 'b'); await editorReady(h, 'b', mode); h.editor.validate(null, { username: 'old-a', realname: '旧 A', birthday: null })
    assert.equal(calls(h, 'POST', '/sys/user/add').length + calls(h, 'PUT').length, 0); assert.equal(h.editor.i.visible, true)
  })
  test(`control: normal B user ${mode} submits its original identity and class and emits a compatible OK`, async () => {
    const h = mount('panel'); await ready(h, 'b'); await editorReady(h, 'b', mode); h.editor.i.handleSubmit()
    h.editor.validate(null, { username: 'student-b', realname: '合成学生 B', birthday: null }); const write = calls(h, mode === 'add' ? 'POST' : 'PUT').at(-1)
    assert.ok(write); assert.equal(write.url, mode === 'add' ? '/sys/user/add' : '/sys/user/edit'); assert.equal(write.data.selecteddeparts, 'class-b')
    if (mode === 'edit') assert.equal(write.data.id, 'user-b')
    await complete(h, write); assert.equal(memberReads(h).at(-1).data.depId, 'class-b'); assert.equal(h.editor.i.visible, false)
  })
}
test('late A user department and role reads cannot overwrite B editor identity or assignments', async () => {
  const h = mount('panel'); await ready(h, 'a'); h.i.handleEdit(displayed(h, user('a'))); const a = h.env.calls.filter(call => call.method === 'GET' && !call.url.endsWith('/departUserList'))
  await ready(h, 'b'); await editorReady(h, 'b'); const model = plain(h.editor.i.model), departs = plain(h.editor.i.userDepartModel.departIdList), selected = plain(h.editor.i.selectedRole)
  for (const call of a) {
    if (call.url.endsWith('/queryMySubRole')) call.resolve({ success: true, result: roles('a') })
    else if (call.url.endsWith('/queryUserRole')) call.resolve({ success: true, result: ['role-a'] })
    else if (call.url.endsWith('/userDepartList')) call.resolve({ success: true, result: [{ key: 'class-a', title: '班 A' }] })
  }
  await flush(); assert.deepEqual(plain(h.editor.i.model), model); assert.deepEqual(plain(h.editor.i.userDepartModel.departIdList), departs); assert.deepEqual(plain(h.editor.i.selectedRole), selected)
})
test('queued user form nextTick after clear cannot fill or revive the closed A editor', async () => {
  const h = mount('panel'); await ready(h, 'a'); h.i.handleEdit(displayed(h, user('a'))); h.i.clearList(); const fields = h.editor.fields.length
  h.editor.ticks(); h.editor.timers(); assert.equal(h.editor.i.visible, false); assert.equal(h.editor.fields.length, fields)
})
test('already dispatched A user edit completion cannot close B form or refresh B membership', async () => {
  const h = mount('panel'); await ready(h, 'a'); await editorReady(h, 'a'); h.editor.i.handleSubmit(); h.editor.validate(null, { realname: 'A changed', birthday: null }); const a = calls(h, 'PUT').at(-1); assert.ok(a)
  await ready(h, 'b'); await editorReady(h, 'b'); const reads = memberReads(h).length, notices = h.env.notices.length, model = plain(h.editor.i.model)
  await complete(h, a); assert.equal(memberReads(h).length, reads); assert.equal(h.env.notices.length, notices); assert.equal(h.editor.i.visible, true); assert.deepEqual(plain(h.editor.i.model), model)
})
test('legacy UserModal edit(record) preserves ordinary user management save and zero-argument OK', async () => {
  const h = mount('editor'); h.i.edit(user('b')); await settleEditorReads(h, 'b'); h.i.handleSubmit(); h.validate(null, { realname: 'B changed', birthday: null }); const write = calls(h, 'PUT').at(-1)
  assert.ok(write); assert.equal(write.data.id, 'user-b'); assert.equal(write.data.selecteddeparts, 'class-b'); await complete(h, write)
  assert.deepEqual(h.events.filter(value => value.name === 'ok').map(value => value.args), [[]]); assert.equal(h.i.visible, false)
})
test('B user submit locks both pending validation and the in-flight save against repeated clicks', async () => {
  const h = mount('panel'); await ready(h, 'b'); await editorReady(h, 'b'); h.editor.i.handleSubmit(); h.editor.i.handleSubmit()
  assert.equal(h.editor.validations.length, 1); h.editor.validate(null, { realname: 'B changed', birthday: null }); h.editor.i.handleSubmit()
  assert.equal(calls(h, 'PUT').length, 1); assert.equal(h.editor.validations.length, 0)
})
test('A role assignment opened before switch B cannot save after switch, and normal B assignment still works', async () => {
  const h = mount('panel'); await ready(h, 'a'); h.i.handleDeptRole(displayed(h, user('a'))); await settleRoleReads(h.roles, 'a')
  await ready(h, 'b'); h.roles.i.handleSubmit(); assert.equal(calls(h, 'POST').length, 0); assert.equal(h.roles.i.visible, false)
  const since = h.env.calls.length; h.i.handleDeptRole(displayed(h, user('b'))); await settleRoleReads(h.roles, 'b', since); h.roles.i.handleSubmit()
  assert.equal(calls(h, 'POST').length, 1); assert.equal(calls(h, 'POST')[0].url, '/sys/sysDepartRole/deptRoleUserAdd'); assert.equal(calls(h, 'POST')[0].data.userId, 'user-b'); assert.equal(calls(h, 'POST')[0].data.newRoleId, 'role-b')
})
test('late A assigned-role and available-role reads cannot replace B role selections', async () => {
  const h = mount('panel'); await ready(h, 'a'); h.i.handleDeptRole(displayed(h, user('a'))); const a = h.env.calls.filter(call => call.url.includes('/sys/sysDepartRole/'))
  await ready(h, 'b'); const since = h.env.calls.length; h.i.handleDeptRole(displayed(h, user('b'))); await settleRoleReads(h.roles, 'b', since)
  const selected = plain(h.roles.i.designNameValue), options = plain(h.roles.i.designNameOption)
  for (const call of a) call.resolve({ success: true, result: call.url.endsWith('/getDeptRoleList') ? roles('a') : [{ droleId: 'role-a' }] })
  await flush(); assert.deepEqual(plain(h.roles.i.designNameValue), selected); assert.deepEqual(plain(h.roles.i.designNameOption), options); assert.equal(h.roles.i.userId, 'user-b')
})
test('already dispatched A role save completion cannot close a newly opened B assignment', async () => {
  const h = mount('panel'); await ready(h, 'a'); h.i.handleDeptRole(displayed(h, user('a'))); await settleRoleReads(h.roles, 'a'); h.roles.i.handleSubmit(); const a = calls(h, 'POST').at(-1); assert.ok(a)
  await ready(h, 'b'); const since = h.env.calls.length; h.i.handleDeptRole(displayed(h, user('b'))); await settleRoleReads(h.roles, 'b', since); const notices = h.env.notices.length
  await complete(h, a); assert.equal(h.roles.i.visible, true); assert.equal(h.roles.i.userId, 'user-b'); assert.equal(h.env.notices.length, notices)
})
test('legacy role add(record, departId) preserves the ordinary request and zero-argument OK', async () => {
  const h = mount('roles'); h.i.add(user('b'), 'class-b'); await settleRoleReads(h, 'b'); h.i.handleSubmit(); const write = calls(h, 'POST').at(-1)
  assert.ok(write); assert.equal(write.data.userId, 'user-b'); assert.equal(write.data.newRoleId, 'role-b'); await complete(h, write)
  assert.deepEqual(h.events.filter(value => value.name === 'ok').map(value => value.args), [[]]); assert.equal(h.i.visible, false)
})
test('role save waits for both reads, retries failed loading, and sends only one pending write', async () => {
  const h = mount('roles'); h.i.add(user('b'), 'class-b'); calls(h, 'GET', '/getDeptRoleList').at(-1).resolve({ success: true, result: roles('b') }); await flush()
  h.i.handleSubmit(); assert.equal(calls(h, 'POST').length, 0)
  calls(h, 'GET', '/getDeptRoleByUserId').at(-1).reject(new Error('synthetic offline')); await flush(); h.i.handleSubmit(); assert.equal(calls(h, 'POST').length, 0)
  const since = h.env.calls.length; h.i.loadDesformList(); await settleRoleReads(h, 'b', since); h.i.handleSubmit(); h.i.handleSubmit()
  assert.equal(calls(h, 'POST').length, 1); assert.equal(calls(h, 'POST')[0].data.userId, 'user-b')
})
test('editing A configured roles must not request removal of a role assigned outside A options', async () => {
  const h = mount('roles'); h.i.add(user('a'), 'class-a')
  calls(h, 'GET', '/getDeptRoleList').at(-1).resolve({ success: true, result: roles('a') })
  calls(h, 'GET', '/getDeptRoleByUserId').at(-1).resolve({ success: true, result: [{ droleId: 'role-a' }, { droleId: 'role-b' }] })
  await flush(); h.i.designNameChange(['role-a']); h.i.handleSubmit(); const write = calls(h, 'POST').at(-1); assert.ok(write)
  assert.deepEqual(write.data.oldRoleId.split(',').filter(Boolean), ['role-a']); assert.deepEqual(write.data.newRoleId.split(',').filter(Boolean), ['role-a'])
})
test('queued A import transport is refused after switch B before sending any upload', async () => {
  const h = mount('panel'); await ready(h, 'a'); const file = importFile('a'); assert.notEqual(prepareImport(h, file), false)
  await ready(h, 'b'); transportImport(h, file); assert.equal(h.env.transports.length, 0)
})
test('late A import completion cannot notify, clear selection or refresh B membership', async () => {
  const h = mount('panel'); await ready(h, 'a'); const file = importFile('a'); prepareImport(h, file); transportImport(h, file); assert.equal(h.env.transports.length, 1)
  await ready(h, 'b'); select(h, [user('b')]); const reads = memberReads(h).length, notices = h.env.notices.length
  h.i.handleImportExcel({ file: { ...file, status: 'done', response: { success: true, message: 'A imported' } }, fileList: [] }); await flush()
  assert.equal(memberReads(h).length, reads); assert.equal(h.env.notices.length, notices); assert.deepEqual(plain(h.i.selectedRowKeys), ['user-b'])
})
test('control: B import preserves its class action and successful feedback refreshes B', async () => {
  const h = mount('panel'); await ready(h, 'b'); const file = importFile('b'); assert.notEqual(prepareImport(h, file), false); transportImport(h, file)
  assert.equal(h.env.transports.length, 1); assert.equal(h.env.transports[0].action, '/api/sys/user/importStudent?departIds=class-b')
  const reads = memberReads(h).length; h.i.handleImportExcel({ file: { ...file, status: 'done', response: { success: true, message: 'B imported' } }, fileList: [] }); await flush()
  assert.equal(memberReads(h).length, reads + 1); assert.equal(memberReads(h).at(-1).data.depId, 'class-b')
})
test('current B import failure permits another upload without stale A completion unlocking it', async () => {
  const h = mount('panel'); await ready(h, 'a'); const a = importFile('a'); prepareImport(h, a); transportImport(h, a)
  await ready(h, 'b'); const b = importFile('b'); assert.notEqual(prepareImport(h, b), false); transportImport(h, b)
  h.i.handleImportExcel({ file: { ...a, status: 'done', response: { success: true } }, fileList: [] }); await flush()
  assert.equal(prepareImport(h, importFile('b-duplicate')), false)
  h.i.handleImportExcel({ file: { ...b, status: 'error', msg: 'synthetic offline' }, fileList: [] }); await flush()
  assert.notEqual(prepareImport(h, importFile('b-retry')), false)
})
