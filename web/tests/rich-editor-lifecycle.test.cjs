const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const vm = require('node:vm')
const path = require('node:path')
const source = fs.readFileSync(path.join(__dirname, '../src/components/jeecg/JEditor.vue'), 'utf8')
function instance () {
  const context = { sanitizeRichText: value => value || '', safeMediaUrl: value => value, Vue: {}, SYS_CONFIG: '', component: null }
  vm.createContext(context)
  vm.runInContext('component = ' + source.match(/export default ([\s\S]*?)<\/script>/)[1], context)
  const component = context.component
  const state = { ...component.data.call({ value: '<p>A</p>' }), active: true, disabled: false, _uploadGeneration: 0, _editorGeneration: 0, _editorInitialized: true, $nextTick: callback => callback(),
    _editor: { destroy () {}, commands: { setContent: value => { state.content = value } }, setEditable: value => { state.editable = value } } }
  for (const [key, fn] of Object.entries(component.methods)) state[key] = fn.bind(state)
  state.createEditor = () => { state.content = state.myValue; state._editor = { destroy () {}, setEditable () {} } }
  let resolve, reject
  state.uploadMedia = () => new Promise((a, b) => { resolve = a; reject = b })
  state.dialog = 'image'
  const pending = () => state.uploadFile({ target: { files: [{ name: 'a.png', type: 'image/png' }] } })
  return { component, state, pending, resolve: value => resolve(value), reject: value => reject(value) }
}
for (const boundary of ['value', 'session', 'active', 'disabled']) {
  test('pending upload cannot cross editor ' + boundary + ' boundary', async () => {
    const h = instance(), pending = h.pending()
    h.state.preview = true; h.state.fullscreen = true
    const next = boundary === 'value' ? '<p>B</p>' : boundary === 'session' ? 2 : boundary === 'disabled'
    if (boundary !== 'value') h.state[boundary] = next
    h.component.watch[boundary].call(h.state, next)
    h.resolve('https://example.test/a.png'); await pending
    assert.equal(h.state.draft, ''); assert.equal(h.state.dialog, ''); assert.equal(h.state.uploading, false)
    assert.equal(h.state.fullscreen, false); assert.equal(h.state.preview, false)
    if (boundary === 'value') assert.equal(h.state.content, '<p>B</p>')
  })
}
test('closing a session restores fullscreen node and ignores rejected old upload', async () => {
  const h = instance(), pending = h.pending(), calls = []
  const parent = { insertBefore: (...args) => calls.push(['insert', ...args]), removeChild: node => calls.push(['remove', node]) }
  const anchor = { parentNode: parent }; h.state._fullscreenAnchor = anchor; h.state.$el = {}
  h.state.active = false; h.component.watch.active.call(h.state, false)
  h.reject(Error('old session failed')); await pending
  assert.equal(h.state.error, ''); assert.equal(h.state._fullscreenAnchor, null)
  assert.equal(calls.length, 2); assert.equal(calls[0][1], h.state.$el)
})
test('ordinary input echo does not cancel current editing dialog', () => {
  const h = instance(); h.component.watch.value.call(h.state, '<p>A</p>')
  assert.equal(h.state.dialog, 'image'); assert.equal(h.state._uploadGeneration, 0)
})
