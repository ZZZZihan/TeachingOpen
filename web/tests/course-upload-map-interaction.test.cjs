const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const Vue = require('vue')
const compiler = require('vue-template-compiler')
Vue.config.silent = true
const root = path.resolve(__dirname, '..')
const flush = async () => { await Vue.nextTick(); await new Promise(resolve => setImmediate(resolve)); await Vue.nextTick() }
const deferred = () => { let resolve, reject; const promise = new Promise((yes, no) => { resolve = yes; reject = no }); return { promise, resolve, reject } }
function harness () {
  const calls = [], notices = [], confirms = [], listeners = new Set()
  const api = method => (url, data) => {
    if (url === '/teaching/teachingCourse/list') return Promise.resolve({ success: true, result: { records: [], total: 0 } })
    const wait = deferred(); calls.push({ method, url, data, ...wait }); return wait.promise
  }
  const context = {
    Vue: { ls: { get: () => ({ uploadType: 'local' }) } }, ACCESS_TOKEN: 'synthetic', SYS_CONFIG: 'config',
    getAction: api('get'), postAction: api('post'), deleteAction: api('delete'), putAction: api('put'), httpAction: api('save'),
    pick: require('lodash.pick'), JEditor: {}, JDictSelectTag: {}, JSelectDepart: {},
    window: { _CONFIG: { domianURL: '' }, addEventListener: (type, fn) => listeners.add(fn), removeEventListener: (type, fn) => listeners.delete(fn) },
    console: { log () {} }
  }
  vm.createContext(context)
  const load = (file, binding, template = true) => {
    const source = fs.readFileSync(path.join(root, file), 'utf8')
    const script = file.endsWith('.vue') ? source.match(/<script>([\s\S]*?)<\/script>/)[1] : source
    vm.runInContext(script.replace(/^\s*import .*$/gm, '').replace('export default', binding + ' ='), context)
    const component = context[binding]
    if (template && file.endsWith('.vue')) {
      const compiled = compiler.compile(source.slice(source.indexOf('<template>') + 10, source.indexOf('\n<script>')).replace(/<\/template>\s*$/, ''))
      assert.equal(compiled.errors.length, 0, compiled.errors.join('\n'))
      component.render = new Function(compiled.render)
      component.staticRenderFns = compiled.staticRenderFns.map(code => new Function(code))
    }
    return component
  }
  load('src/components/jeecg/JUpload.vue', 'JUpload')
  load('src/mixins/CourseFormRecovery.js', 'CourseFormRecovery', false)
  load('src/views/teaching/modules/TeachingMapEditor.vue', 'TeachingMapEditor')
  const messages = Object.fromEntries(['success', 'error', 'warning'].map(type => [type, text => notices.push({ type, text })]))
  const create = (options, propsData = {}, extras = {}) => new Vue({ ...options, propsData,
    beforeCreate () { Object.assign(this, { $message: messages, $confirm: item => confirms.push(item), ...extras }) }
  })
  const walk = (node, predicate) => {
    if (predicate(node)) return node
    for (const child of node.children || []) { const found = walk(child, predicate); if (found) return found }
    return null
  }
  const form = async (name, field) => {
    const values = {}, validators = []
    const formApi = { resetFields: () => Object.keys(values).forEach(key => delete values[key]), setFieldsValue: value => Object.assign(values, value),
      getFieldValue: key => values[key], isFieldsTouched: () => false, validateFields: callback => validators.push(callback) }
    const options = load('src/views/teaching/modules/' + name + '.vue', 'CourseForm')
    const dialog = create(options, {}, { $form: { createForm: () => formApi } })
    dialog.edit({ id: 'course-row', courseId: 'course-A', courseName: '原课程', unitName: '原单元', courseVideoSource: 1, [field]: 'attachments/old.png' })
    await flush()
    const tree = dialog._render()
    const node = walk(tree, node => node.componentOptions?.Ctor.options.name === 'JUpload' && node.data.directives?.some(d => d.name === 'decorator' && d.value[0] === field))
    assert.ok(node, field + ' is wired to the real JUpload template')
    const upload = create(context.JUpload, { ...node.componentOptions.propsData, value: values[field], uploadTarget: 'local' }, { $store: { getters: { sysConfig: { staticDomain: '', qiniuDomain: '' } } } })
    for (const [event, listener] of Object.entries(node.componentOptions.listeners || {})) upload.$on(event, listener)
    upload.$on('change', value => { values[field] = value; upload.value = value })
    dialog.$watch('uploadSession', value => { upload.session = value })
    dialog.$watch('visible', value => { upload.active = value })
    dialog.$watch('confirmLoading', value => { upload.disabled = value })
    const okDisabled = () => dialog._render().data.attrs.okButtonProps.props.disabled
    const save = () => dialog._render().data.on.ok()
    const validate = () => validators.shift()(null, { ...values })
    const event = async (file, status, response) => {
      const vnode = upload._render()
      const control = walk(vnode, n => n.tag === 'a-upload')
      assert.ok(control, 'real upload template has event control')
      return control.data.on.change({ file: { ...file, status, response }, fileList: upload.fileList.filter(f => f.uid !== file.uid).concat({ ...file, status, response }) })
    }
    const attachMap = () => {
      const node = walk(dialog._render(), n => n.componentOptions?.Ctor.options.name === 'TeachingMapEditor')
      assert.ok(node, 'real outer form contains map component')
      const map = create(context.TeachingMapEditor)
      for (const [event, listener] of Object.entries(node.componentOptions.listeners || {})) map.$on(event, listener)
      dialog.$refs.mapEditor = map
      return map
    }
    const openMap = () => {
      const button = walk(dialog._render(), n => n.tag === 'a-button' && n.children?.some(child => child.text === '地图编辑器'))
      assert.ok(button, 'real form has map editor action')
      return button.data.on.click()
    }
    return { dialog, upload, values, validators, okDisabled, save, validate, event, attachMap, openMap }
  }
  const map = () => create(context.TeachingMapEditor)
  return { calls, notices, confirms, listeners, form, map }
}
const file = uid => ({ uid, name: 'new.png', type: 'image/png', size: 1024 })
for (const name of ['TeachingCourseModal', 'TeachingCourseUnitModal']) {
  const field = name === 'TeachingCourseModal' ? 'courseCover' : 'unitCover'
  test(name + ': business failure preserves old value; retry waits for registration and writes new attachment', async () => {
    const h = harness(), f = await h.form(name, field), first = file('first')
    assert.equal(f.upload.beforeUpload(first), true)
    await flush(); assert.equal(f.okDisabled(), true); f.save(); assert.equal(f.validators.length, 0)
    await f.event(first, 'done', { success: false, message: '文件上传失败，请稍后重试' })
    assert.equal(f.values[field], 'attachments/old.png'); assert.equal(f.upload.uploadState, 'error')
    assert.equal(h.calls.length, 0); assert.equal(h.notices.some(n => n.type === 'success'), false)
    const second = file('second'); f.upload.beforeUpload(second)
    const completed = f.event(second, 'done', { success: true, message: 'attachments/new.png' })
    await flush(); assert.equal(f.upload.uploadState, 'registering'); assert.equal(f.okDisabled(), true)
    f.save(); assert.equal(f.validators.length, 0); assert.equal(f.values[field], 'attachments/old.png')
    h.calls[0].resolve({ success: true, result: { id: 'new-file', filePath: 'attachments/new.png' } }); await completed; await flush()
    assert.equal(f.okDisabled(), false); assert.equal(f.values[field], 'attachments/new.png')
    assert.equal(h.calls.filter(c => c.method === 'delete').length, 0)
    f.save(); f.validate(); assert.equal(h.calls[1].data[field], 'attachments/new.png')
    h.calls[1].resolve({ success: true }); await flush(); assert.equal(f.dialog.visible, false)
  })
  test(name + ': close and switch ignore old upload/registration callbacks', async () => {
    const h = harness(), f = await h.form(name, field), selected = file('late')
    f.upload.beforeUpload(selected)
    const completed = f.event(selected, 'done', { success: true, message: 'attachments/late.png' })
    await flush(); f.dialog.close(); await flush(); f.dialog.edit({ id: 'course-B', [field]: 'attachments/b.png' }); await flush()
    f.upload.value = f.values[field]; await flush()
    h.calls[0].resolve({ success: true, result: { id: 'late-file', filePath: 'attachments/late.png' } }); await completed; await flush()
    assert.equal(f.values[field], 'attachments/b.png'); assert.equal(h.notices.some(n => n.type === 'success'), false)
    await f.event(selected, 'done', { success: true, message: 'attachments/late.png' })
    assert.equal(h.calls.length, 1); assert.equal(f.okDisabled(), false)
  })
  test(name + ': failed registration cannot emit a new value; removing failure unlocks old value', async () => {
    const h = harness(), f = await h.form(name, field), selected = file('bad-register')
    f.upload.beforeUpload(selected)
    const completed = f.event(selected, 'done', { success: true, message: 'attachments/unregistered.png' })
    await flush(); h.calls[0].resolve({ success: false, message: 'denied' }); await completed; await flush()
    assert.equal(f.okDisabled(), true); assert.equal(f.values[field], 'attachments/old.png')
    await f.event(selected, 'removed'); await flush(); assert.equal(f.okDisabled(), false)
    f.save(); f.validate(); assert.equal(h.calls[1].data[field], 'attachments/old.png')
    h.calls[1].resolve({ success: true }); await flush()
  })
}
const course = id => ({ id, courseMap_url: id + '/map.png' })
const unit = (id, courseId) => ({ id, courseId, unitName: id, mapX: 1, mapY: 2, mediaContent: 'concurrent content must not be submitted' })
const page = (records, total = records.length) => ({ success: true, result: { records, total } })
test('map: A late page cannot replace B; empty course clears data; close removes drag listener', async () => {
  const h = harness(), m = h.map()
  const a = m.open(course('A')); m.close(); const b = m.open(course('B'))
  h.calls[1].resolve(page([unit('b1', 'B')])); await b; await flush()
  h.calls[0].resolve(page([unit('a1', 'A')])); await a; await flush()
  assert.equal(m.courseInfo.id, 'B'); assert.equal(m.unitList[0].id, 'b1')
  m.drag('b1'); await flush(); assert.equal(h.listeners.size, 1); m.selectUnit('b1'); m.drag('b1'); assert.equal(h.listeners.size, 0); m.drag('b1'); m.close(); assert.equal(h.listeners.size, 0)
  const empty = m.open(course('empty')); assert.equal(m.unitList.length, 0)
  h.calls[2].resolve(page([])); await empty; assert.equal(m.currentUnitId, ''); assert.equal(m.unitList.length, 0)
})
test('map: late course detail and rejected list after close cannot mutate a new course', async () => {
  const h = harness(), m = h.map(), a = m.openById('A', 'a1')
  m.close(); const b = m.open(course('B'))
  h.calls[1].resolve(page([unit('b1', 'B')])); await b
  h.calls[0].resolve({ success: true, result: course('A') }); await a
  assert.equal(m.courseInfo.id, 'B'); assert.equal(m.mapUrl, 'B/map.png'); assert.equal(h.calls.length, 2)
  const closed = m.open(course('C')); m.close(); h.calls[2].reject(new Error('late network error')); await closed
  assert.equal(m.loadError, ''); assert.equal(m.unitList.length, 0)
})
test('map: loads all 101 units using pageSize 100; failure retains unsaved positions; payload excludes content', async () => {
  const h = harness(), m = h.map(), load = m.open(course('A'))
  h.calls[0].resolve(page(Array.from({ length: 100 }, (_, i) => unit('a' + i, 'A')), 101)); await flush()
  assert.equal(h.calls[1].data.pageNo, 2); assert.equal(h.calls[1].data.pageSize, 100)
  h.calls[1].resolve(page([unit('a100', 'A')], 101)); await load; await flush()
  assert.equal(m.unitList.length, 101); m.unitList[0].mapX = 8; m.saved = false
  const failed = m._render().data.on.ok(); assert.deepEqual(Object.keys(h.calls[2].data.units[0]).sort(), ['id', 'mapX', 'mapY'])
  assert.equal(h.calls[2].data.courseId, 'A'); h.calls[2].resolve({ success: false }); await failed
  assert.equal(m.saved, false); assert.equal(m.unitList[0].mapX, 8); assert.ok(m.saveError); assert.equal(h.notices.length, 0)
  const saved = m._render().data.on.ok(); h.calls[3].resolve({ success: true }); await saved; assert.equal(m.saved, true)
})
test('map: failed/incomplete or mixed-course list blocks saving; invalid coordinates never request', async () => {
  const h = harness(), m = h.map(), bad = m.open(course('A'))
  h.calls[0].resolve(page([unit('b1', 'B')])); await bad; assert.ok(m.loadError); await m.handleOk(); assert.equal(h.calls.length, 1)
  const load = m.open(course('A')); h.calls[1].resolve(page([unit('a1', 'A')])); await load
  m.unitList[0].mapX = 'abc'; await m.handleOk(); assert.equal(h.calls.length, 2); assert.ok(m.saveError)
})
test('map: destroy invalidates loads and drag; late save cannot mark a new course saved', async () => {
  const h = harness(), m = h.map(), load = m.open(course('A'))
  h.calls[0].resolve(page([unit('a1', 'A')])); await load
  m.saved = false; const save = m.handleOk(); m.close(); const other = m.open(course('B'))
  h.calls[2].resolve(page([unit('b1', 'B')])); await other; m.saved = false
  h.calls[1].resolve({ success: true }); await save; assert.equal(m.saved, false); assert.equal(h.notices.length, 0)
  m.drag('b1'); m.$destroy(); assert.equal(h.listeners.size, 0)
})

