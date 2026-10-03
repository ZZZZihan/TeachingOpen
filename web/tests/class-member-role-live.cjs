// Narrow actual role SFC -> HTTP -> DB test; credentials arrive only on stdin.
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const crypto = require('node:crypto')
const { execFileSync } = require('node:child_process')
const input = JSON.parse(fs.readFileSync(0, 'utf8')), source = path.resolve(process.argv[2])
if (input.origin !== 'http://127.0.0.1:18178' || input.userId !== 'fixture_student_a' || input.departId !== 'fixture_class_a') throw Error('Only owned role fixtures supported')
const cases = [], requests = [], dbObservations = [], pending = new Set()
function check(name, passed) { cases.push({ case: name, passed: !!passed }) }
function track(promise) { pending.add(promise); promise.then(() => pending.delete(promise), () => pending.delete(promise)); return promise }
async function settle() {
  for (let i = 0; i < 100; i++) {
    await Promise.allSettled([...pending]); await new Promise(resolve => setImmediate(resolve))
    if (!pending.size) return
  }
  throw Error('Role requests did not settle')
}
function action(route, params, method) {
  const allowed = { '/sys/sysDepartRole/getDeptRoleList': 'GET', '/sys/sysDepartRole/getDeptRoleByUserId': 'GET', '/sys/sysDepartRole/deptRoleUserAdd': 'POST' }
  if (allowed[route] !== method || params.userId !== input.userId || (params.departId && params.departId !== input.departId)) throw Error('Non-owned role operation rejected')
  const roleScopes = value => (value || '').split(',').filter(Boolean).map(id => {
    const alias = Object.keys(input.roles).find(key => input.roles[key] === id)
    if (!alias) throw Error('Non-owned role mutation rejected')
    return alias[0]
  })
  const record = { method, route }
  if (method === 'POST') {
    record.old_role_scopes = roleScopes(params.oldRoleId); record.new_role_scopes = roleScopes(params.newRoleId)
  }
  requests.push(record)
  const url = new URL('/api' + route, input.origin)
  const options = { method, headers: { 'X-Access-Token': input.token }, signal: AbortSignal.timeout(15000) }
  if (method === 'GET') for (const [key, value] of Object.entries(params)) url.searchParams.set(key, value)
  else { options.headers['Content-Type'] = 'application/json'; options.body = JSON.stringify(params) }
  return track(fetch(url, options).then(async response => {
    if (!response.ok) throw Error('Owned role HTTP failed with status ' + response.status)
    const body = await response.json(); record.success = body.success === true; record.code = body.code; return body
  }))
}
const file = 'web/src/views/system/modules/DeptRoleUserModal.vue'
const text = input.sourceRef ? execFileSync('git', ['-C', source, 'show', input.sourceRef + ':' + file], { encoding: 'utf8' }) : fs.readFileSync(path.join(source, file), 'utf8')
const code = text.split('<script>')[1].split('</script>')[0].replace(/^\s*import .*$/mg, '').replace('export default', 'module.exports =')
const context = { module: { exports: {} }, getAction: (route, params) => action(route, params, 'GET'),
  httpAction: (route, params, method) => action(route, params, method.toUpperCase()), JEllipsis: {}, initDictOptions() {}, console: { log() {}, warn() {}, error() {} } }
vm.runInNewContext(code, context, { filename: file })
const component = context.module.exports
function instance() {
  const modal = { emitted: [], messages: [], $emit: type => modal.emitted.push(type),
    $message: Object.fromEntries(['success', 'warning', 'error'].map(type => [type, () => modal.messages.push(type)])),
    $form: { createForm: () => ({ resetFields() {} }) } }
  Object.assign(modal, component.data.call(modal))
  for (const [name, method] of Object.entries(component.methods)) modal[name] = method.bind(modal)
  return modal
}
function db() { return JSON.parse(execFileSync('python3', [input.wrapper, '--runtime', input.runtime, '--db-state', '--prefix', input.prefix], { encoding: 'utf8', timeout: 30000 })) }
async function main() {
  const modal = instance()
  modal.add({ id: input.userId }, input.departId); await settle()
  check('actual A role options contain the two A roles and exclude B', modal.designNameOption.length === 2 && modal.designNameOption.every(option => [input.roles.Aold, input.roles.Anew].includes(option.value)))
  const before = requests.length
  modal.cancelCheckALL(); modal.handleSubmit(); await settle()
  check('actual A cancellation submits successfully', requests.slice(before).some(request => request.method === 'POST' && request.success))
  const removed = db()
  dbObservations.push({ phase: 'after A role removal', role_row_counts: removed.counts })
  check('saving empty A selection removes the original A role in DB', !removed.Aold)
  check('saving empty A selection preserves the B role in DB', removed.Bold)
  // Restore only the owned B assignment through its real API before testing
  // addition independently, so a legacy cancellation cannot mask this result.
  if (!removed.Bold) await action('/sys/sysDepartRole/deptRoleUserAdd', { userId: input.userId, oldRoleId: '', newRoleId: input.roles.Bold }, 'POST')
  modal.add({ id: input.userId }, input.departId); await settle()
  modal.designNameChange([input.roles.Anew])
  const addIndex = requests.length
  modal.handleSubmit(); await settle()
  check('actual A addition submits successfully', requests.slice(addIndex).some(request => request.method === 'POST' && request.success))
  const added = db()
  dbObservations.push({ phase: 'after A role addition', role_row_counts: added.counts })
  check('saving A selection adds the selected A role in DB', added.Anew && !added.Aold)
  check('saving A selection preserves the B role in DB', added.Bold)
}
function emit(error) {
  process.stdout.write(JSON.stringify({ cases, observations: [{ kind: 'transport', value: 'Actual DeptRoleUserModal methods, real HTTP, immediate owned DB checks; no Vue/AntD rendering.' }, { kind: 'requests', operations: requests }, { kind: 'database', phases: dbObservations }],
    source_hashes: { [file]: crypto.createHash('sha256').update(text).digest('hex') }, source_ref: input.sourceRef || 'working-tree', ...(error ? { error: error.message } : {}) }) + '\n')
  process.exitCode = error ? 2 : cases.every(test => test.passed) ? 0 : 1
}
main().then(() => emit(), emit)
