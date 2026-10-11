#!/usr/bin/env node
// Real Chrome + actual Vue/Ant Design components. No production server or credentials.
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const os = require('node:os')
const http = require('node:http')
const cp = require('node:child_process')
const crypto = require('node:crypto')
const build = require('./build.cjs')

const root = path.resolve(process.env.M05_SOURCE_ROOT || path.join(__dirname, '../../..'))
const out = path.resolve(process.argv[2] || path.join(root, 'output/playwright/additional-work'))
const before = process.argv[3] || 'a3f4e10ceafcbe405093a3abe06a20225a17d3f6'
const chrome = process.env.CHROME_BIN || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'teachingopen-m05-browser-'))
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms))
const report = {
  generatedAt: new Date().toISOString(), baseline: before,
  candidate: cp.execFileSync('git', ['rev-parse', 'HEAD'], { cwd: root, encoding: 'utf8' }).trim(),
  frontendChanges: cp.execFileSync('git', ['status', '--porcelain', '--', 'web/src'], { cwd: root, encoding: 'utf8' }).trim(),
  boundary: 'Actual AdditionalWorkModal, recovery mixin, JUpload, JModal, dictionary and department components; synthetic Axios API, local files, no authenticated backend or database. Legacy comparison replaces only AdditionalWorkModal at the pinned baseline.',
  limitations: ['UI guards do not provide backend create idempotency. A connection reset before response headers can cause Chrome to replay a POST; report records the observed count.', 'No production requests, full-app authentication/session test, or backend create-idempotency claim.'],
  sourceHashes: {}, scenarios: [], blockedExternalRequests: [], unexpectedRequests: []
}
const state = { mode: 'success', writes: [], uploads: [], registrations: [], pending: null }
const files = {
  'cover.png': Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=', 'base64'),
  'instructions.txt': Buffer.from('Synthetic assignment instructions. No personal data.\n'),
  'starter.txt': Buffer.from('Synthetic starter attachment.\n')
}
let browser, server, cdp, target

