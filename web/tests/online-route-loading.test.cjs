const { test } = require('node:test')
const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const vm = require('node:vm')
const { resolve } = require('node:path')

function harness (load) {
  const source = readFileSync(resolve(__dirname, '../src/utils/onlineRoute.js'), 'utf8')
    .replace('export function', 'function')
    .replace(/import\(\/\* webpackChunkName: "online-forms" \*\/ '\.\/onlineComponents'\)/, 'load()')
  const context = vm.createContext({ load })
  vm.runInContext(source, context)
  return context.resolveOnlineRoute
}

const routes = [
  ['cgform/OnlCgformHeadList', 'OnlCgformHeadList'],
  ['cgform/OnlCgformCopyList', 'OnlCgformCopyList'],
  ['cgform/auto/OnlCgformAutoList', 'OnlCgformAutoList'],
  ['cgform/auto/OnlCgformTreeList', 'OnlCgformTreeList'],
  ['cgform/auto/erp/OnlCgformErpList', 'OnlCgformErpList'],
  ['cgform/auto/innerTable/OnlCgformInnerTableList', 'OnlCgformInnerTableList'],
  ['cgreport/OnlCgreportHeadList', 'OnlCgreportHeadList'],
  ['cgreport/auto/OnlCgreportAutoList', 'OnlCgreportAutoList']
]

test('building menus does not load Online; visiting each route returns its original component', async () => {
  let loads = 0
  const components = Object.fromEntries(routes.map(([, name]) => [name, { name }]))
  const resolveRoute = harness(async () => { loads++; return { default: components } })
  const factories = routes.map(([path]) => resolveRoute('modules/online/' + path))
  assert.equal(loads, 0)
  for (let i = 0; i < factories.length; i++) {
    assert.equal(await factories[i](), components[routes[i][1]])
    assert.equal(loads, i + 1)
  }
})

test('normal and unknown menu paths keep the existing route loader and never load Online', () => {
  const resolveRoute = harness(() => { throw new Error('unexpected Online download') })
  for (const path of ['teaching/TeachingWorkList', 'dashboard/Analysis', 'modules/online/unknown', 'toString', '__proto__']) {
    assert.equal(resolveRoute(path), null)
  }
})

test('a failed chunk load rejects navigation and can be retried with the same route factory', async () => {
  const unavailable = new Error('chunk unavailable')
  const component = { name: 'OnlCgformHeadList' }
  let calls = 0
  const factory = harness(async () => {
    if (++calls === 1) throw unavailable
    return { default: { OnlCgformHeadList: component } }
  })('modules/online/cgform/OnlCgformHeadList')
  await assert.rejects(factory(), error => error === unavailable)
  assert.equal(await factory(), component)
})
