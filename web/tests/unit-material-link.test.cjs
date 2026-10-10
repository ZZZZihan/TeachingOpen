const assert = require('node:assert/strict')
const { execFileSync } = require('node:child_process')
const { readFileSync } = require('node:fs')
const { resolve } = require('node:path')
const { test } = require('node:test')
const vm = require('node:vm')

const root = resolve(__dirname, '..')
const origin = 'http://127.0.0.1:18150'
const staticDomain = '/api/sys/common/static'
function source (path) {
  return process.env.SOURCE_REF
    ? execFileSync('git', ['show', `${process.env.SOURCE_REF}:web/${path}`], { cwd: root, encoding: 'utf8' })
    : readFileSync(resolve(root, path), 'utf8')
}
function reader (config = {}) {
  // Execute the real helpers: identity stubs hide the second staticDomain prefix.
  const context = {
    URL, URLSearchParams,
    window: { location: { origin } }, location: { protocol: 'http:', host: '127.0.0.1:18150' },
    store: { getters: { sysConfig: { uploadType: 'local', staticDomain, filePreview: 'none', ...config } } },
    axios: () => Promise.resolve({ success: true }), Vue: {}, SYS_CONFIG: 'unused', component: null
  }
  vm.createContext(context)
  vm.runInContext(source('src/api/manage.js').replace(/^import .*$/gm, '').replace(/^export default api$/m, '').replace(/\bexport function /g, 'function '), context)
  const script = source('src/views/account/course/modules/UnitViewModal.vue').match(/<script>([\s\S]*?)<\/script>/)[1]
  vm.runInContext(script.replace(/^import .*$/gm, '').replace('export default', 'component ='), context)
  const instance = { ...context.component.data(), $refs: {} }
  for (const [name, method] of Object.entries(context.component.methods)) instance[name] = method.bind(instance)
  for (const [name, computed] of Object.entries(context.component.computed)) Object.defineProperty(instance, name, { get: () => computed.call(instance) })
  return instance
}

test('已由 mineUnit 解析的课程资料和教案根路径不重复加文件前缀', () => {
  const instance = reader()
  instance.unit = { coursePpt: `${staticDomain}/role-flow/learning-notes.txt`, coursePlan: `${staticDomain}/role-flow/lesson.pdf` }
  assert.equal(instance.resources[0].url, `${origin}${staticDomain}/role-flow/learning-notes.txt`)
  assert.equal(instance.resources[1].url, `${origin}${staticDomain}/role-flow/lesson.pdf`)
})

test('原相对文件 key 继续解析一次，资料字段和顺序保持不变', () => {
  const instance = reader()
  instance.unit = { coursePpt: ' role-flow/one.txt,role-flow/two.pdf ', coursePlan: 'role-flow/plan.docx' }
  assert.deepEqual(Array.from(instance.resources, item => [item.key, item.name, item.url]), [
    ['coursePpt-0', '课程资料 1', `${origin}${staticDomain}/role-flow/one.txt`],
    ['coursePpt-1', '课程资料 2', `${origin}${staticDomain}/role-flow/two.pdf`],
    ['coursePlan-0', '课程教案 1', `${origin}${staticDomain}/role-flow/plan.docx`]
  ])
  assert.equal(instance.unit.coursePpt, ' role-flow/one.txt,role-flow/two.pdf ')
})

test('完整外链和 protocol-relative 链接保留目标，不移入本地文件目录', () => {
  const instance = reader()
  instance.unit = { coursePpt: 'https://files.example/a%20b.txt?x=1&y=中文#part,//cdn.example/notes.txt?download=1' }
  assert.equal(instance.resources[0].url, new URL('https://files.example/a%20b.txt?x=1&y=中文#part').href)
  assert.equal(instance.resources[1].url, 'http://cdn.example/notes.txt?download=1')
})

