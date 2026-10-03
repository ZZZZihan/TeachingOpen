const assert = require('node:assert/strict')
const { test } = require('node:test')
const vm = require('node:vm')
const crypto = require('node:crypto')
const { environment, page, source, flush } = require('./python-source-loading/harness.cjs')

function button (host) {
  function find (node) {
    if (!node || typeof node !== 'object') return null
    if (node.data?.on?.click === host.instance.runit) return node
    for (const child of node.children || []) { const match = find(child); if (match) return match }
    return null
  }
  const result = find(host.render())
  assert.ok(result, 'find the actual bundled Run button')
  return result
}
function blocked (h) {
  const host = h.actual()
  assert.equal(button(host).data.attrs.disabled, true)
  assert.equal(host.instance.runit(), undefined)
  assert.equal(h.frames.length, 0, 'actual guarded runit creates no execution frame')
}
async function ready (h, text = 'print 42\n') {
  await flush()
  h.response(h.requests.at(-1), text)
  await h.pump(() => h.phase() === 'ready')
}
function reading () { const h = environment(); h.load('web/public/python/source-loading.js'); return h }

for (const name of ['index', 'player']) {
  for (const editorType of ['ace', 'codemirror']) {
    test(name + ' ' + editorType + ': one actual entry performs one GET, waits for raw editor, then enables Worker Run', async () => {
      const url = '/fixtures/a%2Fb.py?revision=1&label=a+b&next=/child?x=1#fragment+%26'
      const h = page(name, { editorType, href: '/python/' + name + '.html?' + new URLSearchParams({ queryEncoding: 'uri', url }) })
      const host = h.actual(), key = editorType === 'ace' ? 'editor' : 'coder'
      assert.deepEqual(h.bundles, [name === 'index' ? 'app' : 'appPlayer'])
      assert.ok(h.scripts.indexOf('./source-loading.js') < h.scripts.indexOf('./static/js/' + h.bundles[0] + '.js'))
      delete host.child[key]
      h.start(); await flush()
      assert.equal(h.requests.length, 1)
      assert.equal(h.requests[0].url, new URL(url, h.context.location.href).href)
      assert.equal(h.requests[0].transport, 'fetch')
      assert.equal(h.requests[0].settings.method, 'GET')
      assert.equal(h.requests[0].settings.credentials, 'same-origin')
      assert.equal(h.requests[0].settings.headers, undefined, 'file GET never receives API headers')
      blocked(h)
      h.response(h.requests[0], 'print 42\r\n'); await flush(); h.clock.advance(300); await flush()
      assert.equal(h.phase(), 'loading'); blocked(h)
      host.child[key] = host.raw
      await h.pump(() => h.phase() === 'ready')
      assert.equal(host.raw.getValue(), 'print 42\n')
      assert.equal(host.child.getCodeContent(), 'print 42\n'); assert.equal(host.instance.code, 'print 42\n')
      assert.equal(host.raw.readOnly, name === 'player', 'editor unlocks; preview preserves inherited readonly')
      assert.equal(button(host).data.attrs.disabled, false)
      const id = host.instance.runit(), frame = h.nodes.get('mycanvas').querySelector('iframe')
      assert.ok(id); assert.equal(frame.getAttribute('sandbox'), 'allow-scripts')
      frame.dispatch('load')
      assert.equal(h.posted[0].data.code, 'print 42\n', 'real coordinator receives the loaded bytes')
      assert.equal(h.requests.length, 1)
    })
  }

  test(name + ': 404 and network errors keep Run disabled, expose retry, and retry makes exactly one further GET', async () => {
    for (const kind of ['404', 'network']) {
      const h = page(name), host = h.actual()
      h.start(); await flush()
      if (kind === '404') h.response(h.requests[0], 'missing', 404)
      else h.requests[0].reject(new TypeError('controlled offline'))
      await h.pump(() => h.phase() === 'load-error')
      assert.match(h.nodes.get('persistence-status').textContent, kind === '404' ? /404/ : /网络/)
      assert.equal(h.nodes.get('retry-load').hidden, false); blocked(h)
      h.nodes.get('retry-load').dispatch('click'); h.nodes.get('retry-load').dispatch('click'); await flush()
      assert.equal(h.requests.length, 2, 'retry is also single-flight')
      assert.equal(h.requests[1].url, h.requests[0].url)
      await ready(h, 'print 7\n')
      assert.equal(host.raw.getValue(), 'print 7\n')
      assert.equal(h.nodes.get('retry-load').hidden, true)
      assert.equal(button(host).data.attrs.disabled, false)
    }
  })

  test(name + ': loading changes are preserved, including a late response and a change during apply nextTick', async () => {
    for (const at of ['before-response', 'after-write']) {
      const h = page(name); h.start(); await flush()
      const host = h.actual()
      if (at === 'before-response') {
        host.raw.setValue('print "manual edit"'); if (name === 'index') host.instance.projectName = 'Manual title'
        h.response(h.requests[0], 'print "server"')
      } else {
        host.instance.$nextTick = callback => h.clock.setTimeout(() => { host.raw.setValue('print "manual edit"'); callback() }, 0)
        h.response(h.requests[0], 'print "server"')
      }
      await h.pump(() => h.phase() === 'load-error')
      assert.equal(host.raw.getValue(), 'print "manual edit"')
      assert.match(h.nodes.get('persistence-status').textContent, /已修改|发生变化/); blocked(h)
      h.clock.advance(350); assert.equal(host.raw.getValue(), 'print "manual edit"')
      if (at === 'before-response' && name === 'index') assert.equal(host.instance.projectName, 'Manual title')
    }
  })

  test(name + ': missing raw editor times out application without becoming runnable', async () => {
    const h = page(name), host = h.actual()
    delete host.child.editor; h.start(); await flush(); h.response(h.requests[0], 'print 42\n')
    await h.pump(() => h.phase() === 'load-error')
    assert.match(h.nodes.get('persistence-status').textContent, /编辑器尚未准备好/)
    assert.equal(host.instance.code, ''); blocked(h)
  })
}

