/* Real Chromium probes against an unmodified production build and local synthetic APIs.
 * Usage: PLAYWRIGHT_MODULE=/absolute/path/to/playwright node tests/theme-browser/run.cjs baseline|candidate DIST OUTPUT
 */
const fs = require('node:fs')
const path = require('node:path')
const crypto = require('node:crypto')
const { startFixture, syntheticUser } = require('./fixture-server.cjs')
const playwright = require(process.env.PLAYWRIGHT_MODULE || 'playwright')
const [phase = 'candidate', distArg = 'dist', outArg = 'output/playwright/pr94-review-20261010'] = process.argv.slice(2)
const dist = path.resolve(distArg), out = path.resolve(outArg)
fs.mkdirSync(out, { recursive: true })
const cases = [], captures = [], errors = [], external = [], snapshots = [], networkTimings = [], consoleErrors = []
let completed = false, fatalError = null, fatalStack = null
const check = (name, ok, detail) => cases.push({ name, passed: Boolean(ok), detail })
const hex = value => { const v = value.match(/\d+/g); return v ? '#' + v.slice(0, 3).map(c => Number(c).toString(16).padStart(2, '0')).join('') : value }
const hash = p => crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex')
const wait = ms => new Promise(resolve => setTimeout(resolve, ms))

