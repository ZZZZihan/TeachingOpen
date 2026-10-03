const assert = require('node:assert/strict')
const { test } = require('node:test')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const { execFileSync } = require('node:child_process')

// The same business assertions can run against another checkout or a historical
// ref. Network, attachment storage and submission are controlled in memory.
const sourceRoot = path.resolve(process.env.COURSE_RESUME_SOURCE_ROOT || path.join(__dirname, '../..'))
const sourceRef = process.env.COURSE_RESUME_SOURCE_REF || ''
function source (relative) {
  return sourceRef
    ? execFileSync('git', ['show', `${sourceRef}:web/${relative}`], { cwd: sourceRoot, encoding: 'utf8' })
    : fs.readFileSync(path.join(sourceRoot, 'web', relative), 'utf8')
}
function persistence (relative) {
  const module = { exports: {} }
  vm.runInNewContext(source(relative), { module, exports: module.exports, URLSearchParams, Blob })
  return module.exports
}
const scratch = persistence('public/scratch3/persistence.js')
const python = persistence('public/python/persistence.js')
const engines = [
  { label: 'Scratch', type: 2, extension: 'sb3', path: '/scratch3/index.html', api: scratch, acceptedTypes: ['1', '2'] },
  { label: 'ScratchJr', type: 3, extension: 'sjr', path: '/scratchjr/editor.html', api: scratch, acceptedTypes: ['3'] },
  { label: 'Python', type: 4, extension: 'py', path: '/python/index.html', api: python }
]
const unitId = 'unit & 中文 + 100%'
const savedName = '本人修改 & 100% + 中文'
const savedContent = 'student revision 1, retained after closing'
const plain = value => JSON.parse(JSON.stringify(value))

function courseEntry (engine) {
  const script = source('src/views/account/course/modules/UnitViewModal.vue')
    .match(/<script>([\s\S]*?)<\/script>/)[1]
    .replace(/^import .*$/gm, '').replace('export default', 'component =')
  const context = {
    component: null, URL, URLSearchParams,
    window: { location: { origin: 'https://teaching.test' } },
    getFileAccessHttpUrl: value => value || '',
    getAction: () => { throw new Error('Reader logging is not part of this controlled boundary') },
    getFilePrevew: value => value
  }
  vm.createContext(context); vm.runInContext(script, context)
  const template = `https://files.test/teacher-template.${engine.extension}?v=100%25&part=1`
  const instance = { unit: { id: unitId, courseWorkType: engine.type, courseWork: template, courseWork_url: template } }
  for (const [name, method] of Object.entries(context.component.methods)) instance[name] = method.bind(instance)
  const href = context.component.computed.workUrl.call(instance)
  const parsed = new URL(href, 'https://teaching.test')
  assert.equal(parsed.pathname, engine.path)
  const params = engine.api.query(parsed.search)
  assert.equal(params.unitId, unitId)
  assert.equal(params.scene, 'course')
  assert.equal(params.workId, '')
  return { href, params, template }
}

function backend (engine, existing = false) {
  const entry = courseEntry(engine)
  const id = `owned-course-${engine.type}`
  const savedUrl = `https://files.test/student-edits.${engine.extension}`
  const store = {
    entry, id, mineWorkId: existing ? id : '', serial: 0,
    files: new Map([[entry.template, 'teacher original'], [savedUrl, savedContent]]),
    registered: new Map(), works: new Map()
  }
  if (existing) store.works.set(id, {
    id, workType: engine.type, workName: savedName, workFileKey_url: savedUrl,
    courseId: unitId, additionalId: 'bound-task', departId: 'class-a'
  })
  return store
}

