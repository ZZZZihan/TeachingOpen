const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const { test } = require('node:test')
const Vue = require('vue')
const compiler = require('vue-template-compiler')
const babel = require('@babel/core')
const source = file => fs.readFileSync(path.resolve(__dirname, '../src', file), 'utf8')
const run = (text, context = {}) => { vm.runInNewContext(text, context); return context }
const helpers = run(source('utils/studentWorkList.js').replace(/export /g, ''))
const paged = run(source('utils/loadPagedRecords.js').replace(/export /g, ''))
const filterObj = run(source('utils/util.js').match(/export function filterObj\(obj\) \{[\s\S]*?^}/m)[0].replace('export ', '')).filterObj
const stub = { render (h) { return h('div', this.$slots.default) } }
Vue.ls = { get: () => undefined }
const row = id => ({ id, workName: id, score: 0, teacherComment: '反馈', workType: '0' })
const ok = (records = [], total = records.length) => ({ success: true, result: { records, total } })
const deferred = () => { let settleResolve, settleReject; const promise = new Promise((resolve, reject) => { settleResolve = resolve; settleReject = reject }); return { promise, resolve: settleResolve, reject: settleReject } }
const failure = fields => Object.assign(new Error('synthetic transport failure'), fields)
const flush = () => new Promise(resolve => setImmediate(resolve))
const plain = value => JSON.parse(JSON.stringify(value))

function component (file, imports = {}) {
    const parsed = compiler.parseComponent(source(file))
    const context = run(parsed.script.content.replace(/^[ \t]*import .*$/gm, '').replace('export default', 'this.component ='), { ...helpers, ...paged, ...imports, window: { _CONFIG: { webURL: 'http://synthetic.invalid' } } })
    const compiled = compiler.compileToFunctions(parsed.template.content)
    return { ...context.component, render: compiled.render, staticRenderFns: compiled.staticRenderFns }
}
const State = component('components/teaching/StudentWorkListState.vue')
function nodes (vnode) {
    if (!vnode) return []
    return [vnode, ...(vnode.children || []).concat(vnode.componentOptions ? vnode.componentOptions.children || [] : []).flatMap(nodes)]
}
const byTestId = (tree, id) => nodes(tree).find(node => node.data && node.data.attrs && node.data.attrs['data-testid'] === id)
const content = tree => nodes(tree).map(node => node.text || '').join('')

function harness (entry, transport = () => Promise.resolve(ok()), initial = false) {
    const calls = []
    const getAction = (url, params) => {
        if (url.endsWith('/getWorkTags')) return Promise.resolve({ success: true, result: [] })
        calls.push({ url, params: plain(params) })
        return transport(params)
    }
    const mixinSource = source('mixins/JeecgListMixin.js').replace(/^import .*$/gm, '').replace('export const JeecgListMixin', 'this.JeecgListMixin')
    const mixinCode = babel.transformSync(mixinSource, { babelrc: false, configFile: false, envName: 'test', presets: [[require.resolve('@vue/babel-preset-app'), { useBuiltIns: false }]] }).code
    const mixin = run(mixinCode, { filterObj, Vue, ACCESS_TOKEN: 'unused-synthetic', getAction, deleteAction () {}, downFile () {}, getFileAccessHttpUrl: value => value, console: { log () {} } }).JeecgListMixin
    const imports = { getAction, deleteAction () {}, getFileAccessHttpUrl: value => value, QrCode: stub, JeecgListMixin: mixin, TeachingWorkPreviewModal: stub, JDictSelectTag: stub, JEllipsis: stub, StudentWorkFeedback: stub, StudentWorkListState: State }
    const options = component(entry === 'table' ? 'views/account/center/MineWorkList.vue' : 'views/account/center/page/MineWorks.vue', imports)
    const instance = new Vue({ ...options, data () { return { ...options.data.call(this), disableMixinCreated: !initial } } })
    return { instance, calls, options, load: (...args) => entry === 'table' ? instance.loadData(...args) : instance.getWorkList(), busy: () => entry === 'table' ? instance.listLoading : instance.loading }
}
function status (parent) {
    const vnode = nodes(parent._render()).find(node => node.componentOptions && node.componentOptions.Ctor.options.name === 'StudentWorkListState')
    assert.ok(vnode, 'actual parent renders actual status component')
    const state = new Vue({ ...State, propsData: vnode.componentOptions.propsData })
    let retry
    state.$on('retry', () => { retry = vnode.componentOptions.listeners.retry() })
    return { state, render: () => state._render(), clickRetry () { byTestId(state._render(), 'work-list-retry').data.on.click(); return retry } }
}

