const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { resolve } = require('node:path')
const { test } = require('node:test')
const vm = require('node:vm')
const axios = require('axios')
const buildURL = require('axios/lib/helpers/buildURL')

const source = file => readFileSync(resolve(__dirname, '../src', file), 'utf8')
const stripImports = text => text.replace(/^import .*$/gm, '')

// Execute the shipped API wrapper, GET helper and interceptor with an Axios adapter.
// Only the network transport is controlled; request headers and params are real.
function harness () {
  const requests = []
  const response = { success: true, result: { menu: [{ id: 'student', path: '/learn' }], auth: [], allAuth: [] } }
  const context = { ACCESS_TOKEN: 'ACCESS_TOKEN', console: { log () {} },
    window: { _CONFIG: { domianURL: '/api' } },
    Vue: { ls: { get: () => 'current-fixture-session' } },
    axios: { create: config => axios.create({ ...config, adapter: async options => {
      requests.push(options)
      return { data: response, status: 200, headers: {}, config: options }
    } }) } }
  vm.createContext(context)
  vm.runInContext(stripImports(source('utils/request.js')).replace(/export\s*\{[\s\S]*?\}\s*$/, '') + '\nthis.client = service', context)
  context.axios = context.client
  const manage = source('api/manage.js')
  vm.runInContext(manage.slice(manage.indexOf('export function getAction('), manage.indexOf('//deleteAction')).replace('export ', '') + '\nthis.getAction = getAction', context)
  const api = stripImports(source('api/api.js')).replace(/^export const /gm, 'const ').replace(/export\s*\{[\s\S]*$/, '')
  vm.runInContext(api + '\nthis.queryPermissionsByUser = queryPermissionsByUser', context)
  return { context, requests, response }
}

test('menu requests use the current header credential and ignore legacy URL credentials', async () => {
  const h = harness()
  for (const args of [[], [{ token: 'other-fixture-session', username: 'fixture_admin' }]]) {
    assert.equal(await h.context.queryPermissionsByUser(...args), h.response)
    const request = h.requests.at(-1)
    assert.equal(request.method, 'get')
    assert.equal(request.url, '/api/sys/permission/getUserPermissionByToken')
    assert.equal(request.headers['X-Access-Token'], 'current-fixture-session')
    const url = buildURL(request.url, request.params)
    assert.equal(url.includes('token'), false)
    assert.equal(url.includes('session'), false)
    assert.equal(url.includes('username'), false)
  }
})

test('store menu loading keeps menu and button data without forwarding a URL credential', async () => {
  const h = harness()
  const writes = new Map()
  const commits = []
  for (const key of ['USER_AUTH', 'SYS_BUTTON_AUTH']) h.context[key] = key
  h.context.sessionStorage = { setItem: (key, value) => writes.set(key, value) }
  vm.runInContext(stripImports(source('store/modules/user.js')).replace('export default user', 'this.user = user'), h.context)
  const response = await h.context.user.actions.GetPermissionList({ commit: (...args) => commits.push(args) })
  assert.equal(response, h.response)
  assert.equal(commits[0][0], 'SET_PERMISSIONLIST')
  assert.equal(commits[0][1], h.response.result.menu)
  assert.equal(writes.get('USER_AUTH'), '[]')
  assert.equal(writes.get('SYS_BUTTON_AUTH'), '[]')
  assert.equal(h.requests.length, 1)
  assert.equal(h.requests[0].headers['X-Access-Token'], 'current-fixture-session')
  assert.equal(h.requests[0].params.token, undefined)
})
