// Actual ShowAnnouncement SFC compiled and mounted in Chromium, with only design-system shells stubbed.
// All payload effects are local DOM markers; this fixture does not send data to any endpoint.
const assert = require('node:assert/strict')
const { readFileSync, writeFileSync, mkdtempSync, rmSync, existsSync } = require('node:fs')
const { resolve, join } = require('node:path')
const { tmpdir } = require('node:os')
const { createHash } = require('node:crypto')
const { spawnSync, execFileSync } = require('node:child_process')
const compiler = require('vue-template-compiler')
const root = resolve(__dirname, '..')
const browser = process.env.CHROME_BIN || ['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', '/usr/bin/google-chrome', '/usr/bin/chromium'].find(existsSync)
assert.ok(browser, 'Set CHROME_BIN to an installed Chromium browser')
const legacy = process.argv.includes('--expect-legacy')
const source = legacy ? execFileSync('git', ['show', 'a3f4e10ceafcbe405093a3abe06a20225a17d3f6:web/src/components/tools/ShowAnnouncement.vue'], { cwd: root, encoding: 'utf8' }) : readFileSync(join(root, 'src/components/tools/ShowAnnouncement.vue'), 'utf8')
const sfc = compiler.parseComponent(source)
const render = compiler.compile(sfc.template.content)
assert.deepEqual(render.errors, [])
const componentScript = sfc.script.content.replace(/^\s*import .*$/gm, '').replace('export default', 'const component =')
const sanitizer = readFileSync(join(root, 'src/utils/richText.js'), 'utf8').replace(/^import .*$/gm, '').replace(/export function/g, 'function')
const safeImage = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9Zl9sAAAAASUVORK5CYII='
const payload = '<p>课堂通知 <strong>保留格式</strong></p><table><tbody><tr><td>表格保留</td></tr></tbody></table>' +
  '<img src="' + safeImage + '" alt="正常图片"><img src="data:image/png;base64,broken" onerror="document.body.dataset.executed=\'image\'">' +
  '<a href="javascript:void(document.body.dataset.executed=\'url\')" onclick="document.body.dataset.executed=\'click\'">危险链接</a>' +
  '<svg onload="document.body.dataset.executed=\'svg\'"></svg><iframe srcdoc="<script>parent.document.body.dataset.executed=\'frame\'</script>"></iframe>' +
  '<div style="background-image:url(javascript:document.body.dataset.executed=\'css\');color:red">样式</div>'
const scripts = ["window.addEventListener('error', event => {document.querySelector('#result').textContent = JSON.stringify({error: event.message, file: event.filename, line: event.lineno});});", readFileSync(require.resolve('vue/dist/vue.js'), 'utf8'), readFileSync(require.resolve('dompurify/dist/purify.js'), 'utf8'),
  'const createDOMPurify = DOMPurify;\n' + sanitizer, componentScript + `\ncomponent.render = new Function(${JSON.stringify(render.render)}); component.staticRenderFns = ${JSON.stringify(render.staticRenderFns)}.map(body => new Function(body));`, `
for (const name of ['j-modal','a-button','a-card','a-card-meta','a-divider']) Vue.component(name, {render(h) {return h('div', this.$slots.default)}});
const app = new Vue({render: h => h(component, {ref: 'notice'})}).$mount('#app');
app.$refs.notice.detail({titile: '合成通知', sender: 'fixture_admin', msgContent: ${JSON.stringify(payload)}, sendTime: '2026-10-11'});
Vue.nextTick(() => setTimeout(() => {
  const content = document.querySelector('.article-content');
  for (const img of content.querySelectorAll('img')) img.dispatchEvent(new Event('error'));
  const link = content.querySelector('a'); if (link) link.dispatchEvent(new Event('mouseover'));
  setTimeout(() => {
    const checks = {actualComponent: !!content, executed: document.body.dataset.executed || '',
      unsafe: !!content.querySelector('[onerror],[onclick],[onload],svg,iframe,script') || Array.from(content.querySelectorAll('a')).some(a => /^javascript:/i.test(a.getAttribute('href') || '')),
      paragraph: content.querySelector('p strong').textContent === '保留格式', table: content.querySelector('table td').textContent === '表格保留',
      image: content.querySelector('img[alt="正常图片"]').naturalWidth === 1, html: content.innerHTML};
    document.querySelector('#result').textContent = JSON.stringify(checks);
  }, 100);
}, 100));`]
const directory = mkdtempSync(join(tmpdir(), 'teaching-announcement-dom-'))
try {
  const html = '<!doctype html><html><head><meta charset="UTF-8"></head><body><div id="app"></div><pre id="result"></pre>' + scripts.map(script => '<script>' + script.replace(/<\/script/gi, '<\\/script') + '</script>').join('') + '</body></html>'
  const file = join(directory, 'fixture.html'); writeFileSync(file, html)
  const screenshot = process.env.ANNOUNCEMENT_SCREENSHOT_DIR ? join(resolve(process.env.ANNOUNCEMENT_SCREENSHOT_DIR), legacy ? 'announcement-before.png' : 'announcement-after.png') : null
  const result = spawnSync(browser, [...(screenshot ? ['--screenshot=' + screenshot] : []), '--window-size=1280,800', '--headless=new', '--no-sandbox', '--disable-gpu', '--disable-background-networking', '--no-first-run', '--no-default-browser-check', '--disable-extensions', '--user-data-dir=' + join(directory, 'profile'), '--virtual-time-budget=2000', '--dump-dom', 'file://' + file], {encoding:'utf8', timeout:30000, killSignal:'SIGKILL', maxBuffer: 4 * 1024 * 1024})
  assert.equal(result.status, 0, (result.stderr || '').slice(-2000))
  const match = result.stdout.match(/<pre id="result">([^<]+)<\/pre>/)
  assert.ok(match, 'Browser must finish the actual component rendering: ' + (result.stderr || '').slice(-1000))
  const observed = JSON.parse(match[1].replace(/&quot;/g,'"').replace(/&gt;/g,'>').replace(/&lt;/g,'<').replace(/&amp;/g,'&'))
  assert.equal(observed.actualComponent, true); assert.equal(observed.paragraph, true); assert.equal(observed.table, true); assert.equal(observed.image, true)
  assert.equal(observed.unsafe, legacy); assert.equal(Boolean(observed.executed), legacy)
  process.stdout.write(JSON.stringify({status:'passed', mode:legacy ? 'legacy-reproduced' : 'fixed', component:'ShowAnnouncement.vue', source_sha256:createHash('sha256').update(source).digest('hex'), viewport:{width:1280,height:800}, checks:observed}, null, 2) + '\n')
} finally { rmSync(directory, {recursive:true, force:true}) }
