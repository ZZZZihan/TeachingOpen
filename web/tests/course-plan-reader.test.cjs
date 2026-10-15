const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { resolve } = require('node:path')
const { test } = require('node:test')
const vm = require('node:vm')

const componentPath = resolve(__dirname, '../src/views/account/course/modules/CoursePlanReader.vue')
const utilityPath = resolve(__dirname, '../src/utils/coursePlan.js')

function loader ({ response, sanitize = value => value } = {}) {
  const requests = []; const sanitized = []
  const source = readFileSync(utilityPath, 'utf8')
    .replace(/^import .*$/gm, '')
    .replace(/\bexport\s+(?=(?:async\s+)?function|const|let)/g, '')
  const context = {
    URL, Blob, TextDecoder, Uint8Array, AbortController, Response, ReadableStream,
    window: { location: { origin: 'https://teaching.test', href: 'https://teaching.test/learning' } },
    MarkdownIt: require('markdown-it'),
    sanitizeRichText: html => { sanitized.push(html); return sanitize(html) },
    fetch: async (url, options = {}) => { requests.push({ url, options }); return typeof response === 'function' ? response(url, options) : response }
  }
  vm.runInNewContext(source + '\nthis.loadCoursePlan = loadCoursePlan', context)
  return { load: context.loadCoursePlan, requests, sanitized }
}

function reader () {
  const source = readFileSync(componentPath, 'utf8')
  const script = source.match(/<script>([\s\S]*?)<\/script>/)[1]
    .replace(/^import .*$/gm, '')
    .replace('export default', 'component =')
  const requests = []; const created = []; const revoked = []; const timers = new Map(); let nextTimer = 1
  const context = {
    component: null, AbortController, Blob,
    setTimeout: callback => { const id = nextTimer++; timers.set(id, callback); return id },
    clearTimeout: id => timers.delete(id),
    URL: {
      createObjectURL (value) { const url = 'blob:lesson-' + (created.length + 1); created.push({ value, url }); return url },
      revokeObjectURL (value) { revoked.push(value) }
    },
    loadCoursePlan: (url, options = {}) => new Promise((resolve, reject) => requests.push({ url, options, resolve, reject }))
  }
  vm.runInNewContext(script, context)
  const component = context.component
  const instance = { ...component.data(), url: 'https://teaching.test/api/sys/common/static/lesson.md', title: '课程教案 1' }
  for (const [name, method] of Object.entries(component.methods)) instance[name] = method.bind(instance)
  for (const [name, computed] of Object.entries(component.computed || {})) Object.defineProperty(instance, name, { get: () => computed.call(instance) })
  return { component, instance, requests, created, revoked, timers }
}

test('课程教案：读取内容在当前阅读器内显示，失败后可以重试恢复', async () => {
  const h = reader()
  const first = h.instance.load()
  assert.equal(h.instance.status, 'loading')
  assert.equal(h.requests[0].url, h.instance.url)
  h.requests[0].reject(new Error('offline'))
  await first
  assert.equal(h.instance.status, 'error')
  const retried = h.instance.load()
  assert.equal(h.instance.status, 'loading')
  const document = { type: 'html', content: '<h1>观察语音识别</h1><p>课程内容</p>' }
  h.requests[1].resolve(document)
  await retried
  assert.equal(h.instance.status, 'ready')
  assert.equal(h.instance.document, document)
  assert.equal(h.created.length, 0)
})

test('课程教案：切换文件取消旧请求，迟到成功不会覆盖新文件', async () => {
  const h = reader()
  const old = h.instance.load()
  h.instance.url = 'https://teaching.test/api/sys/common/static/second.md'
  const current = h.instance.load()
  assert.equal(h.requests[0].options.signal.aborted, true)
  const second = { type: 'text', content: '第二份教案' }
  h.requests[1].resolve(second)
  await current
  h.requests[0].resolve({ type: 'text', content: '旧教案' })
  await old
  assert.equal(h.instance.document, second)
  assert.equal(h.instance.status, 'ready')
})