function json (res, status, body) {
  res.writeHead(status, { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store' })
  res.end(JSON.stringify(body))
}

function fixtureServer () {
  return http.createServer(async (req, res) => {
    const url = new URL(req.url, 'http://127.0.0.1')
    const chunks = []
    for await (const chunk of req) chunks.push(chunk)
    const body = Buffer.concat(chunks)
    if (url.pathname === '/fixture/departments') return json(res, 200, { success: true, result: [{ id: 'class-a', key: 'class-a', title: '合成一班', departName: '合成一班', orgCategory: 3, isLeaf: true, children: [] }] })
    if (url.pathname === '/sys/common/upload' && req.method === 'POST') {
      const match = body.toString('latin1').match(/filename="([^"]+)"/)
      const name = match && match[1]
      assert.ok(files[name], `Unexpected synthetic upload ${name}`)
      state.uploads.push(name)
      return json(res, 200, { success: true, message: `attachments/${name}` })
    }
    if (url.pathname === '/system/sysFile/add' && req.method === 'POST') {
      const data = JSON.parse(body)
      assert.ok(Object.keys(files).some(name => data.filePath === `attachments/${name}`))
      state.registrations.push(data)
      return json(res, 200, { success: true, result: { ...data, id: `synthetic-file-${state.registrations.length}` } })
    }
    if (url.pathname === '/teaching/teachingAdditionalWork/add' && req.method === 'POST') {
      state.writes.push(JSON.parse(body))
      if (state.mode === 'forbidden') return json(res, 403, { success: false, message: 'Synthetic forbidden response' })
      if (state.mode === 'disconnect') return req.socket.destroy()
      if (state.mode === 'truncated') {
        res.writeHead(200, { 'content-type': 'application/json', 'content-length': '200' })
        res.write('{"success":')
        setTimeout(() => res.destroy(), 50)
        return
      }
      if (state.mode === 'slow') { state.pending = res; return }
      return json(res, 200, { success: true, result: { id: 'synthetic-work' }, message: '保存成功' })
    }
    if (url.pathname.startsWith('/attachments/')) {
      const name = url.pathname.slice('/attachments/'.length)
      if (files[name]) { res.writeHead(200, { 'content-type': name.endsWith('.png') ? 'image/png' : 'text/plain' }); return res.end(files[name]) }
    }
    const match = url.pathname.match(/^\/(fixed|legacy)\/(preview\.js|index\.html)?$/)
    if (match && req.method === 'GET') {
      res.writeHead(200, { 'content-type': match[2] === 'preview.js' ? 'application/javascript' : 'text/html; charset=utf-8' })
      return res.end(fs.readFileSync(path.join(temp, match[1], match[2] || 'index.html')))
    }
    if (url.pathname === '/favicon.ico') { res.writeHead(204); return res.end() }
    report.unexpectedRequests.push({ method: req.method, path: url.pathname })
    return json(res, 404, { success: false })
  })
}

// Chrome's debugging pipe avoids opening a debugging listener on the host.
function debuggingPipe (child) {
  let nextId = 0, buffer = ''
  const pending = new Map()
  const listeners = []
  child.stdio[4].setEncoding('utf8')
  child.stdio[4].on('data', data => {
    buffer += data
    let boundary
    while ((boundary = buffer.indexOf('\0')) !== -1) {
      const raw = buffer.slice(0, boundary)
      buffer = buffer.slice(boundary + 1)
      if (!raw) continue
      const message = JSON.parse(raw)
      if (message.id) {
        const waiter = pending.get(message.id)
        if (waiter) { pending.delete(message.id); clearTimeout(waiter.timer); message.error ? waiter.reject(new Error(JSON.stringify(message.error))) : waiter.resolve(message.result) }
      } else for (const listener of listeners) listener(message)
    }
  })
  child.once('exit', (code, signal) => {
    for (const waiter of pending.values()) { clearTimeout(waiter.timer); waiter.reject(new Error(`Chrome exited: ${code}/${signal}`)) }
    pending.clear()
  })
  return {
    on: listener => listeners.push(listener),
    send: (method, params = {}, sessionId) => new Promise((resolve, reject) => {
      const id = ++nextId
      const timer = setTimeout(() => { pending.delete(id); reject(new Error(`CDP timed out: ${method}`)) }, 15000)
      pending.set(id, { resolve, reject, timer })
      child.stdio[3].write(JSON.stringify({ id, method, params, ...(sessionId ? { sessionId } : {}) }) + '\0')
    })
  }
}

async function evaluate (expression) {
  const result = await cdp.send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true }, target.sessionId)
  if (result.exceptionDetails) throw new Error(JSON.stringify(result.exceptionDetails))
  return result.result.value
}
async function until (expression, label) {
  for (let i = 0; i < 200; i++) { if (await evaluate(expression)) return; await sleep(50) }
  throw new Error(`Browser condition timed out: ${label}`)
}
const modal = 'window.fixtureApp.$refs.work'
async function capture (name) {
  // Let normal upload toasts expire so narrow-screen screenshots show the title and alert.
  if (!name.endsWith('-success')) {
    for (let i = 0; i < 90 && await evaluate('!!document.querySelector(".ant-message-notice")'); i++) await sleep(50)
  }
  await sleep(180)
  const screenshot = await cdp.send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false }, target.sessionId)
  fs.writeFileSync(path.join(out, name + '.png'), Buffer.from(screenshot.data, 'base64'))
  return name + '.png'
}
async function formState () {
  return evaluate(`({ visible: ${modal}.visible, busy: ${modal}.confirmLoading, values: ${modal}.form.getFieldsValue(), saved: window.fixtureApp.saved, error: ${modal}.saveError || '', alertFocused: !!(document.activeElement && document.activeElement.getAttribute('role') === 'alert'), filenames: Array.from(document.querySelectorAll('.ant-upload-list-item-name')).map(e => e.title || e.textContent) })`)
}

async function openForm (variant, viewport) {
  state.writes = []; state.uploads = []; state.registrations = []
  const created = await cdp.send('Target.createTarget', { url: 'about:blank' })
  target = { targetId: created.targetId, ...(await cdp.send('Target.attachToTarget', { targetId: created.targetId, flatten: true })) }
  for (const method of ['Page.enable', 'Runtime.enable']) await cdp.send(method, {}, target.sessionId)
  await cdp.send('Emulation.setDeviceMetricsOverride', { width: viewport.width, height: viewport.height, deviceScaleFactor: 1, mobile: false }, target.sessionId)
  await cdp.send('Fetch.enable', { patterns: [{ urlPattern: '*' }] }, target.sessionId)
  await cdp.send('Page.navigate', { url: `http://127.0.0.1:${server.address().port}/${variant}/` }, target.sessionId)
  await until('!!window.fixtureApp', 'Vue mounted')
  await evaluate('document.querySelector("#open").click()')
  await until(`!!document.querySelector('input[placeholder="请输入作业名"]') && ${modal}.form.getFieldValue('workDept') === 'class-a'`, 'form opened')
  const fields = [['input[placeholder="请输入作业名"]', '天气观察 · 合成附加作业'], ['textarea[placeholder="请输入作业描述"]', '保留这段课堂说明：观察云、风和温度。\n失败后继续编辑，附件仍可用。']]
  await evaluate(`(() => {
    for (const [selector, value] of ${JSON.stringify(fields)}) {
      const input = document.querySelector(selector); input.value = value; input.dispatchEvent(new Event('input', { bubbles: true })); input.dispatchEvent(new Event('change', { bubbles: true }));
    }
  })()`)
  const document = await cdp.send('DOM.getDocument', {}, target.sessionId)
  const inputs = await cdp.send('DOM.querySelectorAll', { nodeId: document.root.nodeId, selector: '.j-upload input[type=file]' }, target.sessionId)
  assert.equal(inputs.nodeIds.length, 3)
  for (let index = 0; index < inputs.nodeIds.length; index++) {
    await cdp.send('DOM.setFileInputFiles', { nodeId: inputs.nodeIds[index], files: [path.join(temp, Object.keys(files)[index])] }, target.sessionId)
  }
  await until(`${modal}.form.getFieldValue('workCover') === 'attachments/cover.png' && ${modal}.form.getFieldValue('workDocumentUrl') === 'attachments/instructions.txt' && ${modal}.form.getFieldValue('workUrl') === 'attachments/starter.txt' && !document.querySelector('.ant-upload-list-item-uploading')`, 'three actual uploads registered')
  assert.equal(state.uploads.length, 3)
  assert.equal(state.registrations.length, 3)
  await sleep(400) // Ant Design briefly keeps entering/leaving upload rows during its transition.
  return formState()
}

