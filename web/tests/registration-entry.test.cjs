const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { resolve } = require('node:path')
const { test } = require('node:test')
const compiler = require('vue-template-compiler')

test('registration entry compiles and links to the named registration route', () => {
    const component = compiler.parseComponent(readFileSync(resolve(__dirname, '../src/views/home/modules/RegistrationEntry.vue'), 'utf8'))
    const compiled = compiler.compile(component.template.content)
    assert.deepEqual(compiled.errors, [])
    assert.match(compiled.render, /name:\s*'register'/)
})
