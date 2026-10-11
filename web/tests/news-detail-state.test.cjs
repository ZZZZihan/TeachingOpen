const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { resolve } = require('node:path')
const { test } = require('node:test')
const vm = require('node:vm')
const Vue = require('vue')
const compiler = require('vue-template-compiler')

const source = readFileSync(resolve(__dirname, '../src/views/home/NewsDetail.vue'), 'utf8')
const article = (id, title = '资讯 ' + id) => ({ id, newsTitle: title, newsContent: '<p>正文 ' + id + '</p>', createTime: '2026-10-11' })

function detail(id = 'first') {
  const requests = []
  const context = {
    getAction: (url, params) => new Promise((resolve, reject) => requests.push({ url, params, resolve, reject })),
    sanitizeRichText: value => value || ''
  }
  vm.runInNewContext(source.match(/<script>([\s\S]*?)<\/script>/)[1]
    .replace(/^import .*$/gm, '').replace('export default', 'this.component ='), context)
  const component = context.component
  const instance = { ...component.data(), $route: { query: { id } } }
  Object.entries(component.methods).forEach(([name, method]) => { instance[name] = method.bind(instance) })
  const navigate = next => {
    instance.$route = { query: { id: next } }
    return component.watch['$route.query.id'].call(instance)
  }
  return { instance, component, requests, navigate }
}

test('加载新路由立即清空旧资讯，成功只展示当前记录并结束加载', async () => {
  const h = detail('next & id')
  h.instance.cmsInfo = article('old')
  const pending = h.instance.getCmsDetail()
  assert.equal(h.instance.cmsInfo, null)
  assert.equal(h.instance.loading, true)
  assert.equal(h.instance.error, false)
  assert.equal(h.requests[0].url, '/teaching/teachingNews/newsDetail')
  assert.equal(h.requests[0].params.id, 'next & id')
  h.requests[0].resolve({ success: true, result: article('next & id') })
  await pending
  assert.equal(h.instance.cmsInfo.id, 'next & id')
  assert.equal(h.instance.loading, false)
  assert.equal(h.instance.error, false)
})

test('业务失败、网络失败及损坏响应均清空旧文，重试成功可恢复', async () => {
  for (const reply of [{ success: false }, null, new Error('offline'),
    { success: true, result: [] }, { success: true, result: 'invalid' },
    { success: true, result: { id: 'first' } }, { success: true, result: article('other') },
    { success: true, result: { ...article('first'), newsContent: {} } }]) {
    const h = detail()
    h.instance.cmsInfo = article('old')
    const failed = h.instance.getCmsDetail()
    if (reply instanceof Error) h.requests[0].reject(reply)
    else h.requests[0].resolve(reply)
    await failed
    assert.equal(h.instance.cmsInfo, null)
    assert.equal(h.instance.loading, false)
    assert.equal(h.instance.error, true)
    const retried = h.instance.getCmsDetail()
    assert.equal(h.instance.error, false)
    assert.equal(h.instance.loading, true)
    h.requests[1].resolve({ success: true, result: article('first') })
    await retried
    assert.equal(h.instance.cmsInfo.id, 'first')
    assert.equal(h.instance.loading, false)
    assert.equal(h.instance.error, false)
  }
})

test('最新请求的空结果显示空状态，空或非法路由 ID 不请求接口', async () => {
  for (const result of [null, undefined, {}]) {
    const h = detail()
    const pending = h.instance.getCmsDetail()
    h.requests[0].resolve({ success: true, result })
    await pending
    assert.equal(h.instance.cmsInfo, null)
    assert.equal(h.instance.loading, false)
    assert.equal(h.instance.error, false)
  }
  for (const id of [undefined, null, '', ' ', ['first', 'second']]) {
    const h = detail()
    h.instance.$route.query.id = id
    h.instance.cmsInfo = article('old')
    h.instance.getCmsDetail()
    assert.equal(h.requests.length, 0)
    assert.equal(h.instance.cmsInfo, null)
    assert.equal(h.instance.loading, false)
    assert.equal(h.instance.error, false)
  }
})