function editor (engine, store, params = store.entry.params) {
  const h = {
    notices: [], unitReads: [], detailReads: [], fileReads: [], opens: [], uploads: [], writes: [], saved: [],
    title: '', content: '', captureCount: 0
  }
  const options = {
    params: { ...params }, workType: engine.type, acceptedTypes: engine.acceptedTypes,
    defaultTitle: engine.label + ' 作品', defaultFile: '/default.' + engine.extension,
    notify: state => h.notices.push(plain(state)),
    unit: async id => {
      h.unitReads.push(id)
      return { id, courseWorkType: engine.type, unitName: '教师单元名称', courseWork_url: store.entry.template, mineWorkId: store.mineWorkId }
    },
    info: async id => { h.detailReads.push(id); return plain(store.works.get(id) || null) },
    title: () => h.title,
    open: async (url, title) => {
      h.fileReads.push(url)
      if (!store.files.has(url)) throw new Error('Attachment unavailable')
      h.title = title; h.content = store.files.get(url); h.opens.push({ url, title, content: h.content })
    },
    opened () {},
    text: async url => {
      h.fileReads.push(url)
      if (!store.files.has(url)) throw new Error('Attachment unavailable')
      return store.files.get(url)
    },
    apply: async (title, code) => { h.title = title; h.content = code; h.opens.push({ title, content: code }) },
    capture: async () => {
      h.captureCount++
      return { project: new Blob([h.content]), cover: new Blob(['cover']), hasCloudData: false }
    },
    upload: async (title, value) => {
      const content = engine.type === 4 ? value : await value.project.text()
      const fileId = 'registered-' + ++store.serial
      const url = `https://files.test/${fileId}.${engine.extension}`
      store.files.set(url, content); store.registered.set(fileId, url)
      h.uploads.push({ fileId, title, content })
      return engine.type === 4 ? { id: fileId } : { project: fileId, cover: 'cover-' + store.serial }
    },
    submit: async body => {
      h.writes.push(plain(body))
      const id = body.id || store.id
      store.works.set(id, {
        id, workName: body.workName, workType: body.workType, workFileKey_url: store.registered.get(body.workFile),
        courseId: body.courseId, additionalId: body.additionalId, departId: body.departId || 'class-a'
      })
      if (body.courseId === unitId) store.mineWorkId = id
      return { id }
    },
    saved: id => h.saved.push(id)
  }
  h.options = options
  h.session = engine.api.create(options)
  h.save = async (title = h.title, content = h.content) => {
    h.title = title; h.content = content
    return engine.type === 4 ? h.session.save(title, content) : h.session.save(0)
  }
  return h
}

async function cannotOverwrite (engine, h) {
  assert.equal(await h.session.load(), false)
  assert.equal(h.session.state.ready, false)
  assert.equal(h.session.state.busy, false)
  assert.equal(h.session.state.phase, 'load-error')
  assert.equal(await h.save('Must not overwrite', 'new data'), false)
  assert.equal(h.opens.length, 0)
  assert.equal(h.fileReads.length, 0)
  assert.equal(h.captureCount, 0)
  assert.equal(h.uploads.length, 0)
  assert.equal(h.writes.length, 0)
  assert.equal(h.saved.length, 0)
}