test('根路径的空格、已编码字符、查询和片段保持一次 URL 编码', () => {
  const instance = reader()
  const file = `${staticDomain}/role-flow/学习%20notes.txt?download=a%2Fb&name=中文#part`
  instance.unit = { coursePpt: file }
  assert.equal(instance.resources[0].url, new URL(file, origin).href)
  assert.equal(new URL(instance.resources[0].url).searchParams.get('download'), 'a/b')
})

test('officeapps 预览继续包装根路径与相对 key，嵌套文件只有一个前缀', () => {
  const instance = reader({ filePreview: 'officeapps' })
  instance.unit = { coursePpt: `${staticDomain}/role-flow/slides.pptx,role-flow/plan.docx` }
  for (const [index, name] of ['slides.pptx', 'plan.docx'].entries()) {
    const preview = new URL(instance.resources[index].url)
    assert.equal(preview.origin, 'https://view.officeapps.live.com')
    assert.equal(preview.searchParams.get('src'), `${origin}${staticDomain}/role-flow/${name}`)
  }
})

test('ow365 加密 aes/aess 地址保持原预览标记与密文', () => {
  const instance = reader({ filePreview: 'ow365', owId: 'synthetic-viewer' })
  instance.unit = { coursePpt: 'aes:opaque_*-token,aess:secure_*-token' }
  const plain = new URL(instance.resources[0].url)
  const secure = new URL(instance.resources[1].url)
  assert.equal(plain.searchParams.get('furl'), 'opaque_*-token')
  assert.equal(plain.searchParams.has('ssl'), false)
  assert.equal(secure.searchParams.get('furl'), 'secure_*-token')
  assert.equal(secure.searchParams.get('ssl'), '1')
})

test('七牛相对 key 使用既有 CDN，已经解析的根路径保持原目标', () => {
  const instance = reader({ uploadType: 'qiniu', qiniuDomain: 'https://cdn.example' })
  instance.unit = { coursePpt: `role-flow/notes.txt,${staticDomain}/role-flow/legacy.txt` }
  assert.equal(instance.resources[0].url, 'https://cdn.example/role-flow/notes.txt')
  assert.equal(instance.resources[1].url, `${origin}${staticDomain}/role-flow/legacy.txt`)
})

test('Scratch 资料保留 create 场景并携带可访问的完整文件 URL', () => {
  const instance = reader()
  const file = `${staticDomain}/role-flow/a%20b.SB3?x=1&y=中文#part`
  instance.unit = { coursePpt: `${file},role-flow/other.sb3` }
  const link = new URL(instance.resources[0].url, origin)
  assert.equal(link.pathname, '/scratch3/index.html')
  assert.equal(link.searchParams.get('scene'), 'create')
  assert.equal(link.searchParams.get('queryEncoding'), 'uri')
  assert.equal(link.searchParams.get('workFile'), new URL(file, origin).href)
  assert.equal(new URL(instance.resources[1].url, origin).searchParams.get('workFile'), `${origin}${staticDomain}/role-flow/other.sb3`)
})

test('可执行和非 Web scheme 不被文件 helper 包装成可点击资料', () => {
  const instance = reader()
  instance.unit = { coursePpt: 'javascript:alert(1),data:text/html;base64;YWJj,file:///notes.txt,ftp://files.example/one.txt,javascript:example.sb3' }
  assert.equal(instance.resources.length, 5)
  for (const item of instance.resources) assert.equal(item.url, '')
})

test('预览配置异常只使该资料地址不可用，不阻止其他 Scratch 资料显示', () => {
  const instance = reader({ filePreview: 'kkfileview' })
  instance.unit = { coursePpt: `${staticDomain}/role-flow/notes.txt,${staticDomain}/role-flow/example.sb3` }
  assert.equal(instance.resources.length, 2)
  assert.equal(instance.resources[0].url, '')
  assert.equal(new URL(instance.resources[1].url, origin).searchParams.get('workFile'), `${origin}${staticDomain}/role-flow/example.sb3`)
})
