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
  panel: 'src/views/system/modules/DeptCourseInfo.vue',
  selector: 'src/views/teaching/modules/SelectCourseModal.vue',
  editor: 'src/views/teaching/modules/TeachingCourseDeptModal.vue'
}
const read = file => sourceRef
  ? cp.execFileSync('git', ['show', `${sourceRef}:web/${file}`], { cwd: root, encoding: 'utf8' })
  : fs.readFileSync(path.join(root, file), 'utf8')
const flush = () => new Promise(resolve => setImmediate(resolve))
const plain = value => JSON.parse(JSON.stringify(value))
const dept = key => ({ id: `class-${key}`, departName: `合成班 ${key}`, orgCategory: '3' })
const relation = (key, suffix = '') => ({ id: `relation-${key}${suffix}`, deptId: `class-${key}`, courseId: `course-${key}${suffix}`, courseName: `课程 ${key}${suffix}`, openTime: '2026-10-03 09:00:00' })
const course = key => ({ id: `course-${key}`, courseName: `课程 ${key}` })
const page = (records, total = records.length) => ({ success: true, result: { records, total } })

// These tests execute the real SFC scripts and inherited list methods. APIs, form validation,
// Vue nextTick and confirmations are controlled; no browser, service or database is involved.
// Keep an unobserved rejection in the old product's abandoned Promise chain from escaping
// into another test. Product error handlers still run normally and must expose recovery state.
function observed(promise) {
  promise.catch(() => {})
  return {
    then: (...args) => observed(promise.then(...args)),
    catch: (...args) => observed(promise.catch(...args)),
    finally: (...args) => observed(promise.finally(...args))
  }
}
function environment() {
  const calls = [], notices = [], confirms = [], ticks = [], events = []
  const request = method => (url, data) => observed(new Promise((resolve, reject) => {
    calls.push({ method, url, data: plain(data || {}), raw: data, resolve, reject })
  }))
  return { calls, notices, confirms, ticks, events, request }
}
function mount(kind, env = environment()) {
  const values = {}, validations = [], localEvents = [], listeners = {}
  const form = {
    resetFields() { for (const key of Object.keys(values)) delete values[key] },
    setFieldsValue(value) { Object.assign(values, value) },
    validateFields(callback) { validations.push(callback) },
    isFieldsTouched() { return false }
  }
  const context = {
    component: null, JeecgListMixin: null, SelectCourseModal: {}, TeachingCourseDeptModal: {}, JDate: {},
    console: { log() {} }, Vue: { ls: { get: () => undefined } }, ACCESS_TOKEN: 'synthetic-unused',
    filterObj: null, URL, Promise, setTimeout, clearTimeout,
    pick: (object, ...keys) => Object.fromEntries(keys.filter(key => key in object).map(key => [key, object[key]])),
    getAction: env.request('GET'), postAction: env.request('POST'), deleteAction: env.request('DELETE'), httpAction: (url, body, method) => env.request(method.toUpperCase())(url, body),
    downFile: env.request('DOWNLOAD'), getFileAccessHttpUrl: value => value,
    window: { _CONFIG: { domianURL: '' } }
  }
  vm.createContext(context)
  vm.runInContext(read('src/utils/util.js').match(/export function filterObj\(obj\) \{[\s\S]*?\n\}/)[0].replace('export ', ''), context)
  if (kind === 'panel') {
    const script = read('src/mixins/JeecgListMixin.js').replace(/^import .*$/gm, '').replace('export const JeecgListMixin =', 'JeecgListMixin =')
    vm.runInContext(babel.transformSync(script, { cwd: root, babelrc: false, configFile: false, presets: [[require.resolve('@vue/babel-preset-app'), { useBuiltIns: false }]] }).code, context)
  }
  const source = read(files[kind])
  vm.runInContext(source.match(/<script>([\s\S]*?)<\/script>/)[1].replace(/^\s*import [^\n]*$/gm, '').replace('export default', 'component ='), context)
  const component = context.component, mixins = component.mixins || []
  const instance = {
    $refs: {}, $form: { createForm: () => form },
    $set(object, key, value) { object[key] = value },
    $nextTick(callback) { if (callback) env.ticks.push({ owner: instance, callback }); else return Promise.resolve() },
    $message: Object.fromEntries(['success', 'warning', 'error', 'info'].map(type => [type, text => env.notices.push({ owner: instance, type, text })])),
    $confirm(value) { env.confirms.push({ ...value, owner: instance }); return { destroy() {} } },
    $emit(name, ...args) { localEvents.push({ name, args }); env.events.push({ owner: instance, name, args }); listeners[name]?.(...args) }
  }
  for (const definition of [...mixins, component]) Object.assign(instance, definition.data?.call(instance) || {})
  for (const definition of [...mixins, component]) for (const [key, fn] of Object.entries(definition.methods || {})) instance[key] = fn.bind(instance)
  for (const definition of [...mixins, component]) for (const [key, fn] of Object.entries(definition.computed || {})) Object.defineProperty(instance, key, { configurable: true, get: () => (typeof fn === 'function' ? fn : fn.get).call(instance) })
  const h = { i: instance, component, source, values, validations, form, events: localEvents, listeners, env,
    ticks() { for (const tick of env.ticks.splice(0)) tick.callback() },
    validate(error = null, supplied = values) { assert.ok(validations.length, 'the actual form must request validation'); validations.shift()(error, { ...supplied }) },
    destroy() { for (const definition of [...mixins, component]) definition.beforeDestroy?.call(instance); instance._isDestroyed = true }
  }
  if (kind === 'panel') {
    const selector = mount('selector', env), editor = mount('editor', env)
    instance.$refs.selectCourseModal = selector.i; instance.$refs.editCourse = editor.i
    selector.listeners.selectFinished = (...args) => instance.selectOK(...args)
    editor.listeners.ok = (...args) => instance.modalFormOk(...args)
    h.selector = selector; h.editor = editor
  }
  return h
}
const calls = (h, method, suffix = '') => h.env.calls.filter(call => call.method === method && (!suffix || call.url.endsWith(suffix)))
async function ready(h, key, rows = [relation(key)]) {
  h.i.open(dept(key)); calls(h, 'GET', '/list').at(-1).resolve(page(rows)); await flush()
}
function select(h, rows) { h.i.onSelectChange(rows.map(row => row.id), rows) }
function rowPrompt(h, record) {
  // A table's scoped slot passes the actual displayed row object, rather than a reconstructed copy.
  record = h.i.dataSource.find(row => row.id === record.id) || record
  if (/@click="confirmDelete\(record\)"/.test(h.source)) {
    h.i.confirmDelete(record)
    return h.env.confirms.at(-1)
  }
  assert.match(h.source, /@confirm="\(\) => handleDelete\(record.id\)"/, 'execute the actual row deletion binding')
  return { onOk: () => h.i.handleDelete(record.id) }
}
async function settleWrite(h, call, result = { success: true, message: '合成成功' }) {
  call.resolve(result); await flush()
  for (const read of h.env.calls.filter(value => value.method === 'GET' && !value.settled)) {
    read.settled = true; read.resolve(page([relation(h.i.currentDeptId?.endsWith('b') ? 'b' : 'a')]))
  }
  await flush()
}