test('课程教案：旧请求失败不能把新教案的成功状态改成错误', async () => {
  const h = reader()
  const old = h.instance.load()
  const current = h.instance.load()
  const document = { type: 'text', content: '最新教案' }
  h.requests[1].resolve(document)
  await current
  h.requests[0].reject(new Error('old request failed'))
  await old
  assert.equal(h.instance.document, document)
  assert.equal(h.instance.status, 'ready')
})

test('课程教案：关闭阅读器取消请求，迟到响应不会重新显示内容或创建对象地址', async () => {
  const h = reader()
  const pending = h.instance.load()
  h.component.beforeDestroy.call(h.instance)
  assert.equal(h.requests[0].options.signal.aborted, true)
  h.requests[0].resolve({ type: 'pdf', content: new Blob(['%PDF-1.4'], { type: 'application/pdf' }) })
  await pending
  assert.equal(h.instance.document, null)
  assert.equal(h.created.length, 0)
  assert.equal(h.timers.size, 0)
})

test('课程教案：超时终止请求并提供重试，旧超时请求的迟到响应不恢复正文', async () => {
  const h = reader()
  const timedOut = h.instance.load()
  h.timers.values().next().value()
  assert.equal(h.instance.status, 'error')
  assert.match(h.instance.error, /超时/)
  assert.equal(h.requests[0].options.signal.aborted, true)
  const retried = h.instance.load()
  const document = { type: 'text', content: '重试后读到的教案' }
  h.requests[1].resolve(document)
  await retried
  h.requests[0].resolve({ type: 'text', content: '超时请求的旧教案' })
  await timedOut
  assert.equal(h.instance.status, 'ready')
  assert.equal(h.instance.document, document)
  assert.equal(h.timers.size, 0)
})

test('课程教案：PDF或图片切换、重试与关闭时释放已创建的对象地址', async () => {
  const h = reader()
  const pdf = h.instance.load()
  h.requests[0].resolve({ type: 'pdf', content: new Blob(['%PDF-1.4'], { type: 'application/pdf' }) })
  await pdf
  assert.equal(h.instance.objectUrl, 'blob:lesson-1')
  assert.equal(h.created.length, 1)
  h.instance.url = 'https://teaching.test/api/sys/common/static/illustration.png'
  const image = h.instance.load()
  assert.deepEqual(h.revoked, ['blob:lesson-1'])
  h.requests[1].resolve({ type: 'image', content: new Blob(['PNG'], { type: 'image/png' }) })
  await image
  assert.equal(h.instance.objectUrl, 'blob:lesson-2')
  h.component.beforeDestroy.call(h.instance)
  assert.deepEqual(h.revoked, ['blob:lesson-1', 'blob:lesson-2'])
  assert.equal(h.instance.objectUrl, '')
})