test('page contract accepts valid records and an empty page with a positive numeric total', () => {
    const records = [row('0')]
    assert.equal(helpers.studentWorkPage(ok(records)).records, records)
    assert.equal(helpers.studentWorkPage(ok([], 25)).total, 25)
    assert.equal(helpers.studentWorkPage(ok()).records.length, 0)
})
test('malformed page, records, rows and numeric total cannot masquerade as a successful empty list', () => {
    for (const response of [null, {}, { success: 'true', result: {} }, { success: false }, { success: true }, { success: true, result: null }, { success: true, result: { records: {} } }, ok([null]), ok([[]]), ok([{}]), ok([{ id: ' ' }]), ok([{ id: {} }]), ok([], '0'), ok([], null), ok([], -1), ok([], Infinity), ok([], 1.5)]) assert.throws(() => helpers.studentWorkPage(response))
})
test('safe errors never copy arbitrary server messages, stack or returned HTML', () => {
    for (const error of [{ message: '<script>private()</script>', stack: 'private' }, { response: { status: 500, data: { message: 'private' } } }, { code: 'ECONNABORTED' }]) assert.doesNotMatch(helpers.studentWorkListError(error), /private|script|stack/)
    assert.match(helpers.studentWorkListError({ code: 'ECONNABORTED' }), /超时/)
    assert.match(helpers.studentWorkListError({ response: { status: 500 } }), /暂时不可用/)
    try { helpers.studentWorkPage({ success: false, code: 510, message: 'private' }) } catch (error) { assert.match(helpers.studentWorkListError(error), /访问权限/); assert.doesNotMatch(helpers.studentWorkListError(error), /private/) }
})
test('status branches give loading priority and retain native retry events and plain text', () => {
    const state = new Vue({ ...State, propsData: { loading: true, error: 'error', empty: true } })
    assert.ok(byTestId(state._render(), 'work-list-loading'))
    assert.equal(byTestId(state._render(), 'work-list-error'), undefined)
    assert.equal(byTestId(state._render(), 'work-list-empty'), undefined)
    state.loading = false
    state.error = '<b>literal text</b>'
    let retries = 0
    state.$on('retry', () => { retries++ })
    const button = byTestId(state._render(), 'work-list-retry')
    assert.equal(button.tag, 'button')
    assert.equal(button.data.attrs.type, 'button')
    button.data.on.click()
    assert.equal(retries, 1)
    assert.match(content(state._render()), /<b>literal text<\/b>/)
    assert.equal(nodes(state._render()).some(node => node.data && node.data.domProps && node.data.domProps.innerHTML), false)
    state.$destroy()
})

