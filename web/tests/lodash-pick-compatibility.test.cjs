const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const parser = require('@babel/parser')
const traverse = require('@babel/traverse').default
const pick = require('lodash/pick')

function sourceFiles (directory) {
  return fs.readdirSync(directory, { withFileTypes: true }).flatMap(entry => {
    const file = path.join(directory, entry.name)
    return entry.isDirectory() ? sourceFiles(file) : /\.(vue|js)$/.test(file) ? [file] : []
  })
}

function literalFields (argumentsList) {
  return argumentsList.map(argument => {
    assert.equal(argument.type, 'StringLiteral', 'Form field names must be explicit strings during this migration')
    assert.doesNotMatch(argument.value, /[.\[\]]/, 'The retired package selected shallow property names')
    return argument.value
  })
}

test('所有现有表单字段在替换后保留浅层筛选及空值语义', () => {
  const calls = []
  for (const file of sourceFiles(path.resolve(__dirname, '../src'))) {
    const source = fs.readFileSync(file, 'utf8')
    if (!/from ['"]lodash\/pick['"]/.test(source)) continue
    const script = file.endsWith('.vue') ? source.match(/<script[^>]*>([\s\S]*?)<\/script>/)[1] : source
    const ast = parser.parse(script, { sourceType: 'module', plugins: ['jsx', 'objectRestSpread'] })
    traverse(ast, {
      CallExpression (call) {
        if (call.node.callee.name !== 'pick') return
        const fields = []
        for (const argument of call.node.arguments.slice(1)) {
          if (argument.type !== 'SpreadElement') {
            fields.push(...literalFields([argument]))
            continue
          }
          // UserModal chooses optional fields by pushing literal names into its local array.
          assert.equal(argument.argument.type, 'Identifier')
          const binding = call.scope.getBinding(argument.argument.name)
          assert.ok(binding && binding.constant)
          assert.equal(binding.path.node.init.type, 'ArrayExpression')
          fields.push(...literalFields(binding.path.node.init.elements))
          for (const reference of binding.referencePaths) {
            if (reference.parentPath.isSpreadElement()) continue
            const member = reference.parentPath
            assert.ok(member.isMemberExpression() && !member.node.computed && member.node.property.name === 'push')
            assert.ok(member.parentPath.isCallExpression())
            fields.push(...literalFields(member.parentPath.node.arguments))
          }
        }
        calls.push({ file, fields })
      }
    })
  }
  assert.ok(calls.length > 0, 'Exercise the actual form consumers')
  for (const { file, fields } of calls) {
    const values = [undefined, null, '', 0, false, ['attachment'], { enabled: true }]
    const selected = Object.fromEntries(fields.map((field, index) => [field, values[index % values.length]]))
    const record = { ...selected, '__unselected_account_secret__': 'must not leave the model' }
    assert.deepEqual(pick(record, ...fields), selected, file)
    assert.deepEqual(pick(Object.create(record), fields), selected, file + ' inherited fields')
    assert.deepEqual(pick({}, fields), {}, file + ' missing fields')
  }
})

test('筛选数组和对象保留引用，缺失字段与显式undefined保持区别', () => {
  const record = { attachments: ['one'], settings: { enabled: true }, empty: undefined }
  const result = pick(record, ['attachments', 'settings', 'empty', 'missing'])
  assert.equal(result.attachments, record.attachments)
  assert.equal(result.settings, record.settings)
  assert.equal(Object.prototype.hasOwnProperty.call(result, 'empty'), true)
  assert.equal(Object.prototype.hasOwnProperty.call(result, 'missing'), false)
  assert.deepEqual(pick(null, 'field'), {})
  assert.deepEqual(pick(undefined, 'field'), {})
})

test('恶意字段路径不能修改源数据或Object原型，允许字段仍然可选', () => {
  const sentinel = 'teachingOpenPickPollutionRegression'
  const record = JSON.parse('{"safe":"allowed","__proto__":{"teachingOpenPickPollutionRegression":true},"constructor":{"prototype":{"teachingOpenPickPollutionRegression":true}},"prototype":{"teachingOpenPickPollutionRegression":true}}')
  const snapshot = JSON.stringify(record)
  const originalPrototype = Object.getOwnPropertyDescriptors(Object.prototype)
  const attacks = ['__proto__.' + sentinel, 'constructor.prototype.' + sentinel, 'prototype.' + sentinel]
  for (const attack of attacks) {
    assert.deepEqual(pick(record, attack), {})
    assert.deepEqual(pick(record, 'safe', attack), { safe: 'allowed' })
    assert.equal(JSON.stringify(record), snapshot)
    assert.deepEqual(Object.getOwnPropertyDescriptors(Object.prototype), originalPrototype)
    assert.equal(({})[sentinel], undefined)
  }
})