test('路由监听会开启新请求，所有迟到分支均不得结束新请求或覆盖当前内容', async () => {
  for (const reply of [{ success: true, result: article('first') }, { success: true, result: null },
    { success: false }, null, new Error('late offline'), { success: true, result: [] }]) {
    const h = detail()
    const old = h.instance.getCmsDetail()
    h.navigate('second')
    assert.equal(h.requests.length, 2)
    assert.equal(h.requests[1].params.id, 'second')
    if (reply instanceof Error) h.requests[0].reject(reply)
    else h.requests[0].resolve(reply)
    await old
    assert.equal(h.instance.cmsInfo, null)
    assert.equal(h.instance.loading, true)
    assert.equal(h.instance.error, false)
    h.requests[1].resolve({ success: true, result: article('second') })
    await new Promise(resolve => setImmediate(resolve))
    assert.equal(h.instance.cmsInfo.id, 'second')
    assert.equal(h.instance.loading, false)
    assert.equal(h.instance.error, false)
  }
})

test('最新结果成功、失败或为空后，旧成功均不能覆盖最新状态', async () => {
  for (const latest of [{ success: true, result: article('second') }, { success: false }, { success: true, result: null }, new Error('latest offline')]) {
    const h = detail()
    const old = h.instance.getCmsDetail()
    h.instance.$route.query.id = 'second'
    const next = h.instance.getCmsDetail()
    if (latest instanceof Error) h.requests[1].reject(latest)
    else h.requests[1].resolve(latest)
    await next
    const current = h.instance.cmsInfo
    const error = h.instance.error
    h.requests[0].resolve({ success: true, result: article('first') })
    await old
    assert.equal(h.instance.cmsInfo, current)
    assert.equal(h.instance.error, error)
    assert.equal(h.instance.loading, false)
  }
})

test('缺少 ID 的新路由及组件销毁会使在途请求的所有分支失效', async () => {
  for (const invalidate of [h => h.navigate(undefined), h => h.component.beforeDestroy.call(h.instance)]) {
    for (const reply of [{ success: true, result: article('first') }, { success: false }, { success: true, result: null }, new Error('offline')]) {
      const h = detail()
      const pending = h.instance.getCmsDetail()
      invalidate(h)
      const snapshot = { cmsInfo: h.instance.cmsInfo, loading: h.instance.loading, error: h.instance.error }
      if (reply instanceof Error) h.requests[0].reject(reply)
      else h.requests[0].resolve(reply)
      await pending
      assert.deepEqual({ cmsInfo: h.instance.cmsInfo, loading: h.instance.loading, error: h.instance.error }, snapshot)
    }
  }
})

test('实际 Vue 模板按加载、错误、空及成功状态互斥呈现，重试绑定当前加载方法', () => {
  const compiled = compiler.compile(compiler.parseComponent(source).template.content)
  assert.deepEqual(compiled.errors, [])
  const h = detail()
  const view = new Vue({ data: h.component.data, computed: h.component.computed, methods: h.component.methods,
    render: new Function(compiled.render), staticRenderFns: compiled.staticRenderFns.map(code => new Function(code)) })
  const nodes = tree => { const all = []; const visit = node => { all.push(node); (node.children || []).forEach(visit) }; visit(tree); return all }
  const text = tree => nodes(tree).map(node => node.text || '').join('')
  view.cmsInfo = article('old', '旧资讯')
  view.loading = true
  assert.match(text(view._render()), /正在加载资讯/)
  assert.doesNotMatch(text(view._render()), /旧资讯/)
  view.loading = false; view.error = true
  const failed = view._render()
  assert.match(text(failed), /资讯暂时无法加载/)
  assert.doesNotMatch(text(failed), /旧资讯/)
  const retry = nodes(failed).find(node => node.tag === 'a-button')
  assert.equal(retry.data.on.click, view.getCmsDetail)
  view.error = false; view.cmsInfo = null
  assert.match(text(view._render()), /未找到这篇资讯/)
  view.cmsInfo = article('first')
  assert.match(text(view._render()), /资讯 first/)
  const content = nodes(view._render()).find(node => node.data && node.data.domProps && node.data.domProps.innerHTML)
  assert.equal(content.data.domProps.innerHTML, '<p>正文 first</p>')
  view.$destroy()
})