test('switching classes clears relation keys, selected rows, old list and pagination before B responds', async () => {
  const h = mount('panel'); await ready(h, 'a'); select(h, [relation('a')]); h.i.ipagination.current = 4; h.i.ipagination.total = 91
  h.i.open(dept('b'))
  assert.deepEqual(plain(h.i.selectedRowKeys), []); assert.deepEqual(plain(h.i.selectionRows), [])
  assert.deepEqual(plain(h.i.dataSource), []); assert.equal(h.i.ipagination.current, 1); assert.equal(h.i.ipagination.total, 0)
  assert.equal(calls(h, 'GET').at(-1).data.deptId, 'class-b')
  calls(h, 'GET').at(-1).resolve(page([relation('b')])); await flush()
  h.i.batchDel(); assert.equal(calls(h, 'DELETE').length, 0); assert.equal(h.env.confirms.length, 0)
})

for (const transition of ['switch B', 'clear', 'reopen A']) {
  test(`bulk confirmation captured in A cannot dispatch after ${transition}`, async () => {
    const h = mount('panel'); await ready(h, 'a'); select(h, [relation('a')]); h.i.batchDel(); const old = h.env.confirms.at(-1)
    if (transition === 'clear') h.i.clearList(); else await ready(h, transition === 'switch B' ? 'b' : 'a')
    await old.onOk(); assert.equal(calls(h, 'DELETE').length, 0)
  })
  test(`row confirmation rendered in A cannot dispatch after ${transition}`, async () => {
    const h = mount('panel'); await ready(h, 'a'); const old = rowPrompt(h, relation('a'))
    if (transition === 'clear') h.i.clearList(); else await ready(h, transition === 'switch B' ? 'b' : 'a')
    await old.onOk(); assert.equal(calls(h, 'DELETE').length, 0)
  })
}
for (const replacement of [[], [relation('a', '-other')]]) {
  test(`changing the relation selection invalidates an open bulk confirmation (${replacement.length})`, async () => {
    const h = mount('panel'); await ready(h, 'a', [relation('a'), relation('a', '-other')]); select(h, [relation('a')]); h.i.batchDel()
    select(h, replacement); await h.env.confirms.at(-1).onOk(); assert.equal(calls(h, 'DELETE').length, 0)
  })
}
test('B bulk deletion dispatches one frozen B ID list despite repeated clicks and confirmation callbacks', async () => {
  const h = mount('panel'), rows = [relation('b'), relation('b', '-second')]; await ready(h, 'b', rows); select(h, rows)
  h.i.batchDel(); h.i.batchDel(); assert.equal(h.env.confirms.length, 1)
  const prompt = h.env.confirms[0]; prompt.onOk(); prompt.onOk(); assert.equal(calls(h, 'DELETE').length, 1)
  assert.deepEqual(calls(h, 'DELETE')[0].data.ids.split(',').filter(Boolean), rows.map(row => row.id))
  await settleWrite(h, calls(h, 'DELETE')[0]); assert.deepEqual(plain(h.i.selectedRowKeys), [])
  assert.equal(calls(h, 'GET').at(-1).data.deptId, 'class-b')
})
test('control: one normal B bulk confirmation deletes only B and refreshes B', async () => {
  const h = mount('panel'); await ready(h, 'b'); select(h, [relation('b')]); h.i.batchDel(); h.env.confirms.at(-1).onOk()
  assert.equal(calls(h, 'DELETE').length, 1); assert.deepEqual(calls(h, 'DELETE')[0].data.ids.split(',').filter(Boolean), ['relation-b'])
  await settleWrite(h, calls(h, 'DELETE')[0]); assert.equal(calls(h, 'GET').at(-1).data.deptId, 'class-b')
})
test('an old cancelled confirmation cannot unlock or submit a newer B prompt', async () => {
  const h = mount('panel'); await ready(h, 'a'); select(h, [relation('a')]); h.i.batchDel(); const old = h.env.confirms.at(-1)
  await ready(h, 'b'); select(h, [relation('b')]); h.i.batchDel(); const current = h.env.confirms.at(-1)
  old.onCancel?.(); await old.onOk(); h.i.batchDel()
  assert.equal(h.env.confirms.length, 2); assert.equal(calls(h, 'DELETE').length, 0)
  current.onCancel?.(); h.i.batchDel(); assert.equal(h.env.confirms.length, 3)
})
test('normal B row deletion preserves the original relation ID and suppresses repeated dispatch', async () => {
  const h = mount('panel'); await ready(h, 'b'); const prompt = rowPrompt(h, relation('b'))
  prompt.onOk(); prompt.onOk(); assert.equal(calls(h, 'DELETE').length, 1)
  assert.deepEqual(calls(h, 'DELETE')[0].data, { id: 'relation-b' }); await settleWrite(h, calls(h, 'DELETE')[0])
})
test('control: one normal B row confirmation keeps the actual DELETE contract', async () => {
  const h = mount('panel'); await ready(h, 'b'); rowPrompt(h, relation('b')).onOk()
  assert.equal(calls(h, 'DELETE').length, 1); assert.equal(calls(h, 'DELETE')[0].url, '/teaching/teachingCourseDept/delete')
  assert.deepEqual(calls(h, 'DELETE')[0].data, { id: 'relation-b' }); await settleWrite(h, calls(h, 'DELETE')[0])
})
test('late A relation-list success cannot replace B list, count or loading state', async () => {
  const h = mount('panel'); h.i.open(dept('a')); const a = calls(h, 'GET').at(-1); h.i.open(dept('b')); const b = calls(h, 'GET').at(-1)
  b.resolve(page([relation('b')], 12)); await flush(); a.resolve(page([relation('a')], 99)); await flush()
  assert.deepEqual(plain(h.i.dataSource), [relation('b')]); assert.equal(h.i.ipagination.total, 12); assert.equal(h.i.loading, false)
})
test('newer list query within one class wins when responses arrive in reverse order', async () => {
  const h = mount('panel'); await ready(h, 'b'); h.i.loadData(); const older = calls(h, 'GET').at(-1); h.i.loadData(); const newer = calls(h, 'GET').at(-1)
  newer.resolve(page([relation('b', '-new')], 2)); await flush(); older.resolve(page([relation('b', '-old')], 9)); await flush()
  assert.equal(h.i.dataSource[0].id, 'relation-b-new'); assert.equal(h.i.ipagination.total, 2)
})
test('malformed relation records containing null never enter the table or deletion path', async () => {
  const h = mount('panel'); h.i.open(dept('b')); calls(h, 'GET').at(-1).resolve(page([null])); await flush()
  assert.deepEqual(plain(h.i.dataSource), []); assert.ok(h.i.listError); assert.equal(h.i.loading, false)
  h.i.batchDel(); assert.equal(h.env.confirms.length, 0); assert.equal(calls(h, 'DELETE').length, 0)
  h.i.loadData(); calls(h, 'GET').at(-1).resolve(page([relation('b')])); await flush(); assert.equal(h.i.dataSource[0].id, 'relation-b')
})
for (const failure of ['network', 'business']) {
  test(`stale A list ${failure} does not publish a B error or unlock B's pending read`, async () => {
    const h = mount('panel'); h.i.open(dept('a')); const a = calls(h, 'GET').at(-1); h.i.open(dept('b')); const b = calls(h, 'GET').at(-1)
    const noticeCount = h.env.notices.length
    if (failure === 'network') a.reject(new Error('synthetic offline')); else a.resolve({ success: false, message: 'SQL secret' })
    await flush(); assert.equal(h.i.loading, true); assert.equal(h.env.notices.length, noticeCount); assert.equal(Boolean(h.i.listError), false)
    b.resolve(page([relation('b')])); await flush(); assert.equal(h.i.dataSource[0].id, 'relation-b')
  })
  test(`current B list ${failure} exposes recoverable failure and can retry without losing its scope`, async () => {
    const h = mount('panel'); await ready(h, 'b'); h.i.loadData(); const read = calls(h, 'GET').at(-1)
    if (failure === 'network') read.reject(new Error('synthetic offline')); else read.resolve({ success: false, message: 'SQL secret' })
    await flush(); assert.equal(h.i.loading, false); assert.ok(h.i.listError || h.env.notices.some(value => ['warning', 'error'].includes(value.type)))
    assert.doesNotMatch(String(h.i.listError || '') + h.env.notices.map(value => value.text).join(''), /SQL secret/)
    h.i.loadData(); assert.equal(calls(h, 'GET').at(-1).data.deptId, 'class-b'); calls(h, 'GET').at(-1).resolve(page([relation('b')])); await flush()
    assert.equal(h.i.dataSource[0].id, 'relation-b')
  })
}
for (const disposal of ['clear', 'destroy']) {
  test(`late relation read after ${disposal} cannot repopulate an inactive panel`, async () => {
    const h = mount('panel'); h.i.open(dept('a')); const read = calls(h, 'GET').at(-1)
    if (disposal === 'clear') h.i.clearList(); else h.destroy()
    const rows = plain(h.i.dataSource), noticeCount = h.env.notices.length; read.resolve(page([relation('a')])); await flush()
    assert.deepEqual(plain(h.i.dataSource), rows); assert.equal(h.env.notices.length, noticeCount)
  })
}
for (const result of [{ success: true, message: '合成成功' }, { success: false, message: 'SQL secret' }]) {
  test(`already dispatched A bulk response (${result.success}) cannot refresh, clear selection or notify in B`, async () => {
    const h = mount('panel'); await ready(h, 'a'); select(h, [relation('a')]); h.i.batchDel(); h.env.confirms.at(-1).onOk(); const write = calls(h, 'DELETE').at(-1)
    await ready(h, 'b'); select(h, [relation('b')]); const reads = calls(h, 'GET').length, noticeCount = h.env.notices.length
    write.resolve(result); await flush(); assert.equal(calls(h, 'GET').length, reads); assert.equal(h.env.notices.length, noticeCount)
    assert.deepEqual(plain(h.i.selectedRowKeys), ['relation-b']); assert.equal(h.i.dataSource[0].id, 'relation-b')
  })
}
test('late A write completion cannot release B write lock or stack a second B write', async () => {
  const h = mount('panel'); await ready(h, 'a'); const aPrompt = rowPrompt(h, relation('a')); aPrompt.onOk(); const a = calls(h, 'DELETE').at(-1)
  await ready(h, 'b'); const bPrompt = rowPrompt(h, relation('b')); bPrompt.onOk(); const b = calls(h, 'DELETE').at(-1)
  assert.equal(calls(h, 'DELETE').length, 2); a.resolve({ success: true }); await flush(); bPrompt.onOk()
  assert.equal(calls(h, 'DELETE').length, 2); await settleWrite(h, b)
})