test('unit outer form: saving map refreshes its stale coordinates before later content save', async () => {
  const h = harness(), f = await h.form('TeachingCourseUnitModal', 'unitCover'), m = f.attachMap()
  f.values.mapX = 1; f.values.mapY = 2; f.dialog.model.mapX = 1; f.dialog.model.mapY = 2
  f.openMap(); assert.equal(h.calls[0].data.id, 'course-A')
  h.calls[0].resolve({ success: true, result: course('course-A') }); await flush()
  h.calls[1].resolve(page([unit('course-row', 'course-A')])); await flush()
  m.unitList[0].mapX = 88; m.unitList[0].mapY = 99; m.saved = false
  const saved = m._render().data.on.ok(); h.calls[2].resolve({ success: true }); await saved; await flush()
  assert.equal(f.values.mapX, 88); assert.equal(f.values.mapY, 99); assert.equal(f.dialog.model.mapX, 88)
  f.values.unitIntro = 'new content'; f.save(); f.validate()
  assert.equal(h.calls[3].data.mapX, 88); assert.equal(h.calls[3].data.unitIntro, 'new content')
  h.calls[3].resolve({ success: true }); await flush()
})
test('unit outer form: changed decorator course or new unit must be saved before map can open', async () => {
  const h = harness(), f = await h.form('TeachingCourseUnitModal', 'unitCover'), m = f.attachMap()
  f.values.courseId = 'course-B'; f.openMap(); assert.equal(h.calls.length, 0); assert.equal(m.visible, false)
  assert.equal(f.dialog.model.courseId, 'course-A'); assert.ok(h.notices.some(n => n.type === 'warning'))
  f.dialog.edit({ id: 'b-unit', courseId: 'course-B' }); await flush(); f.openMap()
  assert.equal(h.calls[0].data.id, 'course-B'); assert.equal(m.courseInfo.id, 'course-B')
  m.close(); h.calls[0].resolve({ success: true, result: course('course-B') }); await flush()
  f.dialog.add(); await flush(); f.values.courseId = 'course-B'; f.openMap(); assert.equal(h.calls.length, 1)
})