async function save () {
  await evaluate('document.querySelector(".j-modal-box .ant-modal-footer .ant-btn-primary").click()')
}

async function rejected (variant, mode, viewport) {
  state.mode = mode
  const initial = await openForm(variant, viewport)
  const name = `${variant}-${mode}-${viewport.width}x${viewport.height}`
  const screenshots = [await capture(name + '-before-save')]
  await save()
  await until(`${modal}.confirmLoading === false && ${variant === 'legacy' ? `${modal}.visible === false` : `${modal}.saveError.length > 0`}`, 'failed save settled')
  const after = await formState()
  const failureRequestCount = state.writes.length
  // Chrome can replay a POST when a pooled connection closes before response headers.
  // UI guards do not provide backend create idempotency; retain this measured boundary.
  if (mode === 'disconnect') assert.ok(failureRequestCount >= 1)
  else assert.equal(failureRequestCount, 1)
  assert.equal(after.saved, 0)
  if (variant === 'fixed') {
    assert.equal(after.visible, true)
    assert.deepEqual(after.values, initial.values)
    assert.deepEqual(after.filenames, initial.filenames)
    assert.equal(after.alertFocused, true)
    assert.ok(after.error.includes('填写内容已保留'))
    screenshots.push(await capture(name + '-after-failure'))
    if (viewport.width < 600) {
      await evaluate('document.querySelector(".ant-modal-wrap").scrollTop = 10000')
      screenshots.push(await capture(name + '-after-failure-attachments'))
    }
    state.mode = 'success'
    await save()
    await until(`${modal}.visible === false && window.fixtureApp.saved === 1`, 'intentional retry succeeded')
    assert.equal(state.writes.length, failureRequestCount + 1)
    assert.deepEqual(state.writes[state.writes.length - 1], state.writes[0])
    screenshots.push(await capture(name + '-success'))
  } else {
    assert.equal(after.visible, false)
    screenshots.push(await capture(name + '-after-failure'))
    await evaluate('document.querySelector("#open").click()')
    await until(`${modal}.visible === true`, 'legacy reopened')
    const reopened = await formState()
    assert.ok(!reopened.values.workName && !reopened.values.workDocumentUrl && !reopened.values.workUrl)
    screenshots.push(await capture(name + '-reopened-empty'))
  }
  report.scenarios.push({ name, viewport, initial, after, failedSaveClicks: 1, failureRequestCount, requests: state.writes.length, uploads: state.uploads.length, registrations: state.registrations.length, screenshots, passed: true })
  await cdp.send('Target.closeTarget', { targetId: target.targetId })
}

