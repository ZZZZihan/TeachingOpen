#!/usr/bin/env node
/* Real Chromium + real compiled Header/TMenu. No component stub or DOM-only click substitute. */
const fs = require('node:fs'), path = require('node:path'), os = require('node:os'), http = require('node:http'), cp = require('node:child_process')
const WebSocket = require('ws')
const build = require('./teaching-menu-browser/build.cjs')
const args = process.argv.slice(2)
function option (key, fallback) { const i = args.indexOf(key); return i < 0 ? fallback : args[i + 1] }
const root = path.resolve(option('--root', path.join(__dirname, '../..')))
const output = path.resolve(option('--output', path.join(root, 'ci-results/teaching-menu-browser')))
const ref = option('--ref', 'working-tree'), legacy = args.includes('--expect-legacy')
const chrome = process.env.CHROME_BIN || ['/usr/bin/google-chrome', '/usr/bin/chromium', '/usr/bin/chromium-browser', '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'].find(p => fs.existsSync(p))
const checks = [], clicks = [], external = [], blocked = [], errors = []
let browser, server, socket, profile, manifest, version
function check (name, passed) { checks.push({ case: name, passed: Boolean(passed) }); console.log((passed ? 'PASS ' : 'FAIL ') + name); if (!passed) throw new Error(name) }
const delay = ms => new Promise(resolve => setTimeout(resolve, ms))
async function until (fn, message, ms = 15000) { const start = Date.now(); while (Date.now() - start < ms) { const value = await fn(); if (value) return value; await delay(50) } throw new Error('Timed out: ' + message) }
async function main () {
  fs.mkdirSync(output, { recursive: true })
  check('Chromium binary exists (browser is required, never skipped)', chrome && fs.existsSync(chrome))
  manifest = await build(root, ref, path.join(output, 'build'))
  fs.writeFileSync(path.join(output, 'sources.json'), JSON.stringify(manifest, null, 2))
  server = http.createServer((req, res) => {
    if (req.url.startsWith('/scratch3/index.html')) { res.setHeader('Content-Type', 'text/html'); res.end('<!doctype html><link rel="icon" href="data:,"><h1 id="editor-arrival">Synthetic static editor</h1>'); return }
    const file = req.url.split('?')[0] === '/preview.js' ? 'preview.js' : 'index.html'
    res.setHeader('Content-Type', file.endsWith('.js') ? 'application/javascript' : 'text/html'); fs.createReadStream(path.join(output, 'build', file)).pipe(res)
  })
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
  const origin = 'http://127.0.0.1:' + server.address().port
  profile = fs.mkdtempSync(path.join(os.tmpdir(), 'teaching-menu-chrome-'))
  browser = cp.spawn(chrome, ['--headless=new', '--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage', '--no-first-run', '--no-default-browser-check', '--disable-background-networking', '--disable-extensions', '--disable-component-update', '--disable-sync', '--metrics-recording-only', '--disable-features=MediaRouter,OptimizationHints', '--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1, EXCLUDE localhost', '--remote-debugging-port=0', '--user-data-dir=' + profile, 'about:blank'], { stdio: ['ignore', 'ignore', 'pipe'] })
  let log = ''
  browser.stderr.on('data', data => { log += data.toString(); if (log.length > 20000) log = log.slice(-20000) })
  browser.on('error', error => { errors.push(error.message) })
  const wsUrl = await until(() => { if (browser.exitCode !== null) throw new Error('Chromium exited ' + browser.exitCode); return (log.match(/DevTools listening on (ws:\/\/[^\s]+)/) || [])[1] }, 'Chromium DevTools endpoint')
  socket = new WebSocket(wsUrl)
  await new Promise((resolve, reject) => { socket.once('open', resolve); socket.once('error', reject) })
  let seq = 0
  const pending = new Map(), sessions = new Map(), ready = new Map()
  function send (method, params = {}, sessionId) { return new Promise((resolve, reject) => { const id = ++seq; const timeout = setTimeout(() => { pending.delete(id); reject(new Error('CDP timeout ' + method)) }, 15000); pending.set(id, { resolve, reject, timeout }); socket.send(JSON.stringify({ id, method, params, ...(sessionId ? { sessionId } : {}) })) }) }
  socket.on('message', raw => {
    const message = JSON.parse(raw)
    if (message.id) {
      const item = pending.get(message.id); if (!item) return; clearTimeout(item.timeout); pending.delete(message.id)
      message.error ? item.reject(new Error(JSON.stringify(message.error))) : item.resolve(message.result)
    } else if (message.method === 'Target.attachedToTarget' && message.params.targetInfo.type === 'page') {
      const { sessionId, targetInfo } = message.params; sessions.set(targetInfo.targetId, sessionId)
      const configured = (async () => { await send('Fetch.enable', { patterns: [{ urlPattern: '*' }] }, sessionId); await send('Runtime.runIfWaitingForDebugger', {}, sessionId); await send('Page.enable', {}, sessionId); await send('Runtime.enable', {}, sessionId) })()
      ready.set(targetInfo.targetId, configured); configured.catch(error => errors.push(error.message))
    } else if (message.method === 'Fetch.requestPaused') {
      const { requestId, request, resourceType } = message.params, sid = message.sessionId
      let action
      if (request.url.startsWith(origin + '/')) action = send('Fetch.continueRequest', { requestId }, sid)
      else if (request.url === 'https://menu-fixture.invalid/learning') {
        external.push({ url: request.url, resourceType, intercepted_before_network: true })
        action = send('Fetch.fulfillRequest', { requestId, responseCode: 200, responseHeaders: [{ name: 'Content-Type', value: 'text/html' }], body: Buffer.from('<!doctype html><link rel="icon" href="data:,"><h1 id="https-arrival">Synthetic HTTPS destination</h1>').toString('base64') }, sid)
      } else { blocked.push(request.url); action = send('Fetch.failRequest', { requestId, errorReason: 'BlockedByClient' }, sid) }
      action.catch(error => errors.push(error.message))
    } else if (message.method === 'Runtime.exceptionThrown') errors.push(message.params.exceptionDetails.text)
  })
  version = await send('Browser.getVersion')
  await send('Target.setAutoAttach', { autoAttach: true, waitForDebuggerOnStart: true, flatten: true })
  const evaluate = async (sid, expression) => { const value = await send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true }, sid); if (value.exceptionDetails) throw new Error(value.exceptionDetails.text + ': ' + expression); return value.result.value }
  async function page (width, height) {
    const { targetId } = await send('Target.createTarget', { url: 'about:blank' })
    const sid = await until(() => sessions.get(targetId), 'target attached'); await ready.get(targetId)
    await send('Emulation.setDeviceMetricsOverride', { width, height, deviceScaleFactor: 1, mobile: false }, sid)
    await send('Page.navigate', { url: origin + '/' }, sid)
    await until(() => evaluate(sid, 'Boolean(window.__headerFixtureReady && document.querySelector(".configured-menu.ant-menu"))'), 'real Header + TMenu ready')
    return { sid, targetId }
  }
  async function click (sid, title, label) {
    const point = await until(() => evaluate(sid, `(() => { const e = [...document.querySelectorAll('.ant-menu span')].find(e => e.textContent === ${JSON.stringify(title)} && e.getBoundingClientRect().width > 0 && getComputedStyle(e).visibility !== 'hidden'); if(!e) return null; const r=e.getBoundingClientRect(); return {x:r.x+r.width/2,y:r.y+r.height/2,href:e.closest('a')?.getAttribute('href')||null,tag:e.parentElement.tagName}; })()`), 'visible menu ' + title)
    await send('Input.dispatchMouseEvent', { type: 'mouseMoved', x: point.x, y: point.y }, sid)
    await send('Input.dispatchMouseEvent', { type: 'mousePressed', x: point.x, y: point.y, button: 'left', clickCount: 1 }, sid)
    await send('Input.dispatchMouseEvent', { type: 'mouseReleased', x: point.x, y: point.y, button: 'left', clickCount: 1 }, sid)
    clicks.push({ case: label, title, input: 'Chromium Input.dispatchMouseEvent', ...point }); await delay(180)
  }
  async function openMobile (sid, width) {
    if (width > 900) return
    const point = await evaluate(sid, '(() => { const e=document.querySelector(".menu-toggle"); if(e.getAttribute("aria-expanded")==="true")return null; const r=e.getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2}; })()')
    if (point) { await send('Input.dispatchMouseEvent', { type: 'mousePressed', ...point, button: 'left', clickCount: 1 }, sid); await send('Input.dispatchMouseEvent', { type: 'mouseReleased', ...point, button: 'left', clickCount: 1 }, sid) }
    await delay(120)
  }
  async function shot (sid, name) { const image = await send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false }, sid); fs.writeFileSync(path.join(output, name + '.png'), Buffer.from(image.data, 'base64')) }
  for (const [width, height] of [[1440, 1000], [390, 1200]]) {
    let { sid, targetId } = await page(width, height)
    check(width + ' actual Header contains mounted TMenu', await evaluate(sid, '(() => { const names=[]; function visit(v){if(!v)return;names.push(v.$options.name);v.$children.forEach(visit)}visit(document.querySelector("#app").__vue__); return names.includes("TMenu") && !!document.querySelector("header.public-header") })()'))
    await openMobile(sid, width)
    await shot(sid, width + '-unsafe-before-click')
    check(width + ' unsafe leaf URL has expected baseline/fixed link shape', await evaluate(sid, 'Array.from(document.querySelectorAll(".configured-menu a")).some(a=>a.getAttribute("href")?.startsWith("javascript:"))') === legacy)
    await click(sid, '历史危险顶级', width + ' top-level unsafe')
    await click(sid, '历史危险分组', width + ' submenu-title unsafe')
    await delay(400)
    await click(sid, '历史危险子项', width + ' child unsafe')
    const counters = await evaluate(sid, 'window.__menuProbe')
    for (const key of ['top', 'group', 'child']) check(width + ' ' + key + (legacy ? ' baseline marker executes once on real click' : ' dangerous navigation cannot execute on real click'), counters[key] === (legacy ? 1 : 0))
    await shot(sid, width + '-unsafe-after-click')
    if (!legacy) {
      if (width > 900) {
        const point = await evaluate(sid, `(() => {const e=[...document.querySelectorAll('.ant-menu-submenu-title')].find(e=>e.textContent.includes('历史危险分组'));const r=e.getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2}})()`);
        await send('Input.dispatchMouseEvent', { type: 'mouseMoved', ...point }, sid); await delay(500)
      }
      await click(sid, '正常子项', width + ' safe child beneath disabled unsafe title')
      check(width + ' safe descendants remain navigable', (await evaluate(sid, 'location.hash')) === '#/safe-child')
    }
    await evaluate(sid, 'window.setFixture("route")'); await openMobile(sid, width)
    await click(sid, '站内课程', width + ' route')
    check(width + ' normal SPA route including query and fragment navigates', (await evaluate(sid, 'location.hash')) === '#/courseList?source=menu#safe')
    await shot(sid, width + '-normal-route')
    await evaluate(sid, 'window.setFixture("group")'); await openMobile(sid, width)
    await click(sid, '正常分组', width + ' normal submenu title')
    check(width + ' normal submenu title navigates', (await evaluate(sid, 'location.hash')) === '#/courseList')
    await evaluate(sid, 'window.setFixture("native")'); await openMobile(sid, width)
    await click(sid, '静态编辑器', width + ' static editor')
    await until(() => evaluate(sid, 'Boolean(document.querySelector("#editor-arrival"))'), 'static editor navigation')
    check(width + ' native same-origin editor preserves path and query', (await evaluate(sid, 'location.pathname+location.search')) === '/scratch3/index.html?scene=create')
    await send('Target.closeTarget', { targetId }); ({ sid, targetId } = await page(width, height))
    await evaluate(sid, 'window.setFixture("https")'); await openMobile(sid, width)
    await click(sid, 'HTTPS 同页', width + ' HTTPS same tab')
    await until(() => evaluate(sid, 'Boolean(document.querySelector("#https-arrival"))'), 'intercepted HTTPS navigation')
    check(width + ' HTTPS same-tab navigation is preserved', (await evaluate(sid, 'location.href')) === 'https://menu-fixture.invalid/learning')
    await send('Target.closeTarget', { targetId }); ({ sid, targetId } = await page(width, height))
    await evaluate(sid, 'window.setFixture("popup")'); await openMobile(sid, width)
    const previous = new Set(sessions.keys())
    await shot(sid, width + '-https-new-tab')
    await click(sid, 'HTTPS 新页', width + ' HTTPS new tab')
    const popup = await until(() => [...sessions.keys()].find(id => !previous.has(id)), 'HTTPS popup'); await ready.get(popup)
    const popupSid = sessions.get(popup)
    await until(() => evaluate(popupSid, 'Boolean(document.querySelector("#https-arrival"))'), 'intercepted popup destination')
    check(width + ' HTTPS popup navigates', (await evaluate(popupSid, 'location.href')) === 'https://menu-fixture.invalid/learning')
    check(width + ' HTTPS popup has no opener', await evaluate(popupSid, 'window.opener === null'))
    await send('Target.closeTarget', { targetId: popup }); await send('Target.closeTarget', { targetId })
  }
  check('all four synthetic HTTPS navigation requests intercepted before network', external.length === 4 && external.every(e => e.intercepted_before_network))
  check('no unexpected outbound request', blocked.length === 0)
  check('no browser runtime or protocol error', errors.length === 0)
}
main().catch(error => { errors.push(error.message); checks.push({ case: 'runner completes all required browser cases', passed: false }); console.error(error.stack); process.exitCode = 1 }).finally(async () => {
  if (socket) socket.close()
  if (browser) { browser.kill('SIGTERM'); await new Promise(resolve => { browser.once('exit', resolve); setTimeout(() => { browser.kill('SIGKILL'); resolve() }, 2000).unref() }) }
  if (server) await new Promise(resolve => server.close(resolve))
  if (profile) fs.rmSync(profile, { recursive: true, force: true })
  fs.mkdirSync(output, { recursive: true })
  fs.writeFileSync(path.join(output, 'report.json'), JSON.stringify({ observed_utc: new Date().toISOString(), expected_legacy: legacy, scope: 'real compiled Header + TMenu in isolated Chromium; synthetic menus; intercepted HTTPS destinations', source: manifest, browser: version, viewports: [{ width: 1440, height: 1000 }, { width: 390, height: 1200 }], passed: checks.filter(c => c.passed).length, failed: checks.filter(c => !c.passed).length, total: checks.length, completed: checks.length > 0 && checks.every(c => c.passed) && errors.length === 0, checks, clicks, external, blocked, errors }, null, 2) + '\n')
})