test('showing the course selector for B clears A selection, rows, draft query and pagination', async () => {
  const h = mount('selector'); h.i.show('class-a', 1); calls(h, 'GET').at(-1).resolve(page([course('a')], 31)); await flush()
  select(h, [course('a')]); h.i.dataSource2 = [course('a')]; h.i.queryParam.courseName = 'A only'; h.i.ipagination.current = 4
  h.i.show('class-b', 2)
  assert.deepEqual(plain(h.i.selectedRowKeys), []); assert.deepEqual(plain(h.i.selectionRows || h.i.selectedRows), [])
  assert.deepEqual(plain(h.i.dataSource1), []); assert.deepEqual(plain(h.i.dataSource2), []); assert.equal(h.i.ipagination.current, 1)
  assert.equal(calls(h, 'GET').at(-1).data.departId, 'class-b'); assert.equal(calls(h, 'GET').at(-1).data.courseName, undefined)
  calls(h, 'GET').at(-1).resolve(page([course('b')])); await flush()
})
test('course selector late A result cannot replace the visible B choices', async () => {
  const h = mount('selector'); h.i.show('class-a', 1); const a = calls(h, 'GET').at(-1); h.i.show('class-b', 2); const b = calls(h, 'GET').at(-1)
  b.resolve(page([course('b')], 3)); await flush(); a.resolve(page([course('a')], 99)); await flush()
  assert.deepEqual(plain(h.i.dataSource1), [course('b')]); assert.equal(h.i.ipagination.total, 3)
})
test('malformed course records containing null cannot become selectable course IDs', async () => {
  const h = mount('selector'); h.i.show('class-b', 2); calls(h, 'GET').at(-1).resolve(page([null])); await flush()
  assert.deepEqual(plain(h.i.dataSource1), []); assert.ok(h.i.loadError); assert.equal(h.i.loading, false)
  h.i.handleOk(); assert.equal(h.events.filter(event => event.name === 'selectFinished').length, 0)
})
for (const failure of ['network', 'business']) {
  test(`selector stale A ${failure} cannot unlock B or expose an error in B`, async () => {
    const h = mount('selector'); h.i.show('class-a', 1); const a = calls(h, 'GET').at(-1); h.i.show('class-b', 2); const b = calls(h, 'GET').at(-1)
    const notices = h.env.notices.length
    if (failure === 'network') a.reject(new Error('synthetic offline')); else a.resolve({ success: false, message: 'SQL secret' })
    await flush(); assert.equal(h.i.loading, true); assert.equal(Boolean(h.i.loadError), false); assert.equal(h.env.notices.length, notices)
    b.resolve(page([course('b')])); await flush(); assert.equal(h.i.dataSource1[0].id, 'course-b')
  })
  test(`selector current B ${failure} blocks emitting until a manual scoped retry succeeds`, async () => {
    const h = mount('selector'); h.i.show('class-b', 2); const read = calls(h, 'GET').at(-1)
    if (failure === 'network') read.reject(new Error('synthetic offline')); else read.resolve({ success: false, message: 'SQL secret' })
    await flush(); assert.equal(h.i.loading, false); assert.ok(h.i.loadError); assert.doesNotMatch(h.i.loadError, /SQL secret/)
    h.i.handleOk(); assert.equal(h.events.filter(event => event.name === 'selectFinished').length, 0)
    h.i.loadData(); assert.equal(calls(h, 'GET').at(-1).data.departId, 'class-b'); calls(h, 'GET').at(-1).resolve(page([course('b')])); await flush()
    select(h, [course('b')]); h.i.handleOk(); assert.equal(h.events.filter(event => event.name === 'selectFinished').length, 1)
  })
}
test('closed course selector ignores a late read instead of restoring old choices', async () => {
  const h = mount('selector'); h.i.show('class-a', 1); const read = calls(h, 'GET').at(-1); h.i.handleCancel(); const before = plain(h.i.dataSource1)
  read.resolve(page([course('a')])); await flush(); assert.equal(h.i.visible, false); assert.deepEqual(plain(h.i.dataSource1), before)
})
test('B selector emits an immutable original department and course-ID snapshot once', async () => {
  const h = mount('selector'); h.i.show('class-b', 7); calls(h, 'GET').at(-1).resolve(page([course('b')])); await flush(); select(h, [course('b')])
  h.i.handleOk(); h.i.handleOk(); const emissions = h.events.filter(event => event.name === 'selectFinished')
  assert.equal(emissions.length, 1); const payload = emissions[0].args[0]
  assert.equal(payload.deptId, 'class-b'); assert.equal(payload.contextVersion, 7); assert.deepEqual(plain(payload.courseIdList), ['course-b'])
  h.i.show('class-a', 8); assert.deepEqual(plain(payload.courseIdList), ['course-b']); calls(h, 'GET').at(-1).resolve(page([course('a')])); await flush()
})
for (const transition of ['switch B', 'clear', 'reopen A']) {
  test(`a delayed selector emit from A cannot add after ${transition}`, async () => {
    const h = mount('panel'); await ready(h, 'a'); h.i.handleAddCourse(); calls(h, 'GET').at(-1).resolve(page([course('a')])); await flush()
    select(h.selector, [course('a')]); delete h.selector.listeners.selectFinished; h.selector.i.handleOk()
    const old = h.selector.events.find(event => event.name === 'selectFinished')
    assert.ok(old, 'capture the actual selector emission before changing context')
    if (transition === 'clear') h.i.clearList(); else await ready(h, transition === 'switch B' ? 'b' : 'a')
    h.i.selectOK(...old.args); assert.equal(calls(h, 'POST').length, 0)
  })
}
test('actual B parent-selector chain adds only B chosen IDs and prevents repeated writes', async () => {
  const h = mount('panel'); await ready(h, 'b'); h.i.handleAddCourse(); const choiceRead = calls(h, 'GET').at(-1)
  assert.equal(choiceRead.data.departId, 'class-b'); choiceRead.resolve(page([course('b')])); await flush(); select(h.selector, [course('b')])
  h.selector.i.handleOk(); const emission = h.selector.events.find(event => event.name === 'selectFinished')
  h.i.selectOK(...emission.args); assert.equal(calls(h, 'POST').length, 1)
  assert.deepEqual(calls(h, 'POST')[0].data, { deptId: 'class-b', courseIdList: ['course-b'] }); await settleWrite(h, calls(h, 'POST')[0])
})
test('control: one ordinary B course selection preserves the addOrUpdate endpoint and body', async () => {
  const h = mount('panel'); await ready(h, 'b'); h.i.handleAddCourse(); calls(h, 'GET').at(-1).resolve(page([course('b')])); await flush()
  select(h.selector, [course('b')]); h.selector.i.handleOk(); assert.equal(calls(h, 'POST').length, 1)
  assert.equal(calls(h, 'POST')[0].url, '/teaching/teachingCourseDept/addOrUpdate')
  assert.deepEqual(calls(h, 'POST')[0].data, { deptId: 'class-b', courseIdList: ['course-b'] }); await settleWrite(h, calls(h, 'POST')[0])
})
test('unscoped legacy selector arrays cannot silently write old courses to the current class', async () => {
  const h = mount('panel'); await ready(h, 'b'); h.i.selectOK(['course-a']); assert.equal(calls(h, 'POST').length, 0)
})
for (const result of [{ success: true }, { success: false, message: 'SQL secret' }]) {
  test(`already dispatched A add response (${result.success}) leaves B list, selection and notices alone`, async () => {
    const h = mount('panel'); await ready(h, 'a'); h.i.handleAddCourse(); calls(h, 'GET').at(-1).resolve(page([course('a')])); await flush()
    select(h.selector, [course('a')]); h.selector.i.handleOk(); const write = calls(h, 'POST').at(-1); assert.ok(write)
    await ready(h, 'b'); select(h, [relation('b')]); const reads = calls(h, 'GET').length, noticeCount = h.env.notices.length
    write.resolve(result); await flush(); assert.equal(calls(h, 'GET').length, reads); assert.equal(h.env.notices.length, noticeCount)
    assert.equal(h.i.dataSource[0].id, 'relation-b'); assert.deepEqual(plain(h.i.selectedRowKeys), ['relation-b'])
  })
}
test('late A add completion cannot release the current B add lock', async () => {
  const h = mount('panel'); await ready(h, 'a'); h.i.handleAddCourse(); calls(h, 'GET').at(-1).resolve(page([course('a')])); await flush()
  select(h.selector, [course('a')]); h.selector.i.handleOk(); const a = calls(h, 'POST').at(-1)
  await ready(h, 'b'); h.i.handleAddCourse(); calls(h, 'GET').at(-1).resolve(page([course('b')])); await flush()
  select(h.selector, [course('b')]); h.selector.i.handleOk(); const b = calls(h, 'POST').at(-1), emission = h.selector.events.filter(event => event.name === 'selectFinished').at(-1)
  assert.equal(calls(h, 'POST').length, 2); a.resolve({ success: true }); await flush(); h.i.selectOK(...emission.args)
  assert.equal(calls(h, 'POST').length, 2); await settleWrite(h, b)
})