for (const engine of engines) {
  test(`${engine.label}: actual course entry opens the template only before any own work exists`, async () => {
    const store = backend(engine), h = editor(engine, store)
    assert.equal(await h.session.load(), true)
    assert.deepEqual(h.unitReads, [unitId])
    assert.deepEqual(h.detailReads, [])
    assert.deepEqual(h.fileReads, [store.entry.template])
    assert.equal(h.content, 'teacher original')
    assert.equal(h.title, '教师单元名称')
    assert.equal(h.session.state.workId, '')
  })

  test(`${engine.label}: save, close and reopen from the same real course URL keeps content, title and ID`, async () => {
    const store = backend(engine), first = editor(engine, store)
    assert.equal(await first.session.load(), true)
    assert.equal(await first.save(savedName, savedContent), true)
    assert.equal(first.writes[0].id, '')
    assert.equal(first.writes[0].courseId, unitId)
    assert.equal(first.writes[0].workScene, 'course')
    assert.equal(first.session.state.workId, store.id)

    // A new state machine represents closing the editor and returning through
    // the unchanged lesson link, which has no workId parameter.
    const second = editor(engine, store)
    assert.equal(await second.session.load(), true)
    assert.deepEqual(second.unitReads, [unitId])
    assert.deepEqual(second.detailReads, [store.id])
    assert.equal(second.title, savedName)
    assert.equal(second.content, savedContent)
    assert.equal(second.session.state.workId, store.id)
    assert.notEqual(second.fileReads[0], store.entry.template)
    assert.equal(await second.save('修改名称', 'student revision 2'), true)
    assert.equal(second.writes[0].id, store.id)
    assert.equal(second.writes[0].courseId, unitId)
    assert.equal(second.writes[0].departId, 'class-a')
    assert.equal(second.writes[0].additionalId, '')
    assert.equal(second.writes[0].workScene, 'course')
    assert.equal(store.works.size, 1)
  })

  test(`${engine.label}: a discovered work restores all record bindings rather than entrance hints`, async () => {
    const store = backend(engine, true)
    const h = editor(engine, store, { ...store.entry.params, workName: '入口旧名称', departId: 'wrong-class', additionalId: 'wrong-task' })
    assert.equal(await h.session.load(), true)
    assert.equal(h.title, savedName)
    assert.equal(h.content, savedContent)
    assert.equal(await h.save(), true)
    assert.equal(h.writes[0].id, store.id)
    assert.equal(h.writes[0].courseId, unitId)
    assert.equal(h.writes[0].departId, 'class-a')
    assert.equal(h.writes[0].additionalId, 'bound-task')
  })

  test(`${engine.label}: discovery failure blocks template fallback and upload; retry discovers own content`, async () => {
    const store = backend(engine, true), h = editor(engine, store), read = h.options.unit
    h.options.unit = async () => { throw new Error('discovery unavailable') }
    await cannotOverwrite(engine, h)
    h.options.unit = read
    assert.equal(await h.session.load(), true)
    assert.equal(h.content, savedContent)
    assert.equal(h.session.state.workId, store.id)
  })

  test(`${engine.label}: details failure keeps save disabled and a manual retry reads the same own work`, async () => {
    const store = backend(engine, true), h = editor(engine, store), read = h.options.info
    h.options.info = async () => { throw new Error('details unavailable') }
    await cannotOverwrite(engine, h)
    h.options.info = read
    assert.equal(await h.session.load(), true)
    assert.equal(h.content, savedContent)
    assert.equal(h.title, savedName)
    assert.equal(h.session.state.workId, store.id)
  })

  for (const invalid of ['missing details', 'wrong work type', 'missing own attachment', 'other unit', 'conflicting work ID']) {
    test(`${engine.label}: ${invalid} cannot fall back to the template or upload`, async () => {
      const store = backend(engine, true), h = editor(engine, store)
      const info = store.works.get(store.id)
      if (invalid === 'missing details') h.options.info = async () => null
      if (invalid === 'wrong work type') info.workType = engine.type === 4 ? 3 : 4
      if (invalid === 'missing own attachment') delete info.workFileKey_url
      if (invalid === 'other unit') info.courseId = 'different-unit'
      if (invalid === 'conflicting work ID') info.id = 'some-other-work'
      await cannotOverwrite(engine, h)
    })
  }

  for (const invalid of ['missing unit', 'wrong template type', 'missing template attachment', 'conflicting unit ID', 'malformed own work ID']) {
    test(`${engine.label}: ${invalid} blocks the first course load despite an entrance file hint`, async () => {
      const store = backend(engine), h = editor(engine, store)
      h.options.unit = async () => invalid === 'missing unit' ? null : {
        id: invalid === 'conflicting unit ID' ? 'different-unit' : unitId,
        mineWorkId: invalid === 'malformed own work ID' ? 123 : '', unitName: '教师单元名称',
        courseWorkType: invalid === 'wrong template type' ? (engine.type === 4 ? 3 : 4) : engine.type,
        courseWork_url: invalid === 'missing template attachment' ? '' : store.entry.template
      }
      await cannotOverwrite(engine, h)
    })
  }

  test(`${engine.label}: explicit workId remains authoritative and restores own record bindings`, async () => {
    const store = backend(engine, true), h = editor(engine, store, {
      workId: store.id, unitId: 'outdated-entrance-unit', workFile: store.entry.template,
      departId: 'wrong-class', additionalId: 'wrong-task'
    })
    assert.equal(await h.session.load(), true)
    assert.deepEqual(h.unitReads, [])
    assert.deepEqual(h.detailReads, [store.id])
    assert.equal(h.content, savedContent)
    assert.equal(await h.save(), true)
    assert.equal(h.writes[0].id, store.id)
    assert.equal(h.writes[0].courseId, unitId)
    assert.equal(h.writes[0].departId, 'class-a')
    assert.equal(h.writes[0].additionalId, 'bound-task')
  })

  test(`${engine.label}: deliberate course reset uses the verified template but keeps the existing work and bindings`, async () => {
    const store = backend(engine, true), h = editor(engine, store, { ...store.entry.params, resetTemplate: '1' })
    assert.equal(await h.session.load(), true)
    assert.equal(h.content, 'teacher original')
    assert.equal(h.session.state.workId, store.id)
    assert.deepEqual(h.detailReads, [store.id])
    assert.equal(await h.save('重做名称', 'deliberate replacement'), true)
    assert.equal(h.writes[0].id, store.id)
    assert.equal(h.writes[0].courseId, unitId)
    assert.equal(h.writes[0].departId, 'class-a')
    assert.equal(h.writes[0].additionalId, 'bound-task')
    const reopened = editor(engine, store)
    assert.equal(await reopened.session.load(), true)
    assert.equal(reopened.content, 'deliberate replacement')
    assert.equal(reopened.title, '重做名称')
  })

  test(`${engine.label}: explicit additional-work reset retains the task and original work ID`, async () => {
    const store = backend(engine, true)
    store.works.get(store.id).courseId = ''
    const h = editor(engine, store, {
      workId: store.id, additionalId: 'bound-task', departId: 'class-a',
      workFile: store.entry.template, resetTemplate: '1', scene: 'additional'
    })
    assert.equal(await h.session.load(), true)
    assert.deepEqual(h.unitReads, [])
    assert.deepEqual(h.detailReads, [store.id])
    assert.equal(h.content, 'teacher original')
    assert.equal(await h.save('任务重做', 'new task revision'), true)
    assert.equal(h.writes[0].id, store.id)
    assert.equal(h.writes[0].courseId, '')
    assert.equal(h.writes[0].additionalId, 'bound-task')
    assert.equal(h.writes[0].departId, 'class-a')
    assert.equal(h.writes[0].workScene, 'additional')
  })

  test(`${engine.label}: explicit reset with a conflicting course cannot overwrite the existing work`, async () => {
    const store = backend(engine, true), h = editor(engine, store, {
      workId: store.id, unitId: 'different-unit', workFile: store.entry.template, resetTemplate: '1'
    })
    await cannotOverwrite(engine, h)
  })

  test(`${engine.label}: explicit reset with a conflicting additional task cannot overwrite the existing work`, async () => {
    const store = backend(engine, true)
    store.works.get(store.id).courseId = ''
    const h = editor(engine, store, {
      workId: store.id, additionalId: 'different-task', workFile: store.entry.template, resetTemplate: '1'
    })
    await cannotOverwrite(engine, h)
  })

  test(`${engine.label}: pending discovery locks load and save until the own work has opened`, async () => {
    const store = backend(engine, true), h = editor(engine, store), read = h.options.unit
    let release
    h.options.unit = () => new Promise(resolve => { release = () => resolve(read(unitId)) })
    const loading = h.session.load()
    assert.equal(h.session.state.busy, true)
    assert.equal(h.session.state.ready, false)
    assert.equal(await h.session.load(), false)
    assert.equal(await h.save('premature upload', 'new content'), false)
    assert.equal(h.uploads.length, 0)
    release()
    assert.equal(await loading, true)
    assert.equal(h.session.state.workId, store.id)
    assert.equal(h.content, savedContent)
  })

  test(`${engine.label}: reading the saved attachment fails closed; retry preserves the own identity`, async () => {
    const store = backend(engine, true), h = editor(engine, store)
    const url = store.works.get(store.id).workFileKey_url
    store.files.delete(url)
    assert.equal(await h.session.load(), false)
    assert.equal(h.session.state.ready, false)
    assert.equal(await h.save('must not upload', 'new data'), false)
    assert.deepEqual(h.fileReads, [url])
    assert.equal(h.opens.length, 0)
    assert.equal(h.uploads.length, 0)
    assert.equal(h.session.state.workId, '')
    store.files.set(url, savedContent)
    assert.equal(await h.session.load(), true)
    assert.equal(h.content, savedContent)
    assert.equal(h.session.state.workId, store.id)
    assert.deepEqual(h.unitReads, [unitId, unitId])
  })
}

