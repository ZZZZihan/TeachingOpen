const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { test } = require('node:test')
const vm = require('node:vm')
const compiler = require('vue-template-compiler')
const parsed = compiler.parseComponent(readFileSync(require('node:path').resolve(__dirname, '../src/views/home/modules/PublicUserDirectory.vue'), 'utf8'))
function subject (getAction) {
    const context = { getAction }
    vm.runInNewContext(parsed.script.content.replace(/^import .*$/m, '').replace('export default', 'this.component ='), context)
    const state = context.component.data()
    state.loadPage = context.component.methods.loadPage.bind(state)
    return state
}
const payload = (total = 0, pageNo = 1, records = []) => ({ success: true, result: { total, pageNo, pageSize: 10, records } })
test('loading and empty are distinct and template compiles', async () => {
    assert.deepEqual(compiler.compile(parsed.template.content).errors, [])
    let finish
    const state = subject(() => new Promise(resolve => { finish = resolve }))
    const pending = state.loadPage(1)
    assert.equal(state.loading, true); assert.equal(state.total, null)
    finish(payload()); await pending
    assert.equal(state.loading, false); assert.equal(state.total, 0); assert.equal(state.error, false)
})
test('failure is not zero registrations and retry recovers', async () => {
    let response = { success: false }
    const state = subject(async () => response)
    await state.loadPage(1); assert.equal(state.error, true); assert.equal(state.total, null)
    response = payload(); await state.loadPage(1); assert.equal(state.error, false)
})
test('latest response wins and visible records have only public fields', async () => {
    const pending = []
    const state = subject(() => new Promise(resolve => pending.push(resolve)))
    const first = state.loadPage(1); const second = state.loadPage(2)
    pending[1](payload(11, 2, [{ name: '王*明', school: '完整学校', identity: '学生', id: 'private' }]))
    await second; pending[0](payload()); await first
    assert.equal(state.pageNo, 2); assert.equal(state.total, 11)
    assert.deepEqual(Object.keys(state.records[0]).sort(), ['identity', 'name', 'school'])
})
test('malformed response is an error', async () => {
    const state = subject(async () => payload(20, 1, []))
    await state.loadPage(1); assert.equal(state.error, true)
})