for (const entry of ['table', 'card']) {
    test(`${entry}: start hides previous results, success releases loading and renders fresh records`, async () => {
        const pending = deferred(); const h = harness(entry, () => pending.promise)
        Object.assign(h.instance, { dataSource: [row('old')], listError: 'old error', listReady: true })
        const request = h.load()
        assert.equal(h.busy(), true)
        assert.equal(h.instance.dataSource.length, 0)
        assert.equal(h.instance.listReady, false)
        assert.equal(h.instance.listError, '')
        const current = status(h.instance)
        assert.ok(byTestId(current.render(), 'work-list-loading'))
        assert.equal(byTestId(current.render(), 'work-list-empty'), undefined)
        pending.resolve(ok([row('fresh')], entry === 'table' ? 25 : 1)); await request
        assert.equal(h.busy(), false)
        assert.equal(h.instance.listReady, true)
        assert.equal(h.instance.dataSource[0].id, 'fresh')
        current.state.$destroy(); h.instance.$destroy()
    })
    test(`${entry}: network, HTTP500, timeout, business false and malformed results release loading with retry`, async () => {
        const outcomes = [() => Promise.reject(failure({ isAxiosError: true })), () => Promise.reject(failure({ response: { status: 500, data: { message: 'private' } } })), () => Promise.reject(failure({ code: 'ECONNABORTED' })), () => Promise.resolve({ success: false, code: 510, message: 'private' }), () => Promise.resolve({ success: false, message: 'private' }), () => Promise.resolve(ok([null])), () => Promise.resolve({ success: true, result: { records: {} } })]
        for (const outcome of outcomes) {
            const h = harness(entry, outcome)
            h.instance.dataSource = [row('old')]
            await h.load()
            assert.equal(h.busy(), false)
            assert.equal(h.instance.listReady, false)
            assert.equal(h.instance.dataSource.length, 0)
            assert.ok(h.instance.listError)
            const current = status(h.instance)
            assert.ok(byTestId(current.render(), 'work-list-error'))
            assert.ok(byTestId(current.render(), 'work-list-retry'))
            assert.equal(byTestId(current.render(), 'work-list-empty'), undefined)
            assert.doesNotMatch(content(current.render()), /private/)
            current.state.$destroy(); h.instance.$destroy()
        }
    })
    test(`${entry}: successful empty response has explicit empty state and no error or loading`, async () => {
        const h = harness(entry)
        await h.load()
        const current = status(h.instance)
        assert.ok(byTestId(current.render(), 'work-list-empty'))
        assert.equal(byTestId(current.render(), 'work-list-error'), undefined)
        assert.equal(byTestId(current.render(), 'work-list-loading'), undefined)
        current.state.$destroy(); h.instance.$destroy()
    })
    for (const oldFails of [false, true]) {
        test(`${entry}: old ${oldFails ? 'failure' : 'success'} and finally cannot clear a pending newer request`, async () => {
            const requests = []; const h = harness(entry, () => { const d = deferred(); requests.push(d); return d.promise })
            const old = h.load(); const current = h.load()
            oldFails ? requests[0].reject({ isAxiosError: true }) : requests[0].resolve(ok([row('old')]))
            await old
            assert.equal(h.busy(), true)
            assert.equal(h.instance.listError, '')
            assert.equal(h.instance.dataSource.length, 0)
            requests[1].resolve(ok([row('new')])); await current
            assert.equal(h.instance.dataSource[0].id, 'new')
            assert.equal(h.busy(), false)
            h.instance.$destroy()
        })
        test(`${entry}: old ${oldFails ? 'failure' : 'success'} arriving after new success cannot overwrite it`, async () => {
            const requests = []; const h = harness(entry, () => { const d = deferred(); requests.push(d); return d.promise })
            const old = h.load(); const current = h.load()
            requests[1].resolve(ok([row('new')])); await current
            oldFails ? requests[0].reject({ isAxiosError: true }) : requests[0].resolve(ok([row('old')]))
            await old
            assert.equal(h.instance.dataSource[0].id, 'new')
            assert.equal(h.instance.listError, '')
            assert.equal(h.busy(), false)
            h.instance.$destroy()
        })
    }
    test(`${entry}: current failure remains visible when an older success arrives`, async () => {
        const requests = []; const h = harness(entry, () => { const d = deferred(); requests.push(d); return d.promise })
        const old = h.load(); const current = h.load()
        requests[1].reject({ response: { status: 500 } }); await current
        const error = h.instance.listError
        requests[0].resolve(ok([row('old')])); await old
        assert.equal(h.instance.listError, error)
        assert.equal(h.instance.dataSource.length, 0)
        assert.equal(h.busy(), false)
        h.instance.$destroy()
    })
    test(`${entry}: destroyed instances ignore late success/failure and refuse another request`, async () => {
        for (const reject of [false, true]) {
            const d = deferred(); const h = harness(entry, () => d.promise)
            const request = h.load(); h.instance.$destroy()
            const state = plain({ data: h.instance.dataSource, error: h.instance.listError, busy: h.busy(), ready: h.instance.listReady })
            reject ? d.reject({ isAxiosError: true }) : d.resolve(ok([row('late')]))
            await request; await h.load()
            assert.deepEqual(plain({ data: h.instance.dataSource, error: h.instance.listError, busy: h.busy(), ready: h.instance.listReady }), state)
            assert.equal(h.calls.length, 1)
        }
    })
}