async function appState(page) {
  return page.evaluate(() => {
    const root = document.querySelector('#app').__vue__
    const children = []; const visit = vm => { if (!vm || children.includes(vm)) return; children.push(vm); vm.$children.forEach(visit) }; visit(root)
    const drawer = children.find(vm => vm.$options._componentTag === 'setting-drawer')
    const custom = children.find(vm => vm.$options.__file && vm.$options.__file.includes('/settings/Custom'))
    return { color: root.$store.state.app.color, cached: JSON.parse(localStorage.getItem('pro__DEFAULT_COLOR') || 'null'), legacyBackup: JSON.parse(localStorage.getItem('pro__DEFAULT_COLOR_LEGACY') || 'null'), explicitChoice: JSON.parse(localStorage.getItem('pro__DEFAULT_COLOR_USER_CHOICE') || 'null'), marker: localStorage.getItem('pr94-unrelated-marker'), navTheme: root.$store.state.app.theme, cachedNav: localStorage.getItem('pro__DEFAULT_THEME'), drawer: drawer && { color: drawer.primaryColor, colors: drawer.themeColors || drawer.colorList, visible: drawer.visible }, customLabel: custom && custom.colorFilter(custom.primaryColor), lessStyle: Boolean(document.querySelector('style[id^="less:"]')), lessColor: window.less && window.less.options && window.less.options.modifyVars, cssVariable: getComputedStyle(document.documentElement).getPropertyValue('--app-primary-color'), title: document.title, brandName: root.$store.getters.sysConfig.brandName, customization: window.__fixtureBrandCustomization }
  })
}
async function inspectColor(page, selector) {
  return page.locator(selector).first().evaluate(e => { const s = getComputedStyle(e); return { color: s.color, background: s.backgroundColor, fontSize: s.fontSize, text: e.textContent.trim(), rect: { left: e.getBoundingClientRect().left, right: e.getBoundingClientRect().right }, display: s.display } })
}
async function runtimeDiagnostic(page) {
  return page.evaluate(() => {
    const button = document.querySelector('.account-settings-info-right .ant-btn-primary')
    return {
      url: location.href,
      appColor: document.querySelector('#app')?.__vue__?.$store.state.app.color,
      cache: localStorage.getItem('pro__DEFAULT_COLOR'),
      cssVariable: getComputedStyle(document.documentElement).getPropertyValue('--app-primary-color'),
      button: button && { background: getComputedStyle(button).backgroundColor, color: getComputedStyle(button).color, html: button.outerHTML },
      less: window.less && { version: window.less.version, sheets: window.less.sheets?.map(s => s.href), pageLoadFinished: Boolean(window.less.pageLoadFinished), modifyVarsAvailable: typeof window.less.modifyVars === 'function' },
      lessStyles: [...document.querySelectorAll('style[id^="less:"]')].map(e => ({ id: e.id, length: e.textContent.length, primaryRules: e.textContent.match(/\.ant-btn-primary\s*\{[^}]+\}/g)?.slice(0, 3), purpleOccurrences: (e.textContent.match(/#722ed1/gi) || []).length, defaultOccurrences: (e.textContent.match(/#146fc2/gi) || []).length })),
      trace: JSON.parse(sessionStorage.getItem('__pr94_less_trace') || '[]'),
      messages: [...document.querySelectorAll('.ant-message')].map(e => e.textContent)
    }
  })
}
async function waitThemeCompilationSettled(page) {
  await page.waitForFunction(() => {
    const trace = JSON.parse(sessionStorage.getItem('__pr94_less_trace') || '[]').filter(e => e.navigation === performance.timeOrigin)
    const called = trace.filter(e => e.event === 'modifyVars-called').length
    const finished = trace.filter(e => ['modifyVars-resolved', 'modifyVars-rejected'].includes(e.event)).length
    return trace.some(e => ['default-refresh-resolved', 'default-refresh-rejected'].includes(e.event)) && called > 0 && called === finished && !document.querySelector('.ant-message .anticon-loading')
  })
}
async function revealDrawer(page) {
  await page.evaluate(() => {
    const visit = vm => { if (vm.$options._componentTag === 'setting-drawer') return vm; for (const c of vm.$children) { const found = visit(c); if (found) return found } }; visit(document.querySelector('#app').__vue__).showDrawer()
  })
  await page.locator('.ant-drawer-open .setting-drawer-index-content').waitFor()
  await page.waitForFunction(() => { const drawer = document.querySelector('.ant-drawer-open .ant-drawer-content-wrapper'); return drawer && getComputedStyle(drawer).transform === 'none' })
}
async function shot(page, name) { const p = path.join(out, `${phase}-${name}.png`); await page.screenshot({ path: p, fullPage: false }); captures.push(p) }

async function main() {
  const fixture = await startFixture(dist)
  const browser = await playwright.chromium.launch({ headless: true })
  const lessFile = process.env.PR94_LESS_RUNTIME || path.resolve(__dirname, '../../node_modules/less/dist/less.min.js')
  const lessObserver = `;(() => {
    const summarize = () => [...document.querySelectorAll('style[id^="less:"]')].map(s => ({ id: s.id, rule: s.textContent.match(/\\.ant-btn-primary\\s*\\{[^}]+\\}/)?.[0] }));
    const trace = (event, detail) => { const records = JSON.parse(sessionStorage.getItem('__pr94_less_trace') || '[]'); records.push({ event, time: Date.now(), navigation: performance.timeOrigin, detail, styles: summarize() }); sessionStorage.setItem('__pr94_less_trace', JSON.stringify(records.slice(-80))); };
    trace('runtime-loaded-default-refresh-in-flight', { sheets: window.less.sheets.map(s => s.href) });
    if (window.less.pageLoadFinished) window.less.pageLoadFinished.then(() => trace('default-refresh-resolved'), error => trace('default-refresh-rejected', String(error)));
    const original = window.less.modifyVars;
    window.less.modifyVars = function (...args) { trace('modifyVars-called', args[0]); const result = original.apply(this, args); result.then(() => trace('modifyVars-resolved', args[0]), error => trace('modifyVars-rejected', String(error))); return result; };
  })();`
  const contexts = []
  async function open(seedColor, name, authenticated = true) {
    const context = await browser.newContext({ viewport: { width: ['legacy-mobile', 'new-user'].includes(name) ? 390 : 1440, height: 1000 }, serviceWorkers: 'block' }); contexts.push(context)
    await context.route('**/*', route => {
      const url = new URL(route.request().url())
      if (url.hostname === '127.0.0.1' && url.port === new URL(fixture.base).port) return route.continue()
      external.push({ scenario: name, url: url.href, method: route.request().method(), action: /less\.min\.js$/.test(url.pathname) ? 'fulfilled-from-local-installed-less' : 'aborted-no-outbound-network' })
      if (/less\.min\.js$/.test(url.pathname)) return route.fulfill({ body: fs.readFileSync(lessFile, 'utf8') + lessObserver, contentType: 'application/javascript' })
      return route.abort('blockedbyclient')
    })
    if (context.routeWebSocket) await context.routeWebSocket(/.*/, socket => socket.close())
    await context.addInitScript(({ color, auth, user, explicit }) => {
      if (sessionStorage.getItem('__seeded')) return
      sessionStorage.setItem('__seeded', 'yes')
      const set = (k, value) => localStorage.setItem('pro__' + k, JSON.stringify({ value, expire: null }))
      if (color !== null) set('DEFAULT_COLOR', color)
      if (explicit) set('DEFAULT_COLOR_USER_CHOICE', color)
      set('DEFAULT_THEME', 'light'); set('DEFAULT_FIXED_HEADER', false)
      localStorage.setItem('pr94-unrelated-marker', 'must-preserve')
      if (auth) { set('Access-Token', 'synthetic-local-pr94-token'); set('Login_Userinfo', user); set('Login_Username', user.username); set('Login_UserRole', []) }
    }, { color: seedColor, auth: authenticated, user: syntheticUser, explicit: name === 'explicit-legacy-choice' })
    const page = await context.newPage()
    page.on('pageerror', error => errors.push({ scenario: name, error: String(error) }))
    page.on('console', message => { if (message.type() === 'error') consoleErrors.push({ scenario: name, text: message.text().slice(0, 1000), time: Date.now() }) })
    page.on('response', response => { const url = new URL(response.url()); if (/color\.less|less\.min\.js|\/css\//.test(url.pathname)) networkTimings.push({ scenario: name, event: 'response', path: url.pathname, status: response.status(), time: Date.now() }) })
    await page.goto(fixture.base + (authenticated ? '/account/settings/custom' : '/user/login'))
    await page.waitForFunction(() => document.querySelector('#app') && document.querySelector('#app').__vue__)
    if (authenticated) await page.locator('.user-dropdown-menu').waitFor()
    else await page.locator('input').first().waitFor()
    await page.waitForFunction(() => document.querySelector('#app').__vue__.$store.getters.sysConfig.brandName === '合成校园平台')
    return page
  }
  try {
    const values = phase === 'baseline' ? [['legacy-upper', '#1890FF']] : [['legacy-upper', '#1890FF'], ['legacy-lower', '#1890ff'], ['legacy-mobile', '#1890FF'], ['new-user', null], ['purple', '#722ED1'], ['custom', '#24785d'], ['explicit-legacy-choice', '#1890ff']]
    for (const [name, color] of values) {
      const page = await open(color, name)
      const expected = phase === 'baseline' || name === 'explicit-legacy-choice' ? color : color === null || /^#1890ff$/i.test(color) ? '#146fc2' : color
      let state = await appState(page); snapshots.push({ scenario: name, at: 'mounted', state })
      check(name + ' persisted theme state', state.color === expected && state.cached && state.cached.value === expected, state)
      check(name + ' other preferences and customization preserved', state.marker === 'must-preserve' && state.cachedNav === JSON.stringify({ value: 'light', expire: null }) && state.brandName === '合成校园平台' && state.customization === 'preserved', state)
      check(name + ' theme drawer actually mounted', Boolean(state.drawer), state.drawer)
      if (phase === 'candidate' && /^legacy-/.test(name)) {
        check(name + ' migration keeps original legacy backup', state.legacyBackup && state.legacyBackup.value === color, state.legacyBackup)
        check(name + ' migrated default avoids old runtime compilation', !state.lessStyle && !external.some(r => r.scenario === name && r.action === 'fulfilled-from-local-installed-less'), state)
      }
      await page.evaluate(async () => { await document.querySelector('#app').__vue__.$router.push('/account/settings/base') })
      await page.locator('.ant-btn-primary').first().waitFor()
      if (expected.toLowerCase() !== '#146fc2') await waitThemeCompilationSettled(page)
      await page.waitForFunction(expectedColor => {
        const button = document.querySelector('.account-settings-info-right .ant-btn-primary')
        const probe = document.createElement('span'); probe.style.color = expectedColor; document.body.appendChild(probe)
        const expected = getComputedStyle(probe).color; probe.remove()
        return button && getComputedStyle(button).backgroundColor === expected
      }, expected, { timeout: 15000 })
      const primary = await inspectColor(page, '.account-settings-info-right .ant-btn-primary')
      snapshots.push({ scenario: name, at: 'actual-primary-button', primary })
      check(name + ' real Ant primary reflects restored color', hex(primary.background).toLowerCase() === expected.toLowerCase(), primary)
      await page.evaluate(async () => { await document.querySelector('#app').__vue__.$router.push('/account/settings/custom') })
      await page.locator('.account-settings-info-right .ant-list').waitFor()
      await revealDrawer(page)
      const selected = await page.locator('.ant-drawer-open .setting-drawer-theme-color-colorBlock').evaluateAll(nodes => nodes.filter(n => n.querySelector('.anticon-check')).map(n => getComputedStyle(n).backgroundColor))
      snapshots.push({ scenario: name, selected })
      if (phase === 'baseline') check('legacy default reproduces missing default selection', selected.length === 0, selected)
      else check(name + ' drawer selection follows theme state', selected.length === 1 && hex(selected[0]).toLowerCase() === expected.toLowerCase(), selected)
      if (name === 'legacy-upper') await shot(page, name + '-drawer')
      await page.keyboard.press('Escape')
      await page.evaluate(() => { const visit = vm => { if (vm.$options._componentTag === 'setting-drawer') vm.onClose(); vm.$children.forEach(visit) }; visit(document.querySelector('#app').__vue__) })
      const beforeReload = (await appState(page)).cached
      await page.reload(); await page.locator('.user-dropdown-menu').waitFor(); await page.waitForFunction(() => document.querySelector('#app').__vue__.$store.state.app.color)
      state = await appState(page); snapshots.push({ scenario: name, at: 'reload', state })
      check(name + ' refresh is idempotent', JSON.stringify(state.cached) === JSON.stringify(beforeReload) && state.color === expected, state)
      if (name === 'legacy-mobile') {
        await revealDrawer(page)
        const mobileDefault = await page.locator('.ant-drawer-open .setting-drawer-theme-color-colorBlock').evaluateAll(nodes => nodes.filter(n => n.querySelector('.anticon-check')).map(n => getComputedStyle(n).backgroundColor))
        check('legacy migration has one default selection after mobile reload', mobileDefault.length === 1 && hex(mobileDefault[0]) === '#146fc2', mobileDefault)
        await shot(page, 'mobile-default-reloaded')
      }
      if (name === 'legacy-upper') {
        const avatar = await inspectColor(page, '.user-dropdown-menu .avatar'); snapshots.push({ scenario: name, avatar })
        check('actual configured avatar keeps neutral inline foreground', avatar.color === 'rgb(102, 112, 133)', avatar)
        const label = await page.locator('.account-settings-info-right').textContent()
        check(phase === 'baseline' ? 'baseline personal settings reproduces missing label' : 'personal settings resolves default label', phase === 'baseline' ? !/科技蓝|薄暮|火山|日暮|明青|极光绿|极客蓝|酱紫|自定义色/.test(label) : /科技蓝/.test(label), label)
        await shot(page, name + '-account-settings')
        await page.goto(fixture.base + '/friend-detail?id=synthetic-friend'); await page.locator('.work-op a').first().waitFor()
        await page.locator('.work-op a').first().hover(); await wait(350); const friendHover = await inspectColor(page, '.work-op a'); snapshots.push({ scenario: name, friendHover })
        check(phase === 'baseline' ? 'baseline friend hover reproduces stale blue' : 'friend hover uses primary theme', phase === 'baseline' ? friendHover.color === 'rgb(24, 144, 255)' : friendHover.color === 'rgb(20, 111, 194)', friendHover)
        await page.goto(fixture.base + '/newsList'); await page.locator('.title').waitFor(); await page.locator('.title').hover(); await wait(350); const newsHover = await inspectColor(page, '.title'); snapshots.push({ scenario: name, newsHover })
        check(phase === 'baseline' ? 'baseline news hover reproduces stale blue' : 'news hover uses primary theme', phase === 'baseline' ? newsHover.color === 'rgb(24, 144, 255)' : newsHover.color === 'rgb(20, 111, 194)', newsHover)
        await page.goto(fixture.base + '/index'); await page.locator('.campus-masthead').waitFor()
        for (const width of [1440, 768, 390, 320]) {
          await page.setViewportSize({ width, height: 1000 }); await wait(100)
          const foreground = await inspectColor(page, '.university-motto span'), background = await inspectColor(page, '.campus-masthead')
          const geometry = await page.evaluate(() => ({ viewport: innerWidth, document: document.documentElement.scrollWidth, masthead: document.querySelector('.campus-masthead').scrollWidth }))
          const fg = foreground.color.match(/[\d.]+/g).map(Number), bg = background.background.match(/[\d.]+/g).map(Number)
          const alpha = fg.length > 3 ? fg[3] : 1; const blended = fg.slice(0, 3).map((v, i) => v * alpha + bg[i] * (1 - alpha))
          const lum = rgb => rgb.map(v => v / 255).map(v => v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4).reduce((a, v, i) => a + v * [0.2126, 0.7152, 0.0722][i], 0)
          const ratio = (Math.max(lum(blended), lum(bg)) + 0.05) / (Math.min(lum(blended), lum(bg)) + 0.05)
          snapshots.push({ scenario: name, width, masthead: { foreground, background, contrast: ratio, geometry } })
          if (foreground.display !== 'none') check(phase === 'baseline' ? `baseline masthead 10px contrast fails ${width}` : `masthead small text contrast passes ${width}`, phase === 'baseline' ? ratio < 4.5 : ratio >= 4.5, { ratio, foreground, background })
          check(`public header fits ${width}`, geometry.document <= width && geometry.masthead <= width, geometry)
          await shot(page, `masthead-${width}`)
        }
      }
      if (phase === 'candidate' && name === 'new-user') {
        await page.setViewportSize({ width: 390, height: 1000 }); await revealDrawer(page)
        await page.locator('.ant-drawer-open .setting-drawer-theme-color-colorBlock').nth(7).click()
        await page.waitForFunction(() => document.querySelector('#app').__vue__.$store.state.app.color === '#722ED1'); state = await appState(page)
        check('real purple selection updates store and cache', state.color === '#722ED1' && state.cached.value === '#722ED1', state)
        await waitThemeCompilationSettled(page)
        const initialPurple = await runtimeDiagnostic(page)
        snapshots.push({ scenario: name, at: 'first-purple-compilation-settled', runtime: initialPurple })
        check('first purple selection stays purple after all compiler writes settle', initialPurple.lessStyles.some(s => s.primaryRules && /background-color: #722ed1/i.test(s.primaryRules[0])), initialPurple)
        await shot(page, 'mobile-purple-selected')
        await page.reload(); await page.locator('.user-dropdown-menu').waitFor(); state = await appState(page)
        check('real purple selection survives mobile reload', state.color === '#722ED1' && state.cached.value === '#722ED1' && state.explicitChoice.value === '#722ED1', state)
        await revealDrawer(page)
        const selectedPurple = await page.locator('.ant-drawer-open .setting-drawer-theme-color-colorBlock').evaluateAll(nodes => nodes.filter(n => n.querySelector('.anticon-check')).map(n => getComputedStyle(n).backgroundColor))
        check('mobile purple has unique selection after reload', selectedPurple.length === 1 && hex(selectedPurple[0]) === '#722ed1', selectedPurple)
        await waitThemeCompilationSettled(page)
        await shot(page, 'mobile-purple-reloaded')
        await page.evaluate(() => { const visit = vm => { if (vm.$options._componentTag === 'setting-drawer') vm.onClose(); vm.$children.forEach(visit) }; visit(document.querySelector('#app').__vue__) })
        await page.evaluate(async () => { await document.querySelector('#app').__vue__.$router.push('/account/settings/base') })
        snapshots.push({ scenario: name, at: 'before-mobile-purple-primary-wait', runtime: await runtimeDiagnostic(page) })
        await page.waitForFunction(() => { const button = document.querySelector('.account-settings-info-right .ant-btn-primary'); return button && getComputedStyle(button).backgroundColor === 'rgb(114, 46, 209)' })
        snapshots.push({ scenario: name, at: 'after-mobile-purple-primary-wait', runtime: await runtimeDiagnostic(page) })
        check('mobile selected purple compiles actual Ant primary after reload', true, await inspectColor(page, '.account-settings-info-right .ant-btn-primary'))
      }
    }
    if (phase === 'candidate') {
      const login = await open('#1890FF', 'login-shell', false), state = await appState(login)
      check('public login startup migrates legacy before authenticated drawer', state.color === '#146fc2' && state.cached.value === '#146fc2', state)
      await shot(login, 'login-shell')
    }
    check('production Vue runtime has no uncaught browser exceptions', errors.length === 0, errors)
    check('all API traffic stays on synthetic loopback and uses only GET', fixture.requests.filter(r => r.path.startsWith('/api/')).every(r => r.method === 'GET'), fixture.requests.filter(r => r.path.startsWith('/api/')))
    completed = true
  } catch (error) {
    fatalError = String(error)
    fatalStack = error.stack
    check('browser flow completes', false, fatalError)
    const lastPage = contexts.at(-1)?.pages().at(-1)
    if (lastPage) {
      await shot(lastPage, 'failure').catch(() => {})
      snapshots.push({ at: 'failure-runtime', runtime: await runtimeDiagnostic(lastPage).catch(() => null) })
      snapshots.push({ at: 'failure', dom: await lastPage.evaluate(() => ({ url: location.href, drawers: [...document.querySelectorAll('.ant-drawer')].map(e => ({ cls: e.className, zIndex: getComputedStyle(e).zIndex, rect: { x: e.getBoundingClientRect().x, width: e.getBoundingClientRect().width }, html: e.innerHTML.slice(0, 1000) })) })).catch(() => null) })
    }
  } finally {
    const result = { phase, completed, fatalError, fatalStack, status: completed && !cases.some(c => !c.passed) && cases.length > 0 ? 'passed' : 'failed', source: { dist, indexSHA256: hash(path.join(dist, 'index.html')), js: fs.readdirSync(path.join(dist, 'js')).filter(f => /^app\..*\.js$/.test(f)).map(f => ({ file: f, sha256: hash(path.join(dist, 'js', f)) })), lessRuntime: { path: lessFile, sha256: hash(lessFile), header: fs.readFileSync(lessFile, 'utf8').slice(0, 300) } }, chromiumVersion: browser.version(), passed: cases.filter(c => c.passed).length, total: cases.length, cases, snapshots, captures, errors, consoleErrors, networkTimings, externalRequestsBlockedOrLocallyFulfilled: external, syntheticRequests: fixture.requests.filter(r => r.path.startsWith('/api/')), limitations: ['Actual production Vue components, synthetic cached user identity and permission menu; no real login or database acceptance.', 'External Less URL is fulfilled from recorded local Less runtime to compile the real production color.less without outbound browser network. Observer logging forwards original modifyVars without adding delays or changing arguments. External menu thumbnail artwork is blocked and may show missing images in screenshots.', 'Account center member and ImagPreview tree rules currently have no live template nodes; no synthetic DOM injection is used to claim real page coverage.', 'No production APIs, writes, deployments or data used.'] }
    fs.writeFileSync(path.join(out, phase + '-report.json'), JSON.stringify(result, null, 2))
    console.log(JSON.stringify({ phase, passed: result.passed, total: result.total, failed: cases.filter(c => !c.passed).map(c => ({ name: c.name, detail: c.detail })), report: path.join(out, phase + '-report.json') }, null, 2))
    await browser.close(); await new Promise(resolve => fixture.server.close(resolve))
    if (result.status !== 'passed') process.exitCode = 1
  }
}
main().catch(error => { console.error(error); process.exitCode = 1 })
