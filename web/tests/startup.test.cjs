const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { resolve } = require('node:path')
const { test } = require('node:test')
const vm = require('node:vm')

// Run the actual startup block with controlled APIs and a minimal browser surface.
function startupHarness (cached = {}) {
  const elements = new Map()
  const element = tag => ({ tag, children: [], textContent: '', disabled: false,
    appendChild (child) { this.children.push(child) },
    setAttribute () {},
    addEventListener (event, fn) { this[event] = fn },
    remove () { this.removed = true }
  })
  elements.set('app', element('div'))
  elements.set('loader-wrapper', element('div'))
  const cache = { ...cached }
  const calls = { config: [], menu: [] }
  const requests = name => () => new Promise((resolve, reject) => calls[name].push({ resolve, reject }))
  const commits = []
  let mounts = 0
  function Vue (options) { options.created(); options.mounted(); this.$mount = () => { mounts++ } }
  Vue.ls = { get: key => cache[key], set: (key, value) => { cache[key] = value }, remove: key => { delete cache[key] } }
  const store = { getters: {}, commit: (...args) => commits.push(args) }
  Object.defineProperties(store.getters, {
    sysConfig: { get: () => cache.SYS_CONFIG },
    menuList: { get: () => cache.MENU }
  })
  const document = { title: '', head: element('head'),
    getElementById: id => elements.get(id), createElement: element }
  const timers = new Map()
  let timerId = 0
  const context = { setTimeout: (fn, ms) => { timers.set(++timerId, { fn, ms }); return timerId },
    clearTimeout: id => timers.delete(id), Vue, store, router: {}, App: {}, window: { document }, document,
    getSysConfig: requests('config'), getMenu: requests('menu'),
    console, config: {}, SYS_CONFIG: 'SYS_CONFIG', MENU: 'MENU' }
  for (const name of ['SIDEBAR_TYPE', 'DEFAULT_THEME', 'DEFAULT_LAYOUT_MODE', 'DEFAULT_FIXED_HEADER',
    'DEFAULT_FIXED_SIDEMENU', 'DEFAULT_CONTENT_WIDTH_TYPE', 'DEFAULT_FIXED_HEADER_HIDDEN',
    'DEFAULT_COLOR_WEAK', 'DEFAULT_COLOR', 'ACCESS_TOKEN', 'DEFAULT_MULTI_PAGE']) context[name] = name
  vm.createContext(context)
  try {
    const helper = readFileSync(resolve(__dirname, '../src/utils/startup.js'), 'utf8').replace(/export /g, '')
    vm.runInContext(helper, context)
  } catch (error) { if (error.code !== 'ENOENT') throw error }
    const branding = readFileSync(resolve(__dirname, '../src/utils/platformBranding.js'), 'utf8').replace(/export /g, '')
    vm.runInContext(branding, context)
  const source = readFileSync(resolve(__dirname, '../src/main.js'), 'utf8')
  const block = source.slice(source.indexOf('let cacheTime'))
    .replace(/start\(\)\s*$/, 'this.start = start')
  vm.runInContext(block, context)
  return { context, calls, cache, commits, elements, timers,
    expire: () => { for (const timer of Array.from(timers.values())) timer.fn() }, get mounts () { return mounts } }
}
const flush = () => new Promise(resolve => setImmediate(resolve))
const success = result => ({ success: true, result })
const config = { brandName: '测试教学平台', uploadType: 'local', staticDomain: '/files' }
const menu = [{ title: '课程', url: '/courseList' }]

async function answer (h, configReply, menuReply) {
  await flush()
  for (const [name, reply] of [['config', configReply], ['menu', menuReply]]) {
    for (const request of h.calls[name]) {
      if (reply instanceof Error) request.reject(reply)
      else request.resolve(reply)
    }
    await flush()
  }
}

test('首次配置请求失败显示恢复入口，恢复后只挂载一次', async () => {
  const h = startupHarness()
  const first = h.context.start()
  // Attach assertion immediately so the original rejected promise is observed.
  const completed = assert.doesNotReject(first)
  await answer(h, new Error('offline'), success(menu))
  await completed
  assert.equal(h.mounts, 0)
  const retry = h.elements.get('app').children.find(e => e.tag === 'button')
  assert.ok(retry, '应提供重新加载按钮')
  const second = retry.click()
  await answer(h, success(config), success(menu))
  await second
  assert.equal(h.mounts, 1)
  await h.context.start()
  assert.equal(h.mounts, 1)
})

