const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { execFileSync } = require('node:child_process')
const { resolve } = require('node:path')
const { test } = require('node:test')
const vm = require('node:vm')

const root = resolve(__dirname, '..')
const source = process.env.SOURCE_REF
    ? execFileSync('git', ['show', process.env.SOURCE_REF + ':web/src/components/tools/setting.js'], { cwd: root, encoding: 'utf8' })
    : readFileSync(resolve(root, 'src/components/tools/setting.js'), 'utf8')
const purple = '#722ED1'
const green = '#13C2C2'
const blue = '#146fc2'

function deferred () {
    let resolvePromise
    let rejectPromise
    const promise = new Promise((resolve, reject) => { resolvePromise = resolve; rejectPromise = reject })
    return { promise, resolve: resolvePromise, reject: rejectPromise }
}

// All I/O stays behind explicit gates. Drain promise callbacks without timers or
// real network access so tests choose the bootstrap and compilation completion order.
async function flush () {
    for (let turn = 0; turn < 20; turn++) await Promise.resolve()
}

function harness () {
    const loading = []
    const errors = []
    const appended = []
    const context = { window: {}, console: { info () {} } }
    const body = {
        children: [],
        classList: { add () {}, remove () {} },
        appendChild (node) {
            this.children.push(node)
            appended.push(node)
            node.parentNode = this
            if (node.tagName === 'SCRIPT' && !node.src && node.innerHTML) {
                vm.runInNewContext(node.innerHTML, context)
            }
            return node
        },
        removeChild (node) {
            const index = this.children.indexOf(node)
            assert.ok(index >= 0, 'only attached nodes can be removed')
            this.children.splice(index, 1)
            node.parentNode = null
            return node
        }
    }
    context.document = {
        body,
        createElement (tag) {
            return {
                tagName: tag.toUpperCase(), parentNode: null, innerHTML: '',
                setAttribute (key, value) { this[key] = value },
                remove () { if (this.parentNode) this.parentNode.removeChild(this) }
            }
        }
    }
    context.message = {
        loading () {
            const notice = { closes: 0 }
            loading.push(notice)
            return () => { notice.closes++ }
        },
        error: value => errors.push(value)
    }
    vm.runInNewContext(source.replace(/^\s*import [^\n]+$/gm, '').replace(/export \{[^}]+\}/, '') +
        '\nthis.updateTheme = updateTheme', context)

    function request (color) {
        const result = context.updateTheme(color)
        assert.ok(result && typeof result.then === 'function', 'each valid request returns its completion promise')
        return result
    }

    function activeScript () {
        const scripts = body.children.filter(node => node.tagName === 'SCRIPT' && node.src)
        assert.equal(scripts.length, 1, 'one active Less compiler script')
        return scripts[0]
    }

    function runtime () {
        const bootstrap = deferred()
        const state = { currentColor: null, bootstrapFinished: false, bootstrapOverlaps: 0, active: 0, maxActive: 0, calls: [] }
        const pageLoadFinished = bootstrap.promise.then(() => {
            state.currentColor = blue
            state.bootstrapFinished = true
        })
        const less = {
            pageLoadFinished,
            modifyVars (variables) {
                const compilation = deferred()
                const color = variables['@primary-color']
                state.active++
                state.maxActive = Math.max(state.maxActive, state.active)
                if (!state.bootstrapFinished) state.bootstrapOverlaps++
                state.calls.push({ color, ...compilation })
                return compilation.promise.then(() => { state.currentColor = color }).finally(() => { state.active-- })
            }
        }
        return { bootstrap, state, less }
    }

    function load (script, compiler) {
        context.window.less = compiler.less
        assert.equal(typeof script.onload, 'function')
        script.onload()
    }

    function allClosed () {
        assert.ok(loading.length > 0)
        assert.deepEqual(loading.map(notice => notice.closes), loading.map(() => 1), 'every loading notice closes exactly once')
    }

    return { body, appended, loading, errors, runtime, request, activeScript, load, allClosed,
        updateTheme: context.updateTheme, context }
}

async function finish (compiler, index, color) {
    await flush()
    assert.equal(compiler.state.calls.length, index + 1, 'next compilation starts only after the preceding one settles')
    assert.equal(compiler.state.calls[index].color, color)
    assert.equal(compiler.state.active, 1)
    compiler.state.calls[index].resolve()
    await flush()
}

async function loadedHarness () {
    const h = harness()
    const initial = h.request(blue)
    await flush()
    const compiler = h.runtime()
    h.load(h.activeScript(), compiler)
    compiler.bootstrap.resolve()
    await finish(compiler, 0, blue)
    await initial
    return { h, compiler }
}

test('首次保存的紫色等待 Less 初始刷新，默认刷新不会覆盖已保存主题', async () => {
    const h = harness()
    const requested = h.updateTheme(purple)
    await flush()
    const compiler = h.runtime()
    h.load(h.activeScript(), compiler)
    await flush()
    assert.equal(compiler.state.calls.length, 0, 'onload cannot modify variables before pageLoadFinished')
    assert.equal(h.loading[0].closes, 0, 'loading stays visible while the bootstrap is pending')
    compiler.bootstrap.resolve()
    await finish(compiler, 0, purple)
    assert.ok(requested && typeof requested.then === 'function')
    await requested
    assert.equal(compiler.state.currentColor, purple)
    assert.equal(compiler.state.bootstrapOverlaps, 0)
    assert.equal(compiler.state.maxActive, 1)
    assert.equal(h.errors.length, 0)
    h.allClosed()
})