async function slowSave () {
  state.mode = 'slow'
  const viewport = { width: 1440, height: 1100 }
  const initial = await openForm('fixed', viewport)
  await save()
  await until(`${modal}.confirmLoading === true && !!document.querySelector('[inert]')`, 'pending request locked form')
  for (let i = 0; i < 100 && !state.pending; i++) await sleep(20)
  assert.ok(state.pending)
  const locked = await evaluate(`({ busy: ${modal}.confirmLoading, disabled: Array.from(document.querySelectorAll('.j-modal-box .ant-modal-footer button')).every(e => e.disabled), closeCount: document.querySelectorAll('.j-modal-box .ant-modal-content > .ant-modal-close').length, uploadDisabled: Array.from(document.querySelectorAll('.j-upload')).every(e => !!e.querySelector('.ant-upload-disabled') && !!e.closest('[inert]')) })`)
  assert.deepEqual(locked, { busy: true, disabled: true, closeCount: 0, uploadDisabled: true })
  // The DOM button and handler guards both protect against repeated actions while pending.
  await save()
  await evaluate(`${modal}.handleOk(); ${modal}.handleCancel(); ${modal}.edit({ workName: 'must not replace the pending form' })`)
  await cdp.send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27 }, target.sessionId)
  await cdp.send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27 }, target.sessionId)
  await sleep(200)
  const pendingState = await formState()
  assert.equal(pendingState.visible, true)
  assert.deepEqual(pendingState.values, initial.values)
  assert.equal(state.writes.length, 1)
  const screenshots = [await capture('fixed-slow-1440x1100-pending')]
  json(state.pending, 200, { success: true, result: { id: 'synthetic-work' }, message: '保存成功' })
  state.pending = null
  await until(`${modal}.visible === false && window.fixtureApp.saved === 1`, 'slow save success closed once')
  assert.equal(state.writes.length, 1)
  screenshots.push(await capture('fixed-slow-1440x1100-success'))
  report.scenarios.push({ name: 'fixed-slow', viewport, locked, initial, pendingState, requests: state.writes.length, screenshots, passed: true })
  await cdp.send('Target.closeTarget', { targetId: target.targetId })
}

async function main () {
  fs.mkdirSync(out, { recursive: true })
  for (const [name, content] of Object.entries(files)) fs.writeFileSync(path.join(temp, name), content)
  await build(path.join(temp, 'fixed'), undefined, path.join(root, 'web'))
  await build(path.join(temp, 'legacy'), before, path.join(root, 'web'))
  for (const relative of ['web/src/views/teaching/modules/TeachingAdditionalWorkModal.vue', 'web/src/mixins/CourseFormRecovery.js', 'web/src/components/jeecg/JUpload.vue', 'web/src/components/jeecg/JModal/index.vue', 'web/src/components/dict/JDictSelectTag.vue', 'web/src/components/jeecgbiz/JSelectDepart.vue', 'web/src/components/jeecgbiz/modal/JSelectDepartModal.vue']) report.sourceHashes[relative] = crypto.createHash('sha256').update(fs.readFileSync(path.join(root, relative))).digest('hex')
  server = fixtureServer()
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve) })
  browser = cp.spawn(chrome, ['--headless=new', '--remote-debugging-pipe', '--no-sandbox', '--disable-gpu', '--disable-background-networking', '--no-first-run', '--no-default-browser-check', '--disable-extensions', `--user-data-dir=${path.join(temp, 'chrome-profile')}`], { stdio: ['ignore', 'ignore', 'pipe', 'pipe', 'pipe'] })
  browser.stderr.on('data', () => {})
  cdp = debuggingPipe(browser)
  cdp.on(message => {
    if (message.method !== 'Fetch.requestPaused') return
    const url = new URL(message.params.request.url)
    const allowed = url.protocol === 'http:' && url.hostname === '127.0.0.1' && Number(url.port) === server.address().port
    if (!allowed) report.blockedExternalRequests.push(message.params.request.url)
    cdp.send(allowed ? 'Fetch.continueRequest' : 'Fetch.failRequest', { requestId: message.params.requestId, ...(!allowed ? { errorReason: 'BlockedByClient' } : {}) }, message.sessionId).catch(() => {})
  })
  report.browser = await cdp.send('Browser.getVersion')
  const desktop = { width: 1440, height: 1100 }
  await rejected('legacy', 'forbidden', desktop)
  await rejected('fixed', 'forbidden', desktop)
  await rejected('fixed', 'disconnect', desktop)
  await rejected('fixed', 'truncated', desktop)
  await rejected('fixed', 'forbidden', { width: 390, height: 1100 })
  await slowSave()
  assert.deepEqual(report.blockedExternalRequests, [])
  assert.deepEqual(report.unexpectedRequests, [])
  for (const [relative, hash] of Object.entries(report.sourceHashes)) assert.equal(crypto.createHash('sha256').update(fs.readFileSync(path.join(root, relative))).digest('hex'), hash, `Source changed during browser verification: ${relative}`)
  report.status = 'passed'
}

main().catch(error => { report.status = 'failed'; report.error = error.stack; process.exitCode = 1 }).finally(async () => {
  if (browser) { browser.kill('SIGTERM'); await new Promise(resolve => browser.exitCode !== null ? resolve() : browser.once('exit', resolve)) }
  if (state.pending) state.pending.destroy()
  if (server) { server.closeAllConnections(); await new Promise(resolve => server.close(resolve)) }
  fs.writeFileSync(path.join(out, 'report.json'), JSON.stringify(report, null, 2) + '\n')
  fs.rmSync(temp, { recursive: true, force: true })
  console.log(JSON.stringify({ status: report.status, scenarios: report.scenarios.length, report: path.join(out, 'report.json'), error: report.error }, null, 2))
})