test('首次菜单请求失败可重试，失败结果不写入缓存', async () => {
  const h = startupHarness()
  const pending = assert.doesNotReject(h.context.start())
  await answer(h, success(config), new Error('offline'))
  await pending
  assert.equal(h.mounts, 0)
  assert.equal(h.cache.MENU, undefined)
  assert.ok(h.elements.get('app').children.some(e => e.tag === 'button'))
})

test('业务失败和格式错误不会挂载或污染已有缓存', async () => {
  for (const bad of [{ success: false, result: config }, success(null), success([])]) {
    const h = startupHarness()
    const pending = assert.doesNotReject(h.context.start())
    await answer(h, bad, success(menu))
    await pending
    assert.equal(h.mounts, 0)
    assert.equal(h.cache.SYS_CONFIG, undefined)
  }
})

test('正常首次启动并发加载配置和菜单，空菜单也有效', async () => {
  const h = startupHarness()
  const pending = h.context.start()
  await flush()
  assert.equal(h.calls.config.length, 1)
  assert.equal(h.calls.menu.length, 1)
  h.calls.menu[0].resolve(success([]))
  h.calls.config[0].resolve(success(config))
  await pending
  assert.equal(h.mounts, 1)
  assert.equal(h.context.window.document.title, config.brandName)
  assert.deepEqual(Array.from(h.cache.MENU), [])
})

test('有效缓存立即挂载，刷新失败被处理并保留缓存', async () => {
  const h = startupHarness({ SYS_CONFIG: config, MENU: menu })
  await h.context.start()
  assert.equal(h.mounts, 1)
  await answer(h, new Error('offline'), { success: false, result: null })
  assert.equal(h.cache.SYS_CONFIG, config)
  assert.equal(h.cache.MENU, menu)
})

test('只有配置缓存时等待菜单，菜单失败仍显示恢复入口', async () => {
  const h = startupHarness({ SYS_CONFIG: config })
  const pending = assert.doesNotReject(h.context.start())
  await answer(h, new Error('offline'), success(null))
  await pending
  assert.equal(h.mounts, 0)
  assert.equal(h.cache.SYS_CONFIG, config)
})

test('重复触发启动不会发送重复的首次请求', async () => {
  const h = startupHarness()
  const first = h.context.start()
  const duplicate = h.context.start()
  await answer(h, success(config), success(menu))
  await Promise.all([first, duplicate])
  assert.equal(h.calls.config.length, 1)
  assert.equal(h.calls.menu.length, 1)
  assert.equal(h.mounts, 1)
})


test('冷启动请求在15秒期限后显示错误，迟到响应不能写缓存', async () => {
  const h = startupHarness()
  const pending = h.context.start()
  await flush()
  assert.ok(Array.from(h.timers.values()).every(timer => timer.ms === 15000))
  h.expire()
  await pending
  assert.equal(h.mounts, 0)
  await answer(h, success(config), success(menu))
  assert.equal(h.cache.SYS_CONFIG, undefined)
  assert.equal(h.cache.MENU, undefined)
  assert.ok(h.elements.get('app').children.some(e => e.tag === 'button'))
})

test('超时后重试恢复，旧请求迟到不覆盖新缓存', async () => {
  const h = startupHarness()
  const first = h.context.start()
  await flush()
  h.expire()
  await first
  const second = h.context.start()
  await flush()
  const freshConfig = { ...config, brandName: '新配置' }
  h.calls.config[1].resolve(success(freshConfig))
  h.calls.menu[1].resolve(success(menu))
  await second
  h.calls.config[0].resolve(success(config))
  h.calls.menu[0].resolve(success([{ title: '过期菜单' }]))
  await flush()
  assert.equal(h.mounts, 1)
  assert.equal(h.cache.SYS_CONFIG, freshConfig)
  assert.equal(h.cache.MENU, menu)
})

test('重试代次阻止旧的暖缓存刷新覆盖成功恢复的数据', async () => {
  const h = startupHarness({ SYS_CONFIG: config })
  const first = h.context.start()
  await flush()
  h.calls.menu[0].reject(new Error('offline'))
  await first
  const second = h.context.start()
  await flush()
  const freshConfig = { ...config, brandName: '新配置' }
  h.calls.config[1].resolve(success(freshConfig))
  h.calls.menu[1].resolve(success(menu))
  await second
  h.calls.config[0].resolve(success(config))
  await flush()
  assert.equal(h.mounts, 1)
  assert.equal(h.cache.SYS_CONFIG, freshConfig)
})

