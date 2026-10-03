// Execute actual SFC/Mixin methods against the owned HTTP server. No browser
// rendering or browser login is simulated. The only credential arrives on stdin.
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const crypto = require('node:crypto')
const { execFileSync } = require('node:child_process')
const babel = require('@babel/core')
const pick = require('lodash.pick')
const input = JSON.parse(fs.readFileSync(0, 'utf8'))
const source = path.resolve(process.argv[2])
if (input.origin !== 'http://127.0.0.1:18175') throw Error('Only the owned class-context server is supported')
const cases = [], observations = [], sourceHashes = {}
const pending = new Set(), requests = []
function check(name, passed, details = {}) { cases.push({ case: name, passed: !!passed, ...details }) }
function read(file) {
  const text = input.sourceRef ? execFileSync('git', ['-C', source, 'show', input.sourceRef + ':' + file], { encoding: 'utf8', maxBuffer: 1024 * 1024 }) : fs.readFileSync(path.join(source, file), 'utf8')
  sourceHashes[file] = crypto.createHash('sha256').update(text).digest('hex')
  return text
}
function track(promise) {
  pending.add(promise)
  promise.then(() => pending.delete(promise), () => pending.delete(promise))
  return promise
}
async function settle() {
  // Old component methods do not return their HTTP promises. Drain real network
  // requests and the callbacks they enqueue rather than accepting an early return.
  for (let i = 0; i < 100; i++) {
    await Promise.allSettled([...pending])
    await new Promise(resolve => setImmediate(resolve))
    if (!pending.size) return
  }
  throw Error('Component request chain did not settle')
}
function action(route, params, method) {
  if (!/^\/teaching\/teachingCourse(?:Dept)?\/(list|queryById|deleteBatch|delete|addOrUpdate|edit)$/.test(route)) throw Error('Non-probe endpoint rejected')
  const url = new URL('/api' + route, input.origin)
  const options = { method, headers: { 'X-Access-Token': input.token }, signal: AbortSignal.timeout(15000) }
  if (method === 'GET' || method === 'DELETE') {
    for (const [key, value] of Object.entries(params || {})) if (value != null) url.searchParams.set(key, value)
  } else {
    options.headers['Content-Type'] = 'application/json'
    options.body = JSON.stringify(params)
  }
  // Retain only operation names; no token, account, raw payload or department ID.
  requests.push({ method, route })
  return track(fetch(url, options).then(async response => {
    if (!response.ok) throw Error('Owned HTTP request failed with status ' + response.status)
    return response.json()
  }))
}
const getAction = (route, params) => action(route, params, 'GET')
const postAction = (route, params) => action(route, params, 'POST')
const deleteAction = (route, params) => action(route, params, 'DELETE')
const httpAction = (route, params, method) => action(route, params, method.toUpperCase())
const utility = read('web/src/utils/util.js')
const start = utility.indexOf('export function filterObj(')
const end = utility.indexOf('\n}', start) + 2
if (start < 0 || end < start) throw Error('Real filterObj function not found')
const utilContext = { module: { exports: {} } }
vm.runInNewContext(utility.slice(start, end).replace('export function filterObj', 'module.exports = function filterObj'), utilContext)
const filterObj = utilContext.module.exports
const quietConsole = { log() {}, warn() {}, error() {} }
function load(file, extras = {}) {
  let code = read(file)
  if (file.endsWith('.vue')) code = code.split('<script>')[1].split('</script>')[0]
  code = code.replace(/^\s*import .*$/mg, '')
  code = code.replace('export const JeecgListMixin =', 'module.exports =').replace('export default', 'module.exports =')
  if (file.endsWith('JeecgListMixin.js')) code = babel.transformSync(code, { cwd: path.join(source, 'web'), babelrc: false, configFile: false,
    presets: [[require.resolve('@vue/babel-preset-app'), { useBuiltIns: false }]] }).code
  const context = { module: { exports: {} }, getAction, postAction, deleteAction, httpAction, filterObj, pick,
    Vue: { ls: { get: () => input.token } }, ACCESS_TOKEN: 'owned-cli-token', console: quietConsole,
    downFile() {}, getFileAccessHttpUrl() {}, validateDuplicateValue() {}, JDate: {}, ...extras }
  vm.runInNewContext(code, context, { filename: file })
  return context.module.exports
}
const mixin = load('web/src/mixins/JeecgListMixin.js')
const selectComponent = load('web/src/views/teaching/modules/SelectCourseModal.vue')
const editComponent = load('web/src/views/teaching/modules/TeachingCourseDeptModal.vue')
const departmentComponent = load('web/src/views/system/modules/DeptCourseInfo.vue', { JeecgListMixin: mixin, SelectCourseModal: selectComponent, TeachingCourseDeptModal: editComponent })
function instance(component) {
  const ctx = { $refs: {}, confirmations: [], emitted: [], messages: [], disableMixinCreated: true,
    $message: Object.fromEntries(['error', 'warning', 'success'].map(type => [type, () => ctx.messages.push(type)])),
    $confirm: options => ctx.confirmations.push(options),
    $nextTick: callback => track(Promise.resolve().then(callback)),
    $emit: (type, payload) => ctx.emitted.push({ type, payload }),
    $form: { createForm: () => ({ values: {}, resetFields() { this.values = {} },
      setFieldsValue(value) { Object.assign(this.values, value) }, validateFields(callback) { callback(null, this.values) } }) } }
  const definitions = [...(component.mixins || []), component]
  for (const definition of definitions) if (definition.data) Object.assign(ctx, definition.data.call(ctx))
  for (const definition of definitions) for (const [name, method] of Object.entries(definition.methods || {})) ctx[name] = method.bind(ctx)
  for (const definition of definitions) for (const [name, getter] of Object.entries(definition.computed || {})) Object.defineProperty(ctx, name, { configurable: true, get: () => getter.call(ctx) })
  return ctx
}
function workspace() {
  const parent = instance(departmentComponent), modal = instance(selectComponent), edit = instance(editComponent)
  parent.$refs = { selectCourseModal: modal, editCourse: edit }
  modal.$emit = (type, payload) => { modal.emitted.push({ type, payload }); if (type === 'selectFinished') parent.selectOK(payload) }
  edit.$emit = (type, payload) => { edit.emitted.push({ type, payload }); if (type === 'ok') parent.modalFormOk(payload) }
  return { parent, modal, edit }
}
const A = { id: input.classes.A, orgCategory: '3', departName: 'Synthetic class A' }
const B = { id: input.classes.B, orgCategory: '3', departName: 'Synthetic class B' }
function writesSince(index, method, route) { return requests.slice(index).filter(r => r.method === method && r.route === route).length }
async function relation(id) { const body = await getAction('/teaching/teachingCourseDept/queryById', { id }); return body.success ? body.result : null }
async function open(parent, department) { parent.open(department); await settle() }
function selectedRelation(parent, id) {
  const row = parent.dataSource.find(row => row.id === id)
  if (!row) throw Error('Owned relationship missing from actual department list')
  parent.onSelectChange([id], [row])
  return row
}
async function selectCourse(parent, modal, id) {
  parent.handleAddCourse(); await settle()
  const row = modal.dataSource1.find(row => row.id === id)
  if (!row) throw Error('Owned course missing from actual selection list')
  modal.onSelectChange([id], [row])
}
async function main() {
  // Confirmation created in A, then completed while B is current.
  {
    const { parent } = workspace()
    await open(parent, A); selectedRelation(parent, input.relations.bulkPending)
    parent.batchDel()
    const confirmation = parent.confirmations.pop()
    if (!confirmation) throw Error('Expected an actual component confirmation')
    await open(parent, B)
    const before = requests.length
    confirmation.onOk(); await settle()
    const count = writesSince(before, 'DELETE', '/teaching/teachingCourseDept/deleteBatch')
    check('A bulk confirmation after switch to B sends no delete request', count === 0, { write_requests: count })
    check('A relationship survives stale bulk confirmation', !!await relation(input.relations.bulkPending))
  }
  // A selection must not remain actionable when the batch menu is opened in B.
  {
    const { parent } = workspace()
    await open(parent, A); selectedRelation(parent, input.relations.bulkAfterSwitch)
    await open(parent, B)
    const before = requests.length
    parent.batchDel()
    const confirmation = parent.confirmations.pop()
    if (confirmation) confirmation.onOk()
    await settle()
    const count = writesSince(before, 'DELETE', '/teaching/teachingCourseDept/deleteBatch')
    check('A selection cannot produce a B batch delete request', count === 0, { write_requests: count })
    check('A relationship survives batch menu opened after switch', !!await relation(input.relations.bulkAfterSwitch))
  }
  // A visible course modal must not submit the A selection into the new class B.
  {
    const { parent, modal } = workspace()
    await open(parent, A); await selectCourse(parent, modal, input.courses.crossSwitch)
    await open(parent, B)
    const before = requests.length
    modal.handleOk(); await settle()
    const count = writesSince(before, 'POST', '/teaching/teachingCourseDept/addOrUpdate')
    check('A modal selection after switch to B sends no add request', count === 0, { write_requests: count })
    parent.loadData(); await settle()
    check('B has no course inherited from the stale A modal', !parent.dataSource.some(row => row.courseId === input.courses.crossSwitch))
  }
  // Closing and opening another session must require a new selection.
  {
    const { parent, modal } = workspace()
    await open(parent, A); await selectCourse(parent, modal, input.courses.crossReopen)
    modal.handleCancel(); await open(parent, B)
    parent.handleAddCourse(); await settle()
    const before = requests.length
    modal.handleOk(); await settle()
    const count = writesSince(before, 'POST', '/teaching/teachingCourseDept/addOrUpdate')
    check('closed A modal reopened in B cannot reuse its old selection', count === 0, { write_requests: count })
    parent.loadData(); await settle()
    check('B has no course inherited from the closed modal session', !parent.dataSource.some(row => row.courseId === input.courses.crossReopen))
  }
  // Legitimate B operations continue using the same actual component methods.
  {
    const { parent, modal, edit } = workspace()
    await open(parent, B)
    check('B real list contains its own relationship and no A relationships', parent.dataSource.some(row => row.id === input.relations.baseB) && !parent.dataSource.some(row => [input.relations.bulkPending, input.relations.bulkAfterSwitch].includes(row.id)))
    await selectCourse(parent, modal, input.courses.normal)
    modal.handleOk(); await settle()
    const added = parent.dataSource.find(row => row.courseId === input.courses.normal)
    check('B fresh modal selection adds the selected course to B', !!added && added.deptId === input.classes.B)
    if (!added) throw Error('Normal B addition failed')
    const existing = parent.dataSource.find(row => row.id === input.relations.baseB)
    parent.handleEditCourse(existing); await settle()
    edit.form.setFieldsValue({ openTime: input.openTime })
    edit.handleOk(); await settle()
    const saved = await relation(input.relations.baseB)
    check('B openTime edit persists through the real shared modal and HTTP', !!saved && saved.openTime === input.openTime)
    const latest = parent.dataSource.find(row => row.id === added.id)
    parent.onSelectChange([added.id], [latest]); parent.batchDel()
    const confirmation = parent.confirmations.pop()
    if (!confirmation) throw Error('Normal B delete did not confirm')
    confirmation.onOk(); await settle()
    check('B current selection deletes only the newly added relationship', !await relation(added.id) && !!await relation(input.relations.baseB))
  }
  observations.push({ kind: 'transport', value: 'Actual SFC/JeecgListMixin methods, real HTTP with legal synthetic CLI login; AntD form/confirm/nextTick facades only, no browser render or checkbox-cache acceptance.' })
  observations.push({ kind: 'requests', total: requests.length, write_operations: requests.filter(r => r.method !== 'GET').map(r => ({ method: r.method, route: r.route })) })
}
main().then(() => {
  process.stdout.write(JSON.stringify({ cases, observations, source_hashes: sourceHashes, source_ref: input.sourceRef || 'working-tree' }) + '\n')
  process.exitCode = cases.every(c => c.passed) ? 0 : 1
}).catch(error => {
  process.stdout.write(JSON.stringify({ cases, observations, source_hashes: sourceHashes, source_ref: input.sourceRef || 'working-tree', error: error.message }) + '\n')
  process.exitCode = 2
})
