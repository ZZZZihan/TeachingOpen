// Actual component/mixin methods -> owned HTTP -> read-only DB observations.
// AntD confirmation/refs are small facades; this does not claim browser rendering.
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const crypto = require('node:crypto')
const { execFileSync } = require('node:child_process')
const babel = require('@babel/core')
const input = JSON.parse(fs.readFileSync(0, 'utf8'))
const source = path.resolve(process.argv[2])
if (input.origin !== 'http://127.0.0.1:18178') throw Error('Only the owned member-context server is supported')
const cases = [], observations = [], sourceHashes = {}, requests = [], pending = new Set()
let credential = input.token
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
  for (let i = 0; i < 100; i++) {
    await Promise.allSettled([...pending])
    await new Promise(resolve => setImmediate(resolve))
    if (!pending.size) return
  }
  throw Error('Component request chain did not settle')
}
function action(route, params, method) {
  const allowed = {
    '/sys/user/departUserList': 'GET', '/sys/user/list': 'GET', '/sys/role/queryMySubRole': 'GET',
    '/sys/sysDepart/removeAll': 'GET', '/sys/user/editSysDepartWithUser': 'POST',
    '/sys/user/deleteUserInDepart': 'DELETE', '/sys/user/deleteUserInDepartBatch': 'DELETE'
  }
  if (allowed[route] !== method) throw Error('Non-probe endpoint rejected')
  if (route === '/sys/sysDepart/removeAll' && !Object.values(input.classes).includes(params.id)) throw Error('Non-owned clear rejected')
  if (method !== 'GET' && !Object.values(input.classes).includes(params.depId)) throw Error('Non-owned mutation rejected')
  for (const id of params?.userIdList || (params?.userIds || params?.userId || '').split(',').filter(Boolean)) {
    if (!Object.values(input.users).includes(id)) throw Error('Non-owned user rejected')
  }
  const url = new URL('/api' + route, input.origin)
  const options = { method, headers: { 'X-Access-Token': credential }, signal: AbortSignal.timeout(15000) }
  if (method === 'GET' || method === 'DELETE') {
    for (const [key, value] of Object.entries(params || {})) if (value != null) url.searchParams.set(key, value)
  } else {
    options.headers['Content-Type'] = 'application/json'; options.body = JSON.stringify(params)
  }
  const record = { method, route }
  requests.push(record)
  return track(fetch(url, options).then(async response => {
    if (!response.ok) throw Error('Owned HTTP request failed with status ' + response.status)
    const body = await response.json()
    record.success = body.success === true
    record.code = body.code
    return body
  }))
}
const getAction = (route, params) => action(route, params, 'GET')
const postAction = (route, params) => action(route, params, 'POST')
const deleteAction = (route, params) => action(route, params, 'DELETE')
const queryMySubRole = () => getAction('/sys/role/queryMySubRole')
const utility = read('web/src/utils/util.js')
const start = utility.indexOf('export function filterObj('), end = utility.indexOf('\n}', start) + 2
if (start < 0 || end < start) throw Error('Real filterObj function not found')
const utilContext = { module: { exports: {} } }
vm.runInNewContext(utility.slice(start, end).replace('export function filterObj', 'module.exports = function filterObj'), utilContext)
function load(file, extras = {}) {
  let code = read(file)
  if (file.endsWith('.vue')) code = code.split('<script>')[1].split('</script>')[0]
  code = code.replace(/^\s*import .*$/mg, '').replace('export const JeecgListMixin =', 'module.exports =').replace('export default', 'module.exports =')
  if (file.endsWith('JeecgListMixin.js')) code = babel.transformSync(code, {
    cwd: path.join(source, 'web'), babelrc: false, configFile: false,
    presets: [[require.resolve('@vue/babel-preset-app'), { useBuiltIns: false }]]
  }).code
  const context = { module: { exports: {} }, getAction, postAction, deleteAction, queryMySubRole,
    filterObj: utilContext.module.exports, Vue: { ls: { get: () => input.token } }, ACCESS_TOKEN: 'owned-cli-token',
    console: { log() {}, warn() {}, error() {} }, downFile() {}, getFileAccessHttpUrl() {}, ...extras }
  vm.runInNewContext(code, context, { filename: file })
  return context.module.exports
}
const mixin = load('web/src/mixins/JeecgListMixin.js')
const selectorComponent = load('web/src/views/system/modules/SelectUserModal.vue')
const parentComponent = load('web/src/views/system/modules/DeptUserInfo.vue', {
  JeecgListMixin: mixin, SelectUserModal: selectorComponent, UserModal: {}, DeptRoleUserModal: {}
})
function instance(component) {
  const ctx = { $refs: {}, confirmations: [], emitted: [], messages: [], disableMixinCreated: true,
    $message: Object.fromEntries(['error', 'warning', 'success'].map(type => [type, () => ctx.messages.push(type)])),
    $confirm: options => ctx.confirmations.push(options), $nextTick: callback => track(Promise.resolve().then(callback)),
    $emit: (type, payload) => ctx.emitted.push({ type, payload }), $set: (object, key, value) => { object[key] = value } }
  const definitions = [...(component.mixins || []), component]
  for (const definition of definitions) if (definition.data) Object.assign(ctx, definition.data.call(ctx))
  for (const definition of definitions) for (const [name, method] of Object.entries(definition.methods || {})) ctx[name] = method.bind(ctx)
  for (const definition of definitions) for (const [name, getter] of Object.entries(definition.computed || {})) Object.defineProperty(ctx, name, { configurable: true, get: () => getter.call(ctx) })
  return ctx
}
async function workspace() {
  const parent = instance(parentComponent), modal = instance(selectorComponent)
  const ancillary = () => ({ visible: false, close() { this.visible = false }, handleCancel() { this.visible = false } })
  parent.$refs = { selectUserModal: modal, modalForm: ancillary(), deptRoleUser: ancillary() }
  modal.$emit = (type, payload) => { modal.emitted.push({ type, payload }); if (type === 'selectFinished') parent.selectOK(payload) }
  if (selectorComponent.created) selectorComponent.created.call(modal)
  await settle()
  return { parent, modal }
}
const A = { id: input.classes.A, orgCategory: '3', departName: 'Synthetic A' }
const B = { id: input.classes.B, orgCategory: '3', departName: 'Synthetic B' }
async function open(parent, department) { parent.open(department); await settle() }
function select(parent, alias) {
  const row = parent.dataSource.find(row => row.id === input.users[alias])
  if (!row) throw Error('Owned user missing from real department list')
  parent.onSelectChange([row.id], [row]); return row
}
function db() {
  return JSON.parse(execFileSync('python3', [input.wrapper, '--runtime', input.runtime, '--db-state'], { encoding: 'utf8', timeout: 30000 }))
}
function writes(index, route) { return requests.slice(index).filter(r => r.route === route).length }
async function reset(shared = false) {
  credential = input.token
  for (const id of Object.values(input.classes)) await getAction('/sys/sysDepart/removeAll', { id })
  await postAction('/sys/user/editSysDepartWithUser', { depId: A.id, userIdList: [input.users.teacher_a, input.users.student_a] })
  await postAction('/sys/user/editSysDepartWithUser', { depId: B.id, userIdList: [input.users.teacher_b, input.users.student_b, ...(shared ? [input.users.student_a] : [])] })
  await settle()
}
async function chooseUser(parent, modal, alias) {
  parent.handleAddUserDepart(); await settle()
  // Old selector loads on creation; the new selector loads on show. Both use real HTTP.
  const row = modal.dataSource1.find(row => row.id === input.users[alias])
  if (!row) throw Error('Owned user missing from real selection list')
  modal.onSelectChange([row.id], [row])
}
async function main() {
  await reset()
  {
    const { parent } = await workspace()
    await open(parent, A); parent.handleRemoveAll()
    const confirmation = parent.confirmations.pop()
    if (!confirmation) throw Error('Expected clear confirmation')
    await open(parent, B)
    const before = requests.length; confirmation.onOk(); await settle()
    check('A clear confirmation after switching to B sends no removeAll', writes(before, '/sys/sysDepart/removeAll') === 0)
    const state = db()
    check('stale clear preserves B teacher and student in DB', state.B.teacher_b && state.B.student_b, { member_count: state.B.count })
    check('stale clear preserves A members in DB', state.A.teacher_a && state.A.student_a)
  }
  await reset(true)
  {
    const { parent } = await workspace()
    await open(parent, A); select(parent, 'student_a'); parent.batchDel()
    const confirmation = parent.confirmations.pop()
    if (!confirmation) throw Error('Expected batch confirmation')
    await open(parent, B)
    const before = requests.length; confirmation.onOk(); await settle()
    check('A pending batch confirmation after switching to B sends no delete', writes(before, '/sys/user/deleteUserInDepartBatch') === 0)
    const state = db()
    check('stale batch preserves the shared user B association in DB', state.B.student_a)
    check('stale batch preserves the A association in DB', state.A.student_a)
  }
  await reset(true)
  {
    const { parent } = await workspace()
    await open(parent, A); select(parent, 'student_a'); await open(parent, B)
    const before = requests.length; parent.batchDel()
    const confirmation = parent.confirmations.pop(); if (confirmation) confirmation.onOk()
    await settle()
    check('A selected keys are unusable when batch menu is opened in B', writes(before, '/sys/user/deleteUserInDepartBatch') === 0)
    check('batch menu after class switch preserves shared B relation in DB', db().B.student_a)
  }
  for (const reopen of [false, true]) {
    await reset()
    const { parent, modal } = await workspace()
    await open(parent, A); await chooseUser(parent, modal, 'student_a')
    if (reopen) modal.handleCancel()
    await open(parent, B)
    if (reopen) { parent.handleAddUserDepart(); await settle() }
    const before = requests.length; modal.handleOk(); await settle()
    check((reopen ? 'closed A modal reopened in B' : 'A modal after switching to B') + ' sends no stale add', writes(before, '/sys/user/editSysDepartWithUser') === 0)
    check((reopen ? 'reopened' : 'switched') + ' selector does not attach A student to B in DB', !db().B.student_a)
  }
  await reset()
  {
    const { parent, modal } = await workspace()
    await open(parent, B)
    check('normal B list contains its teacher and student only', parent.dataSource.length === 2 && parent.dataSource.some(row => row.id === input.users.student_b))
    await chooseUser(parent, modal, 'student_a'); modal.handleOk(); await settle()
    check('normal B selection adds an existing user through real HTTP and DB', db().B.student_a && parent.dataSource.some(row => row.id === input.users.student_a))
    const row = select(parent, 'student_a')
    if (parent.confirmDelete) { parent.confirmDelete(row); parent.confirmations.pop().onOk() } else parent.handleDelete(row.id)
    await settle()
    const removed = db()
    check('normal B single cancellation removes only that relation in DB', !removed.B.student_a && removed.B.teacher_b && removed.B.student_b && removed.A.student_a)
    select(parent, 'student_b'); parent.batchDel(); parent.confirmations.pop().onOk(); await settle()
    check('normal B batch cancellation removes current student and preserves teacher', !db().B.student_b && db().B.teacher_b)
    parent.handleRemoveAll(); parent.confirmations.pop().onOk(); await settle()
    const cleared = db()
    check('normal B clear removes its remaining relations and preserves A/accounts', cleared.B.count === 0 && cleared.A.count === 2 && cleared.user_count === 5)
  }
  await reset()
  {
    const { parent } = await workspace()
    await open(parent, B); const row = select(parent, 'teacher_b')
    credential = input.studentToken
    const before = requests.length, state = db()
    if (parent.confirmDelete) { parent.confirmDelete(row); parent.confirmations.pop().onOk() } else parent.handleDelete(row.id)
    await settle(); credential = input.token
    const rejected = requests.slice(before).find(r => r.route === '/sys/user/deleteUserInDepart')
    check('actual low-level cancellation returns a business refusal', rejected && rejected.success === false, { business_code: rejected?.code })
    check('refused cancellation preserves the full relation matrix in DB', JSON.stringify(state) === JSON.stringify(db()))
    check('refused cancellation displays feedback without success', !parent.messages.includes('success') && (!!parent.actionError || parent.messages.some(type => ['error', 'warning'].includes(type))))
  }
  observations.push({ kind: 'transport', value: 'Actual SFC/JeecgListMixin methods with legal CLI synthetic login, real HTTP, immediate read-only DB checks; confirmation/ref facades do not test Vue/AntD rendering.' })
  observations.push({ kind: 'requests', total: requests.length, operations: requests })
}
main().then(() => {
  process.stdout.write(JSON.stringify({ cases, observations, source_hashes: sourceHashes, source_ref: input.sourceRef || 'working-tree' }) + '\n')
  process.exitCode = cases.every(c => c.passed) ? 0 : 1
}).catch(error => {
  process.stdout.write(JSON.stringify({ cases, observations, source_hashes: sourceHashes, source_ref: input.sourceRef || 'working-tree', error: error.message }) + '\n')
  process.exitCode = 2
})