test('Python actual editor bridge discovers the course work, reads its saved file and submits the same identity', async () => {
  const engine = engines.find(value => value.type === 4), store = backend(engine, true)
  const requests = [], files = [], events = {}
  const nodes = { 'persistence-status': { dataset: {} }, 'retry-load': {} }
  const host = {
    projectName: '', code: '',
    $set: (target, key, value) => { target[key] = value }, $watch () {},
    $nextTick: callback => setTimeout(callback, 0),
    setCode: value => { host.code = value }, getCode: () => host.code,
    $refs: { codeEditor: { getCodeContent: () => host.code, $watch () {}, editor: {
      getValue: () => host.code, setValue: value => { host.code = value }, setReadOnly () {}
    } } }
  }
  const href = new URL(store.entry.href, 'https://teaching.test').href
  const context = {
    URL, URLSearchParams, Blob, FormData, AbortController, Promise, setTimeout, clearTimeout,
    PythonPersistence: python, location: { href, search: new URL(href).search },
    history: { replaceState () {} }, document: { getElementById: id => nodes[id] },
    getUserToken: () => 'synthetic-unused', uuid: () => 'synthetic-file',
    addEventListener: (name, callback) => { events[name] = callback },
    fetch: async url => {
      files.push(url)
      if (!store.files.has(url)) throw new Error('Unexpected attachment request')
      return { ok: true, status: 200, headers: { get: () => 'text/plain' }, text: async () => store.files.get(url) }
    },
    $: { ajax: request => {
      requests.push(request)
      const url = new URL(request.url, 'https://teaching.test')
      let result
      if (url.pathname.endsWith('/getUnitWorkInfo')) {
        assert.equal(url.searchParams.get('unitId'), unitId)
        result = { id: unitId, courseWorkType: 4, unitName: '教师单元名称', courseWork_url: store.entry.template, mineWorkId: store.id }
      } else if (url.pathname.endsWith('/studentWorkInfo')) {
        assert.equal(url.searchParams.get('workId'), store.id)
        result = plain(store.works.get(store.id))
      } else if (url.pathname.endsWith('/getCurrentConfig')) result = { uploadType: 'local' }
      else if (url.pathname.endsWith('/upload')) { request.success({ success: true, message: 'python/new.py' }); return }
      else if (url.pathname.endsWith('/add')) result = { id: 'registered-new', filePath: JSON.parse(request.data).filePath }
      else if (url.pathname.endsWith('/submit')) result = { id: store.id }
      else throw new Error('Unexpected API request ' + url.pathname)
      request.success({ code: 200, success: true, result })
    } }
  }
  context.window = context
  vm.createContext(context)
  vm.runInContext(source('public/python/source-loading.js'), context)
  vm.runInContext(source('public/python/editor-bridge.js'), context)
  const session = context.TeachingPython.mount(host)
  for (let attempts = 0; attempts < 40 && host.persistBusy; attempts++) await new Promise(resolve => setTimeout(resolve, 5))
  assert.equal(host.persistReady, true)
  assert.equal(host.persistBusy, false)
  assert.equal(host.projectName, savedName)
  assert.equal(host.code, savedContent)
  assert.equal(session.state.workId, store.id)
  assert.deepEqual(files, [store.works.get(store.id).workFileKey_url])
  assert.equal(requests.filter(value => value.url.includes('/getUnitWorkInfo')).length, 1)
  assert.equal(requests.filter(value => value.url.includes('/studentWorkInfo')).length, 1)
  assert.equal(await context.submitCode('学生新名称', 'print(42)'), true)
  const submitted = JSON.parse(requests.find(value => value.url.endsWith('/submit')).data)
  assert.equal(submitted.id, store.id)
  assert.equal(submitted.courseId, unitId)
  assert.equal(submitted.departId, 'class-a')
  assert.equal(submitted.additionalId, 'bound-task')
})