test('normal B opening-time editor keeps relation identity and locks validation and duplicate writes', async () => {
  const h = mount('panel'); await ready(h, 'b'); h.i.handleEditCourse(h.i.dataSource[0]); h.editor.ticks()
  h.editor.values.openTime = '2026-10-04 10:30:00'; h.editor.i.handleOk(); h.editor.i.handleOk()
  assert.equal(h.editor.validations.length, 1); h.editor.validate(); h.editor.i.handleOk(); assert.equal(calls(h, 'PUT').length, 1)
  assert.deepEqual(calls(h, 'PUT')[0].data, { ...relation('b'), openTime: '2026-10-04 10:30:00' })
  await settleWrite(h, calls(h, 'PUT')[0]); assert.equal(h.editor.i.visible, false); assert.equal(calls(h, 'GET').at(-1).data.deptId, 'class-b')
})
test('control: one B opening-time update preserves the existing edit endpoint and refresh callback', async () => {
  const h = mount('panel'); await ready(h, 'b'); h.i.handleEditCourse(h.i.dataSource[0]); h.editor.ticks()
  h.editor.values.openTime = '2026-10-04 10:30:00'; h.editor.i.handleOk(); h.editor.validate()
  assert.equal(calls(h, 'PUT').length, 1); assert.equal(calls(h, 'PUT')[0].url, '/teaching/teachingCourseDept/edit')
  assert.equal(calls(h, 'PUT')[0].data.id, 'relation-b'); assert.equal(calls(h, 'PUT')[0].data.deptId, 'class-b')
  await settleWrite(h, calls(h, 'PUT')[0]); assert.equal(h.editor.i.visible, false); assert.equal(calls(h, 'GET').at(-1).data.deptId, 'class-b')
})
test('switching the parent closes both child dialogs and invalidates editor validation before dispatch', async () => {
  const h = mount('panel'); await ready(h, 'a'); h.i.handleAddCourse(); h.i.handleEditCourse(h.i.dataSource[0]); h.editor.ticks(); h.editor.i.handleOk()
  await ready(h, 'b'); assert.equal(h.selector.i.visible, false); assert.equal(h.editor.i.visible, false)
  h.editor.validate(null, { deptId: 'class-a', courseId: 'course-a', openTime: '2026-10-04 10:30:00' }); assert.equal(calls(h, 'PUT').length, 0)
})
test('late editor nextTick cannot fill a newer record or a closed dialog', () => {
  const h = mount('editor'), a = relation('a'), b = { ...relation('b'), openTime: '2026-10-04 12:00:00' }
  h.i.edit(a); h.i.edit(b); h.env.ticks.reverse(); h.ticks()
  assert.equal(h.values.openTime, b.openTime); assert.equal(h.i.model.deptId, 'class-b'); assert.equal(h.i.model.courseId, 'course-b')
  h.i.edit(a); h.i.close(); h.ticks(); assert.equal(h.values.openTime, undefined)
})
test('late A form validation cannot dispatch a write after editor closes and opens B', () => {
  const h = mount('editor'); h.i.edit(relation('a')); h.ticks(); h.i.handleOk(); h.i.close(); h.i.edit(relation('b')); h.ticks()
  h.validate(null, { deptId: 'class-a', courseId: 'course-a', openTime: '2026-10-04 10:30:00' })
  assert.equal(calls(h, 'PUT').length, 0); assert.equal(h.i.visible, true); assert.equal(h.i.model.id, 'relation-b')
})
test('late A opening-time completion cannot release the currently validating B dialog', async () => {
  const h = mount('editor'); h.i.edit(relation('a')); h.ticks(); h.i.handleOk(); h.validate(); const a = calls(h, 'PUT').at(-1)
  h.i.close(); h.i.edit(relation('b')); h.ticks(); h.i.handleOk(); const count = h.validations.length
  a.resolve({ success: true }); await flush(); assert.equal(h.i.visible, true); assert.equal(h.i.confirmLoading, true)
  h.i.handleOk(); assert.equal(h.validations.length, count); assert.equal(calls(h, 'PUT').length, 1)
  h.validate(); assert.equal(calls(h, 'PUT').length, 2); calls(h, 'PUT').at(-1).resolve({ success: true }); await flush(); assert.equal(h.i.visible, false)
})
test('opening-time validation error unlocks the same dialog without sending a request', () => {
  const h = mount('editor'); h.i.edit(relation('b')); h.ticks(); h.i.handleOk(); h.validate({ openTime: 'invalid' })
  assert.equal(calls(h, 'PUT').length, 0); assert.equal(h.i.confirmLoading, false); assert.equal(h.i.visible, true)
  h.i.handleOk(); assert.equal(h.validations.length, 1)
})
for (const result of [{ success: true, message: '合成成功' }, { success: false, message: 'SQL secret' }]) {
  test(`late A opening-time response (${result.success}) cannot close or notify in the reopened B editor`, async () => {
    const h = mount('editor'); h.i.edit(relation('a')); h.ticks(); h.i.handleOk(); h.validate(); const write = calls(h, 'PUT').at(-1)
    h.i.close(); h.i.edit(relation('b')); h.ticks(); const notices = h.env.notices.length, events = h.events.length
    write.resolve(result); await flush(); assert.equal(h.i.visible, true); assert.equal(h.i.model.id, 'relation-b')
    assert.equal(h.env.notices.length, notices); assert.equal(h.events.length, events); assert.equal(h.i.confirmLoading, false)
  })
}
test('ordinary standalone edit(record) remains compatible and writes the same relation', async () => {
  const h = mount('editor'); h.i.edit(relation('b')); h.ticks(); h.values.openTime = '2026-10-05 11:00:00'; h.i.handleOk(); h.validate()
  const write = calls(h, 'PUT').at(-1); assert.ok(write); assert.equal(write.data.id, 'relation-b'); assert.equal(write.data.deptId, 'class-b'); assert.equal(write.data.courseId, 'course-b')
  write.resolve({ success: true, message: '合成成功' }); await flush(); assert.equal(h.i.visible, false); assert.equal(h.events.filter(event => event.name === 'ok').length, 1)
  assert.deepEqual(plain(h.events.find(event => event.name === 'ok').args), [])
})
test('ordinary standalone new-record edit(record) remains compatible with the existing POST endpoint', async () => {
  const h = mount('editor'); h.i.edit({ deptId: 'class-b', courseId: 'course-b' }); h.ticks(); h.values.openTime = '2026-10-05 11:00:00'
  h.i.handleOk(); h.validate(); const write = calls(h, 'POST').at(-1); assert.ok(write); assert.equal(write.url, '/teaching/teachingCourseDept/add')
  assert.equal(write.data.deptId, 'class-b'); assert.equal(write.data.courseId, 'course-b'); write.resolve({ success: true }); await flush(); assert.equal(h.i.visible, false)
  assert.deepEqual(plain(h.events.find(event => event.name === 'ok').args), [])
})
for (const entry of ['standalone', 'parent context']) {
  test(`${entry}: validation values cannot overwrite the original relation, class or course identity`, async () => {
    const parent = entry === 'parent context' ? mount('panel') : null
    if (parent) { await ready(parent, 'b'); parent.i.handleEditCourse(parent.i.dataSource[0]) }
    const h = parent ? parent.editor : mount('editor')
    if (!parent) h.i.edit(relation('b'))
    h.ticks(); h.i.handleOk(); h.validate(null, { id: 'relation-a', deptId: 'class-a', courseId: 'course-a', openTime: '2026-10-05 11:00:00' })
    const write = calls(h, 'PUT').at(-1); assert.ok(write)
    assert.equal(write.data.id, 'relation-b'); assert.equal(write.data.deptId, 'class-b'); assert.equal(write.data.courseId, 'course-b')
    assert.equal(write.data.openTime, '2026-10-05 11:00:00'); await settleWrite(parent || h, write)
  })
}
test('the actual editor and popup callback fill only registered openTime fields', () => {
  const h = mount('editor'); h.i.edit(relation('b')); h.ticks()
  assert.deepEqual(plain(h.values), { openTime: relation('b').openTime })
  h.i.popupCallback({ id: 'relation-a', deptId: 'class-a', courseId: 'course-a', openTime: '2026-10-05 11:00:00' })
  assert.deepEqual(plain(h.values), { openTime: '2026-10-05 11:00:00' })
  assert.equal(h.i.model.id, 'relation-b'); assert.equal(h.i.model.deptId, 'class-b'); assert.equal(h.i.model.courseId, 'course-b')
})
test('opening-time business failure keeps values available for manual retry', async () => {
  const h = mount('editor'); h.i.edit(relation('b')); h.ticks(); h.values.openTime = '2026-10-05 11:00:00'; h.i.handleOk(); h.validate()
  calls(h, 'PUT').at(-1).resolve({ success: false, message: 'SQL secret' }); await flush(); assert.equal(h.i.visible, true); assert.equal(h.i.confirmLoading, false)
  assert.equal(h.values.openTime, '2026-10-05 11:00:00'); assert.equal(h.events.filter(event => event.name === 'ok').length, 0)
  h.i.handleOk(); h.validate(); assert.equal(calls(h, 'PUT').length, 2); calls(h, 'PUT').at(-1).resolve({ success: true }); await flush(); assert.equal(h.i.visible, false)
})
test('destroyed opening-time editor ignores late validation and response', async () => {
  const h = mount('editor'); h.i.edit(relation('a')); h.ticks(); h.i.handleOk(); h.destroy(); h.validate(); assert.equal(calls(h, 'PUT').length, 0)
  const other = mount('editor'); other.i.edit(relation('a')); other.ticks(); other.i.handleOk(); other.validate(); other.destroy()
  const notices = other.env.notices.length, events = other.events.length; calls(other, 'PUT').at(-1).resolve({ success: true }); await flush()
  assert.equal(other.env.notices.length, notices); assert.equal(other.events.length, events)
})
test('delayed parent refresh event from edited A cannot refresh current B', async () => {
  const h = mount('panel'); await ready(h, 'a'); h.i.handleEditCourse(h.i.dataSource[0]); h.editor.ticks(); delete h.editor.listeners.ok
  h.editor.i.handleOk(); h.editor.validate(); calls(h, 'PUT').at(-1).resolve({ success: true }); await flush()
  const old = h.editor.events.find(event => event.name === 'ok'); assert.ok(old)
  await ready(h, 'b'); const reads = calls(h, 'GET').length; h.i.modalFormOk(...old.args); assert.equal(calls(h, 'GET').length, reads)
})