test('暖缓存刷新收到401或403时清除旧菜单，不当作网络故障保留', async () => {
  for (const status of [401, 403]) {
    const h = startupHarness({ SYS_CONFIG: config, MENU: menu })
    await h.context.start()
    const error = Object.assign(new Error('unauthorized'), { response: { status } })
    await answer(h, success(config), error)
    assert.equal(h.cache.MENU, undefined)
    assert.ok(h.commits.some(([type, value]) => type === 'SET_MENU' && value.length === 0))
  }
})

test('冷启动的业务未授权结果不能借旧菜单挂载', async () => {
  const h = startupHarness({ MENU: menu })
  const pending = h.context.start()
  await answer(h, { success: false, code: 403, result: null }, success(menu))
  await pending
  assert.equal(h.mounts, 0)
  assert.equal(h.cache.MENU, undefined)
})

test('暖缓存刷新超时保留有效数据，迟到响应不覆盖', async () => {
  const h = startupHarness({ SYS_CONFIG: config, MENU: menu })
  await h.context.start()
  h.expire()
  await flush()
  await answer(h, success({ brandName: '迟到' }), success([]))
  assert.equal(h.mounts, 1)
  assert.equal(h.cache.SYS_CONFIG, config)
  assert.equal(h.cache.MENU, menu)
})


test('配置成功与缓存菜单403同批交错时拒绝返回启动成功', async () => {
  const h = startupHarness()
  const denied = Object.assign(new Error('forbidden'), { response: { status: 403 } })
  const pending = h.context.loadStartupData({
    cachedMenu: menu, getConfig: () => Promise.resolve(success(config)),
    getMenu: () => Promise.reject(denied), saveConfig: () => {}, saveMenu: () => {}, clearMenu: () => {}
  })
  await assert.rejects(pending, /Startup/)
})

test('403撤销的菜单不是有效空缓存，重复重试仍须等待授权响应', async () => {
  const h = startupHarness()
  for (let attempt = 0; attempt < 2; attempt++) {
    const pending = h.context.start()
    await answer(h, success(config), Object.assign(new Error('forbidden'), { response: { status: 403 } }))
    await pending
    assert.equal(h.mounts, 0)
    assert.equal(h.cache.MENU, undefined)
  }
})

test('超时后同代迟到的HTTP401和业务403仍撤销暖菜单', async () => {
  for (const reply of [Object.assign(new Error('unauthorized'), { response: { status: 401 } }),
    { success: false, code: 403, result: null }]) {
    const h = startupHarness({ SYS_CONFIG: config, MENU: menu })
    await h.context.start()
    h.expire()
    await flush()
    await answer(h, success(config), reply)
    assert.equal(h.cache.MENU, undefined)
    assert.equal(h.mounts, 1)
  }
})

test('旧代迟到的401不撤销重试后取得的新菜单', async () => {
  const h = startupHarness({ SYS_CONFIG: config })
  const first = h.context.start()
  await flush()
  h.expire()
  await first
  const second = h.context.start()
  await flush()
  h.calls.config[1].resolve(success(config))
  h.calls.menu[1].resolve(success(menu))
  await second
  h.calls.menu[0].reject(Object.assign(new Error('unauthorized'), { response: { status: 401 } }))
  await flush()
  assert.equal(h.cache.MENU, menu)
  assert.equal(h.mounts, 1)
})

test('挂载前再次检查已经失效的启动结果', async () => {
  const h = startupHarness()
  h.context.loadStartupData = async () => ({ sysConfig: config, menu, isCurrent: () => false })
  await h.context.start()
  assert.equal(h.mounts, 0)
  assert.ok(h.elements.get('app').children.some(e => e.tag === 'button'))
})

test('真实启动对空白或非字符串品牌使用平台名称，保留有效自定义品牌', async () => {
    for (const [brandName, expected] of [
        [undefined, '天津工业大学 · 人工智能教学平台'],
        [' \n\t ', '天津工业大学 · 人工智能教学平台'],
        [42, '天津工业大学 · 人工智能教学平台'],
        [{ name: '不应隐式转换' }, '天津工业大学 · 人工智能教学平台'],
        ['  自定义课堂  ', '自定义课堂']
    ]) {
        const h = startupHarness()
        const pending = h.context.start()
        await answer(h, success({ ...config, brandName }), success(menu))
        await pending
        assert.equal(h.mounts, 1)
        assert.equal(h.context.window.document.title, expected)
    }
})