test('table native retry repeats failed applied query/page snapshot, ignoring unsubmitted edits', async () => {
    let fail = true
    const h = harness('table', () => fail ? Promise.reject(failure({ isAxiosError: true })) : Promise.resolve(ok([row('restored')], 100)))
    h.instance.queryParam = { workName: 'applied', workType: '4' }
    h.instance.filters = { categories: ['applied'] }
    h.instance.isorter = { column: 'viewNum', order: 'asc' }
    h.instance.ipagination.current = 3; h.instance.ipagination.pageSize = 20
    await h.load()
    const sent = h.calls[0].params
    h.instance.queryParam.workName = 'draft only'
    h.instance.filters.categories.push('draft only')
    h.instance.ipagination.current = 7; h.instance.ipagination.pageSize = 30
    fail = false
    const current = status(h.instance)
    const retry = current.clickRetry()
    assert.equal(h.instance.listError, '')
    assert.equal(h.busy(), true)
    assert.deepEqual(h.calls[1].params, sent)
    assert.equal(h.instance.queryParam.workName, 'draft only')
    assert.equal(h.instance.ipagination.current, 3)
    assert.equal(h.instance.ipagination.pageSize, 20)
    await retry
    assert.equal(h.instance.dataSource[0].id, 'restored')
    assert.equal(h.busy(), false)
    current.state.$destroy(); h.instance.$destroy()
})
test('new explicit table query applies drafts, resets page only when requested and replaces retry snapshot', async () => {
    const h = harness('table', () => Promise.reject(failure({ isAxiosError: true })))
    h.instance.queryParam = { workName: 'first' }; h.instance.ipagination.current = 4
    await h.load()
    h.instance.queryParam.workName = 'second'
    await h.load(1)
    assert.equal(h.calls[1].params.workName, 'second')
    assert.equal(h.calls[1].params.pageNo, 1)
    assert.deepEqual(plain(h.instance.lastListParams), h.calls[1].params)
    h.instance.$destroy()
})
test('table list loading survives unrelated shared loading cleanup and duplicate retry is blocked', async () => {
    const d = deferred(); const h = harness('table', () => d.promise)
    const pending = h.load()
    h.instance.loading = false
    assert.equal(h.instance.listLoading, true)
    const current = status(h.instance)
    assert.ok(byTestId(current.render(), 'work-list-loading'))
    await h.instance.retryList()
    assert.equal(h.calls.length, 1)
    d.resolve(ok()); await pending
    assert.equal(h.instance.listLoading, false)
    current.state.$destroy(); h.instance.$destroy()
})
test('table remains rendered during loading and failure so AntD deferred pagination retains its refs', async () => {
    const d = deferred(); const h = harness('table', () => d.promise)
    const table = () => nodes(h.instance._render()).find(node => node.tag === 'a-table')
    const pending = h.load()
    assert.ok(table(), 'table instance is retained while hidden')
    assert.equal(table().data.directives.find(directive => directive.name === 'show').value, false)
    d.reject({ isAxiosError: true }); await pending
    assert.ok(table(), 'table instance is retained after failure')
    assert.equal(table().data.directives.find(directive => directive.name === 'show').value, false)
    h.instance.$destroy()
})
test('valid empty table page retains actual pagination and its real mixin navigation request', async () => {
    const h = harness('table', () => Promise.resolve(ok([], 25)))
    h.instance.ipagination.current = 3
    await h.load()
    const tree = h.instance._render()
    const table = nodes(tree).find(node => node.tag === 'a-table')
    assert.ok(table)
    assert.equal(table.data.attrs.pagination.current, 3)
    assert.equal(table.data.attrs.pagination.total, 25)
    const current = status(h.instance)
    assert.match(content(current.render()), /当前页暂无作品/)
    h.instance.handleTableChange({ ...h.instance.ipagination, current: 2 }, {}, {})
    await flush()
    assert.equal(h.calls[1].params.pageNo, 2)
    current.state.$destroy(); h.instance.$destroy()
})
test('actual table creation and card mounted hook wire their existing request contracts', async () => {
    const table = harness('table', () => Promise.resolve(ok()), true)
    await flush()
    assert.equal(table.calls.length, 1)
    assert.equal(table.calls[0].params.pageNo, 1)
    assert.equal(table.calls[0].params.pageSize, 10)
    const card = harness('card')
    card.instance.$options.mounted[0].call(card.instance)
    await flush()
    assert.equal(card.calls.length, 1)
    assert.deepEqual(card.calls[0].params, { pageNo: 1, pageSize: 100 })
    const Index = component('views/account/center/Index.vue', { PageLayout: stub, RouteView: stub, MineWorksPage: card.options, mapGetters: () => ({}), getFileAccessHttpUrl: value => value })
    const index = new Vue(Index)
    assert.ok(nodes(index._render()).some(node => node.componentOptions && node.componentOptions.Ctor.options.name === 'MineWorksCard'))
    table.instance.$destroy(); card.instance.$destroy(); index.$destroy()
})