test('课程教案：Markdown附件响应在内存中渲染标题、表格和代码，不受下载响应头影响', async () => {
  const markdown = '# 观察语音识别\n\n| 阶段 | 说明 |\n| --- | --- |\n| 输入 | 声音 |\n\n```python\nprint("课堂")\n```\n'
  const h = loader({ response: new Response(markdown, { headers: { 'Content-Type': 'application/octet-stream', 'Content-Disposition': 'attachment; filename="lesson.md"' } }) })
  const doc = await h.load('https://teaching.test/api/sys/common/static/lesson.md')
  assert.equal(doc.type, 'html')
  assert.match(doc.content, /<h1>观察语音识别<\/h1>/)
  assert.match(doc.content, /<table>[\s\S]*<td>声音<\/td>/)
  assert.match(doc.content, /<code class="language-python">/)
  assert.match(doc.content, /print\(/)
  assert.equal(h.sanitized.length, 1)
  assert.equal(h.requests.length, 1)
})

test('课程教案：Markdown原始HTML不执行，file图片被拒绝而正常网页链接保留', async () => {
  const markdown = '<script>alert(1)</script>\n\n[Python](https://www.python.org)![Attachment.tiff](file:///Attachment.tiff)\n\n[危险](javascript:alert(1))'
  const h = loader({ response: new Response(markdown) })
  const doc = await h.load('https://teaching.test/lesson.markdown')
  assert.doesNotMatch(doc.content, /<script\b|<img[^>]+file:|<a[^>]+javascript:/i)
  assert.match(doc.content, /href="https:\/\/www.python.org\/?"/)
  assert.match(doc.content, /&lt;script&gt;/)
})

test('课程教案：同源读取带登录会话，外部文件读取不传用户凭据', async () => {
  const h = loader({ response: () => new Response('教案正文') })
  const controller = new AbortController()
  await h.load('https://teaching.test/api/sys/common/static/lesson.txt', { signal: controller.signal })
  await h.load('https://files.example/lesson.txt')
  assert.ok(['same-origin', 'include'].includes(h.requests[0].options.credentials))
  assert.equal(h.requests[0].options.signal, controller.signal)
  assert.equal(h.requests[1].options.credentials, 'omit')
  assert.equal(h.requests[1].options.headers && h.requests[1].options.headers['X-Access-Token'], undefined)
})

test('课程教案：文本保留原文，HTML显示净化后的内容', async () => {
  const text = '<script>课堂中的代码示例</script>\n第二行'
  const plain = loader({ response: new Response(text) })
  const textDocument = await plain.load('https://teaching.test/lesson.txt')
  assert.equal(textDocument.type, 'text')
  assert.equal(textDocument.content, text)
  assert.equal(plain.sanitized.length, 0)
  const html = loader({ response: new Response('<p onclick="evil()">课程正文</p><script>evil()</script>'), sanitize: () => '<p>课程正文</p>' })
  const document = await html.load('https://teaching.test/lesson.html')
  assert.equal(document.type, 'html')
  assert.equal(document.content, '<p>课程正文</p>')
  assert.equal(html.sanitized.length, 1)
})

test('课程教案：拒绝非法协议、Word格式与HTTP失败，不把错误页作为正文', async () => {
  for (const url of ['javascript:alert(1)', 'file:///lesson.md', 'data:text/plain,lesson', 'https://teaching.test/lesson.docx', 'https://user:password@teaching.test/lesson.md']) {
    const h = loader({ response: () => new Response('not a readable lesson') })
    await assert.rejects(() => h.load(url))
  }
  const failed = loader({ response: new Response('<html>login</html>', { status: 403 }) })
  await assert.rejects(() => failed.load('https://teaching.test/lesson.md'))
  assert.equal(failed.sanitized.length, 0)
  for (const mime of ['application/json', 'text/html; charset=utf-8']) {
    const expired = loader({ response: new Response('<html>登录页或错误信息</html>', { headers: { 'Content-Type': mime } }) })
    await assert.rejects(() => expired.load('https://teaching.test/lesson.md'))
    assert.equal(expired.sanitized.length, 0)
  }
})

test('课程教案：响应长度与流中实际长度超限均拒绝，避免读取巨大附件', async () => {
  const advertised = loader({ response: new Response('small body', { headers: { 'Content-Length': String(10 * 1024 * 1024 + 1) } }) })
  await assert.rejects(() => advertised.load('https://teaching.test/lesson.md'))
  let cancelled = false
  const body = new ReadableStream({
    start (controller) { controller.enqueue(new Uint8Array(10 * 1024 * 1024 + 1)) },
    cancel () { cancelled = true }
  })
  const streamed = loader({ response: new Response(body) })
  await assert.rejects(() => streamed.load('https://teaching.test/lesson.md'))
  assert.equal(cancelled, true)
})

test('课程教案：PDF和图片使用内存Blob，读取器负责后续对象地址生命周期', async () => {
  for (const [name, mime, type] of [['lesson.pdf', 'application/pdf', 'pdf'], ['lesson.png', 'image/png', 'image']]) {
    const h = loader({ response: new Response(type === 'pdf' ? '%PDF-1.4' : 'PNG', { headers: { 'Content-Type': mime } }) })
    const doc = await h.load('https://teaching.test/' + name)
    assert.equal(doc.type, type)
    assert.ok(doc.content instanceof Blob)
    assert.equal(doc.content.type, mime)
  }
})