test('脚本加载前连续选择不同颜色，按请求顺序串行编译且最终颜色为最后选择', async () => {
    const h = harness()
    const requests = [h.request(purple), h.request(green), h.request(blue)]
    await flush()
    assert.equal(h.appended.filter(node => node.src).length, 1, 'queued requests share one script bootstrap')
    const compiler = h.runtime()
    h.load(h.activeScript(), compiler)
    await flush()
    assert.equal(compiler.state.calls.length, 0)
    compiler.bootstrap.resolve()
    await finish(compiler, 0, purple)
    await finish(compiler, 1, green)
    await finish(compiler, 2, blue)
    await Promise.all(requests)
    assert.equal(compiler.state.currentColor, blue)
    assert.equal(compiler.state.bootstrapOverlaps, 0)
    assert.equal(compiler.state.maxActive, 1)
    assert.equal(h.errors.length, 0)
    h.allClosed()
})

test('编译器加载后快速连续切色仍无并发 modifyVars，最后选择最终生效', async () => {
    const { h, compiler } = await loadedHarness()
    const requests = [h.request(purple), h.request(green), h.request('#F5222D')]
    await finish(compiler, 1, purple)
    await finish(compiler, 2, green)
    await finish(compiler, 3, '#F5222D')
    await Promise.all(requests)
    assert.equal(compiler.state.currentColor, '#F5222D')
    assert.equal(compiler.state.maxActive, 1)
    assert.equal(h.appended.filter(node => node.src).length, 1)
    h.allClosed()
})

test('一次 modifyVars 失败不会堵住已排队的新选择，失败提示和所有 loading 均收起', async () => {
    const { h, compiler } = await loadedHarness()
    const failed = h.request(purple)
    const recovered = h.request(green)
    await flush()
    assert.equal(compiler.state.calls.length, 2)
    compiler.state.calls[1].reject(new Error('synthetic compilation failure'))
    await failed
    assert.equal(h.errors.length, 1)
    assert.equal(compiler.state.currentColor, blue, 'a failed build does not publish its theme')
    await finish(compiler, 2, green)
    await recovered
    assert.equal(compiler.state.currentColor, green)
    assert.equal(compiler.state.maxActive, 1)
    h.allClosed()
})

test('脚本加载错误清理旧节点，下一次选择重新加载编译器并成功应用颜色', async () => {
    const h = harness()
    const failed = h.request(purple)
    await flush()
    const failedScript = h.activeScript()
    const failedNodes = [...h.body.children]
    failedScript.onerror(new Error('synthetic script loading failure'))
    await failed
    assert.equal(h.body.children.length, 0)
    assert.ok(failedNodes.every(node => node.parentNode === null))
    assert.equal(h.errors.length, 1)
    const recovered = h.request(green)
    await flush()
    const retryScript = h.activeScript()
    assert.notEqual(retryScript, failedScript)
    const compiler = h.runtime()
    h.load(retryScript, compiler)
    compiler.bootstrap.resolve()
    await finish(compiler, 0, green)
    await recovered
    assert.equal(h.appended.filter(node => node.src).length, 2)
    assert.equal(compiler.state.currentColor, green)
    h.allClosed()
})

// Some Less builds resolve pageLoadFinished even after stylesheet errors. This
// explicit rejection verifies the loader's defensive branch, not that upstream behavior.
test('pageLoadFinished 异常拒绝时清理并允许重试，不启动旧编译器（防御分支）', async () => {
    const h = harness()
    const failed = h.request(purple)
    await flush()
    const firstCompiler = h.runtime()
    h.load(h.activeScript(), firstCompiler)
    firstCompiler.bootstrap.reject(new Error('synthetic bootstrap failure'))
    await failed
    assert.equal(firstCompiler.state.calls.length, 0)
    assert.equal(h.body.children.length, 0)
    assert.equal(h.errors.length, 1)
    const recovered = h.request(green)
    await flush()
    const retryCompiler = h.runtime()
    h.load(h.activeScript(), retryCompiler)
    retryCompiler.bootstrap.resolve()
    await finish(retryCompiler, 0, green)
    await recovered
    assert.equal(retryCompiler.state.currentColor, green)
    h.allClosed()
})

test('脚本加载后缺少 modifyVars 时报告失败并清理，后续选择仍能重试', async () => {
    const h = harness()
    const failed = h.request(purple)
    await flush()
    h.context.window.less = {}
    h.activeScript().onload()
    await failed
    assert.equal(h.body.children.length, 0)
    assert.equal(h.errors.length, 1)
    const recovered = h.request(green)
    await flush()
    const compiler = h.runtime()
    h.load(h.activeScript(), compiler)
    compiler.bootstrap.resolve()
    await finish(compiler, 0, green)
    await recovered
    assert.equal(compiler.state.currentColor, green)
    h.allClosed()
})