test('actual cards load all 101 works before rendering any cards', async () => {
    const second = deferred()
    const records = Array.from({ length: 101 }, (_, index) => row(`work-${index}`))
    const h = harness('card', params => params.pageNo === 1 ? Promise.resolve(ok(records.slice(0, 100), 101)) : second.promise)
    const pending = h.load()
    await flush()
    assert.deepEqual(h.calls.map(call => call.params), [{ pageNo: 1, pageSize: 100 }, { pageNo: 2, pageSize: 100 }])
    assert.equal(h.busy(), true)
    assert.equal(h.instance.dataSource.length, 0)
    assert.equal(nodes(h.instance._render()).filter(node => node.tag === 'a-card').length, 0)
    second.resolve(ok(records.slice(100), 101)); await pending
    assert.deepEqual(plain(h.instance.dataSource).map(item => item.id), records.map(item => item.id))
    const cards = nodes(h.instance._render()).filter(node => node.tag === 'a-card')
    assert.equal(cards.length, 101)
    assert.equal(cards[100].key, 'work-100')
    assert.equal(h.instance.listReady, true)
    assert.equal(h.busy(), false)
    h.instance.$destroy()
})

test('actual card late empty page rejects partial results and native retry starts again from page one', async () => {
    let repaired = false
    const records = Array.from({ length: 101 }, (_, index) => row(`work-${index}`))
    const h = harness('card', params => Promise.resolve(ok(params.pageNo === 1 ? records.slice(0, 100) : repaired ? records.slice(100) : [], 101)))
    await h.load()
    assert.equal(h.instance.dataSource.length, 0)
    assert.equal(h.instance.listReady, false)
    assert.equal(h.busy(), false)
    const current = status(h.instance)
    assert.ok(byTestId(current.render(), 'work-list-error'))
    assert.match(content(current.render()), /不完整/)
    repaired = true
    await current.clickRetry()
    assert.deepEqual(h.calls.map(call => call.params.pageNo), [1, 2, 1, 2])
    assert.equal(h.instance.dataSource.length, 101)
    assert.equal(h.instance.listError, '')
    current.state.$destroy(); h.instance.$destroy()
})

test('actual card second-page transport or business failure never displays the first 100 works', async () => {
    const first = Array.from({ length: 100 }, (_, index) => row(`work-${index}`))
    for (const outcome of [() => Promise.reject(failure({ isAxiosError: true })), () => Promise.resolve({ success: false, message: 'private' })]) {
        const h = harness('card', params => params.pageNo === 1 ? Promise.resolve(ok(first, 101)) : outcome())
        await h.load()
        assert.equal(h.instance.dataSource.length, 0)
        assert.equal(h.instance.listReady, false)
        assert.equal(h.busy(), false)
        assert.ok(h.instance.listError)
        assert.doesNotMatch(h.instance.listError, /private/)
        assert.equal(h.calls.length, 2)
        h.instance.$destroy()
    }
})

for (const oldFails of [false, true]) {
    test(`actual card old second-page ${oldFails ? 'failure' : 'success'} cannot end or overwrite a newer complete-list request`, async () => {
        const requests = []
        const h = harness('card', () => { const pending = deferred(); requests.push(pending); return pending.promise })
        const old = h.load()
        requests[0].resolve(ok(Array.from({ length: 100 }, (_, index) => row(`old-${index}`)), 201))
        await flush()
        const current = h.load()
        oldFails ? requests[1].reject({ isAxiosError: true }) : requests[1].resolve(ok(Array.from({ length: 100 }, (_, index) => row(`old-${index + 100}`)), 201))
        await old
        assert.equal(h.calls.length, 3, 'stale pagination does not fetch its third page')
        assert.equal(h.busy(), true)
        assert.equal(h.instance.dataSource.length, 0)
        assert.equal(h.instance.listError, '')
        requests[2].resolve(ok([row('new')])); await current
        assert.deepEqual(plain(h.instance.dataSource).map(item => item.id), ['new'])
        assert.equal(h.busy(), false)
        h.instance.$destroy()
    })
}

test('actual card destroyed before first page completes does not request more pages', async () => {
    const pending = deferred()
    const h = harness('card', () => pending.promise)
    const request = h.load()
    h.instance.$destroy()
    pending.resolve(ok(Array.from({ length: 100 }, (_, index) => row(`late-${index}`)), 101))
    await request
    assert.equal(h.calls.length, 1)
    assert.equal(h.instance.dataSource.length, 0)
})