test('player missing/empty/bad URL reports an actionable error without fetching a template', async () => {
  for (const query of ['', '?url=', '?url=&url=/ignored.py', '#?url=/fragment.py', '?queryEncoding=uri&url=javascript%3Aalert(1)', '?queryEncoding=uri&url=https%3A%2F%2Fu%3Ap%40files.test%2Fseed.py']) {
    const h = page('player', { href: '/python/player.html' + query }); h.start()
    await h.pump(() => h.phase() === 'load-error')
    assert.equal(h.requests.length, 0); blocked(h)
    assert.match(h.nodes.get('persistence-status').textContent, /没有指定程序文件|地址不可用/)
    assert.equal(h.nodes.get('retry-load').hidden, false)
  }
})

test('editor without source loads its established template once and repeated mount is idempotent', async () => {
  const h = page('index', { href: '/python/index.html' }); h.start(); await flush()
  const one = h.context.TeachingPython.mount(h.actual().instance), two = h.context.TeachingPython.mount(h.actual().instance)
  assert.equal(one, two); assert.equal(h.requests.length, 1)
  assert.equal(h.requests[0].url, 'http://fixture.test/python/static/defaultPython.py')
  await ready(h); assert.equal(h.requests.length, 1)
})

test('preview mount is idempotent both during and after successful load', async () => {
  const h = page('player'); h.start(); await flush()
  const api = h.context.PythonSourceLoading, host = h.actual().instance
  const first = api.mountPreview(host); assert.equal(first, api.mountPreview(host))
  assert.equal(h.requests.length, 1); await ready(h)
  assert.equal(api.mountPreview(host), first); assert.equal(h.requests.length, 1)
})

for (const editorType of ['ace', 'codemirror']) {
  for (const text of ['', 'print 42\n']) {
    test(editorType + ': empty/same-code application leaves no delayed setter able to overwrite post-ready edits (' + JSON.stringify(text) + ')', async () => {
      const h = page('index', { editorType, initialCode: text }); h.start(); await ready(h, text)
      const host = h.actual()
      assert.equal(host.raw.readOnly, false); assert.equal(host.raw.getValue(), text)
      host.raw.setValue('print "after ready"')
      h.clock.advance(350); await flush()
      assert.equal(host.raw.getValue(), 'print "after ready"')
      assert.equal(host.instance.getCode(), 'print "after ready"')
      // Exercise retry with the same bytes as current contents: no old wrapper timer may remain.
      const session = h.context.TeachingPython.mount(host.instance)
      session.load(); await flush(); h.response(h.requests.at(-1), 'print "after ready"')
      await h.pump(() => h.phase() === 'ready')
      host.raw.setValue('print "after retry"'); h.clock.advance(350); await flush()
      assert.equal(host.raw.getValue(), 'print "after retry"')
    })
  }
}

test('both actual CodeMirror wrapper setters apply synchronously and cannot overwrite later edits at 300ms', () => {
  for (const bundle of ['app', 'appPlayer']) {
    const text = source('web/public/python/static/js/' + bundle + '.js')
    const methods = [...text.matchAll(/setCodeContent:function\(t\)\{[^}]*\}/g)].filter(match => match[0].includes('.coder'))
    assert.equal(methods.length, 1)
    const h = environment(); vm.runInContext('setter=(' + methods[0][0].slice('setCodeContent:'.length) + ')', h.context)
    let value = ''
    const editor = { code: '', coder: { setValue (v) { value = v } } }
    h.context.setter.call(editor, 'print 42'); assert.equal(value, 'print 42')
    value = 'manual edit'; h.clock.advance(350); assert.equal(value, 'manual edit')
    h.context.setter.call(editor, ''); assert.equal(value, ''); assert.equal(editor.code, '')
  }
})

