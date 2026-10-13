const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const parser = require('@babel/parser')
const axios = require('axios')
assert.equal(require('axios/package.json').version, require('../package.json').dependencies.axios,
  'Run this wire contract test with the locked frontend dependencies')

// Execute the real three frontend layers and Axios serializer without a network request.
function declaration (file, name) {
  const source = fs.readFileSync(path.join(__dirname, '..', file), 'utf8')
  const ast = parser.parse(source, { sourceType: 'module' })
  for (let node of ast.program.body) {
    if (node.type === 'ExportNamedDeclaration') node = node.declaration
    if (node && (node.id?.name === name || node.declarations?.some(value => value.id.name === name))) {
      return source.slice(node.start, node.end)
    }
  }
  throw new Error('Missing source declaration: ' + name)
}

for (const value of ['A+B% C中文', '%41', 'a&b=c?#/+', '中'.repeat(256), '😀']) {
  test('form checker preserves URI transport for ' + (value.length > 25 ? '256 Chinese characters' : JSON.stringify(value)), async () => {
    let wire
    const client = axios.create({ adapter: async config => {
      wire = client.getUri(config)
      return { status: 200, headers: {}, data: { success: true }, config }
    } })
    client.interceptors.response.use(response => response.data)
    const context = vm.createContext({ axios: client })
    vm.runInContext(declaration('src/api/manage.js', 'getAction'), context)
    vm.runInContext(declaration('src/api/api.js', 'checkRuleByCode') + '\napi = { checkRuleByCode }', context)
    vm.runInContext(declaration('src/utils/util.js', 'validateCheckRule'), context)
    const result = await new Promise(resolve => context.validateCheckRule('fixture_check', value, resolve))
    assert.equal(result, undefined)
    const url = new URL(wire, 'http://fixture.invalid')
    assert.equal(url.pathname, '/sys/checkRule/checkByCode')
    assert.equal(url.searchParams.get('ruleCode'), 'fixture_check')
    const servletValue = url.searchParams.get('value')
    assert.equal(servletValue, encodeURIComponent(value))
    assert.equal(decodeURIComponent(servletValue), value)
    assert.ok(wire.includes('%25'), 'Axios serializes the already encoded percent signs')
  })
}

test('empty optional form values keep their existing local success behavior', async () => {
  const context = vm.createContext({ api: { checkRuleByCode: () => assert.fail('Empty field must not send a request') } })
  vm.runInContext(declaration('src/utils/util.js', 'validateCheckRule'), context)
  const result = await new Promise(resolve => context.validateCheckRule('fixture_check', '', resolve))
  assert.equal(result, undefined)
})