test('helper rejects bad addresses and typed content failures while accepting empty Python text', async () => {
  for (const value of [undefined, '', '  ', 'javascript:alert(1)', 'file:///private/x', 'https://u:p@files.test/x.py', '/x\n.py']) {
    const h = reading(); await assert.rejects(h.context.PythonSourceLoading.read(value), /地址不可用/); assert.equal(h.requests.length, 0)
  }
  for (const [status, mime, message] of [[404, 'text/plain', /404/], [401, 'text/plain', /权限/], [403, 'text/plain', /权限/], [503, 'text/plain', /503/], [200, 'text/html', /不是程序文件/], [200, 'application/json', /不是程序文件/]]) {
    const h = reading(), promise = h.context.PythonSourceLoading.read('/seed.py'), assertion = assert.rejects(promise, message)
    await flush(); h.response(h.requests[0], '<fixture>', status, mime); await assertion
  }
  const h = reading(), promise = h.context.PythonSourceLoading.read('/empty.py')
  await flush(); h.response(h.requests[0], ''); assert.equal(await promise, '')
  const large = reading(), result = large.context.PythonSourceLoading.read('/large.py'), assertion = assert.rejects(result, /10 MB/)
  await flush(); large.response(large.requests[0], 'x'.repeat(10 * 1024 * 1024 + 1)); await assertion
})

test('15s timeout aborts one native fetch, keeps Run blocked, and ignores the late response before successful retry', async () => {
  const h = page('player'); h.start(); await flush(); const request = h.requests[0]
  h.clock.advance(14999); assert.equal(h.phase(), 'loading'); assert.equal(request.settings.signal.aborted, false); blocked(h)
  h.clock.advance(1); await h.pump(() => h.phase() === 'load-error')
  assert.equal(request.settings.signal.aborted, true); assert.match(h.nodes.get('persistence-status').textContent, /超时/)
  h.response(request, 'print "late"'); await flush(); assert.equal(h.actual().raw.getValue(), '')
  h.nodes.get('retry-load').dispatch('click'); await ready(h, 'print "retry"')
  assert.equal(h.requests.length, 2); assert.equal(h.actual().raw.getValue(), 'print "retry"')
})

test('workId retains metadata-first single source GET; save uploads current raw bytes and reopening keeps the same identity', async () => {
  const h = page('index', { href: '/python/index.html?workId=seed-work&queryEncoding=uri&url=%2Fignored.py&workFile=%2Falso-ignored.py&workName=Ignored' })
  h.start(); await flush()
  assert.equal(h.writes.filter(value => value.url.includes('studentWorkInfo')).length, 1)
  assert.equal(h.requests.length, 1); assert.equal(h.requests[0].url, 'http://fixture.test/fixtures/seed.py?revision=1&label=a+b')
  await ready(h)
  const host = h.actual(); assert.equal(host.instance.projectName, 'Synthetic saved title')
  host.raw.setValue('print 99\n'); host.instance.projectName = 'Revised title'; host.watches.projectName()
  const session = h.context.TeachingPython.mount(host.instance)
  assert.equal(await session.save(host.instance.projectName, host.instance.getCode()), true)
  const upload = h.writes.find(value => value.url.endsWith('/upload'))
  assert.equal(await upload.body.get('file').text(), 'print 99\n')
  const submission = h.writes.find(value => value.url.endsWith('/submit')).body
  assert.equal(submission.id, 'seed-work'); assert.equal(submission.workName, 'Revised title'); assert.equal(submission.workFile, 'file-1')
  const saved = new URL(h.context.location.href)
  assert.equal(saved.searchParams.get('workId'), 'seed-work'); assert.equal(saved.searchParams.get('queryEncoding'), 'uri')
  for (const key of ['url', 'workFile', 'resetTemplate', 'workName']) assert.equal(saved.searchParams.has(key), false)
  const reopened = page('index', { href: saved.href, work: { workName: submission.workName, workFileKey_url: '/fixtures/revised.py' } })
  reopened.start(); await ready(reopened, await upload.body.get('file').text())
  assert.equal(reopened.actual().raw.getValue(), 'print 99\n'); assert.equal(reopened.actual().instance.projectName, 'Revised title')
  assert.equal(reopened.writes.filter(value => value.url.includes('studentWorkInfo')).length, 1); assert.equal(reopened.requests.length, 1)
})

test('source substitutions reverse to the untouched PR52 bundle hashes before all historical patch layers', () => {
  const hash = value => crypto.createHash('sha256').update(value).digest('hex')
  const chain = ['./python-source-loading/vendor-patch.json', './python-execution-frame/vendor-patch.json', './python-preview-url/vendor-patch.json', './python-output-preview/vendor-patch.json'].map(value => require(value))
  for (const file of chain[0].files) {
    let text = source(file.path)
    for (const patch of chain) {
      const entry = patch.files.find(value => value.path === file.path)
      assert.ok(entry, 'every historical layer records the bundle')
      if (entry.after_sha256) assert.equal(hash(text), entry.after_sha256)
      for (const { before, after } of entry.replacements) { assert.equal(text.split(after).length - 1, 1); text = text.replace(after, before) }
      assert.equal(hash(text), entry.before_sha256)
    }
  }
})
