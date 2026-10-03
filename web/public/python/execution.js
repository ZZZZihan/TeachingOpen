/* Shared lifecycle for the existing editor and player. Authentication and persistence stay in the parent. */
(function (root) {
    'use strict'
    var CHANNEL = 'teaching-python-v1'
    var COMPUTE_MS = 30000
    var LOAD_MS = 10000
    var SESSION_MS = 300000
    var STOP_ACK_MS = 4000
    var MAX_CODE = 256000
    var MAX_TEXT = 2048
    var MAX_INPUT = 4096
    var MAX_OUTPUT_UNITS = 20001
    var active = null
    var pendingRun = null
    var runs = new Set()
    var lastState = 'idle'
    var controls = null
    var policyInstalled = false
    var scriptBase = new URL('.', root.document.currentScript.src).href

    function setState (state, text) {
        lastState = state
        if (active) active.state = state
        var node = root.document.getElementById('python-execution-status')
        if (node) { node.textContent = text; node.setAttribute('data-state', state) }
        var stop = root.document.getElementById('python-execution-stop')
        if (stop) stop.disabled = !active
    }
    function ensureControls (host) {
        if (controls && controls.parentNode) return
        controls = root.document.createElement('div')
        controls.id = 'python-execution-controls'
        controls.className = 'python-execution-controls'
        var status = root.document.createElement('span')
        status.id = 'python-execution-status'
        status.setAttribute('role', 'status')
        status.setAttribute('aria-live', 'polite')
        var stop = root.document.createElement('button')
        stop.id = 'python-execution-stop'
        stop.type = 'button'
        stop.textContent = '停止'
        stop.disabled = true
        stop.addEventListener('click', stopRun)
        var note = root.document.createElement('span')
        note.className = 'python-execution-note'
        note.textContent = '每次计算最长 30 秒；等待输入不计时。运行与绘图最多保留 5 分钟。'
        var form = root.document.createElement('form')
        form.id = 'python-execution-input-form'
        form.hidden = true
        var prompt = root.document.createElement('label')
        prompt.id = 'python-execution-input-prompt'
        prompt.htmlFor = 'python-execution-input'
        var input = root.document.createElement('input')
        input.id = 'python-execution-input'
        input.type = 'text'
        input.maxLength = MAX_INPUT
        input.autocomplete = 'off'
        input.setAttribute('aria-label', '程序输入')
        var submit = root.document.createElement('button')
        submit.type = 'submit'
        submit.textContent = '发送'
        var cancel = root.document.createElement('button')
        cancel.id = 'python-execution-input-cancel'
        cancel.type = 'button'
        cancel.textContent = '取消输入'
        cancel.addEventListener('click', stopRun)
        form.appendChild(prompt)
        form.appendChild(input)
        form.appendChild(submit)
        form.appendChild(cancel)
        form.addEventListener('submit', function (event) {
            event.preventDefault()
            var run = active
            if (!run || !run.pendingInput || !run.port || input.value.length > MAX_INPUT) return
            var requestId = run.pendingInput
            run.pendingInput = null
            form.hidden = true
            // Only the explicitly displayed input receives a reply; no URL, token or parent object crosses the frame.
            run.port.postMessage({ channel: CHANNEL, type: 'input-result', runId: run.runId, requestId: requestId, value: input.value })
            input.value = ''
            startCompute(run)
            setState('running', '正在运行…')
        })
        controls.appendChild(status)
        controls.appendChild(stop)
        controls.appendChild(note)
        controls.appendChild(form)
        host.parentNode.insertBefore(controls, host)
        setState(lastState, '尚未运行')
    }
    function hideInput () {
        var form = root.document.getElementById('python-execution-input-form')
        if (form) form.hidden = true
    }
    function finishRetirement (run) {
        if (run.finished) return
        run.finished = true
        root.clearTimeout(run.loadTimer)
        root.clearTimeout(run.computeTimer)
        root.clearTimeout(run.sessionTimer)
        root.clearTimeout(run.stopTimer)
        if (run.port) { run.port.onmessage = null; run.port.close() }
        if (run.frame) { run.frame.onload = null; run.frame.remove() }
        runs.delete(run)
        if (active === run) {
            active = null
            hideInput()
            setState(run.finalState, run.finalText)
        }
        var host = root.document.getElementById('mycanvas')
        if (host && !active) {
            host.classList.remove('python-execution-host')
            host.removeAttribute('data-graphics')
        }
        if (run.resolveStop) run.resolveStop()
    }
    function retire (run, state, text) {
        if (!run) return root.Promise.resolve()
        if (run.stopping) {
            run.finalState = state
            run.finalText = text
            return run.stopPromise
        }
        run.stopping = true
        run.finalState = state
        run.finalText = text
        pauseCompute(run)
        root.clearTimeout(run.loadTimer)
        root.clearTimeout(run.sessionTimer)
        run.frame.onload = null
        run.frame.style.display = 'none'
        run.stopPromise = new root.Promise(function (resolve) { run.resolveStop = resolve })
        if (!run.handshakeSent) {
            // No transfer means the trusted host could never create a computation Worker.
            finishRetirement(run)
        } else {
            requestStop(run)
        }
        return run.stopPromise
    }
    function requestStop (run) {
        run.port.postMessage({ channel: CHANNEL, type: 'stop', runId: run.runId })
        root.clearTimeout(run.stopTimer)
        run.stopTimer = root.setTimeout(function () {
            if (!run.finished && active === run) setState('stop-error', '停止尚未确认，请点击停止重试。')
        }, STOP_ACK_MS)
    }
    function stopRun () {
        pendingRun = null
        if (!active) return root.Promise.resolve()
        if (active.stopping) {
            active.finalState = 'stopped'
            active.finalText = '已停止，可以修改后重新运行。'
            setState('stopping', '正在停止…')
            requestStop(active)
            return active.stopPromise
        }
        hideInput()
        setState('stopping', '正在停止…')
        return retire(active, 'stopped', '已停止，可以修改后重新运行。')
    }
    function clear () {
        pendingRun = null
        root.TeachingPythonOutput.clear(root.document.getElementById('output'))
        if (!active) { setState('idle', '已清空'); return root.Promise.resolve() }
        hideInput()
        if (active.stopping && active.state === 'stop-error') requestStop(active)
        setState('stopping', '正在清空…')
        return retire(active, 'idle', '已清空')
    }
    function expire (run, state, text) {
        if (active !== run) return
        hideInput()
        setState('stopping', '正在结束本次运行…')
        retire(run, state, text)
    }
    function pauseCompute (run) {
        if (run.computeStarted) {
            run.remainingMs = Math.max(0, run.remainingMs - (Date.now() - run.computeStarted))
            run.computeStarted = 0
        }
        root.clearTimeout(run.computeTimer)
    }
    function startCompute (run) {
        if (active !== run) return
        run.computeStarted = Date.now()
        run.computeTimer = root.setTimeout(function () {
            expire(run, 'timeout', '运行时间较长，已停止。请简化程序后重试。')
        }, run.remainingMs)
    }
    function isText (value, max) { return typeof value === 'string' && value.length <= max }
    function receive (run, event) {
        // This private MessagePort was transferred only to this frame. Window postMessage is deliberately not a result channel.
        var data = event.data
        if (!data || data.channel !== CHANNEL || data.runId !== run.runId || typeof data.type !== 'string') return
        if (data.type === 'stopped' && run.stopping) { finishRetirement(run); return }
        if (active !== run || run.stopping) return
        if (data.type === 'ready' && !run.ready) {
            run.ready = true
            root.clearTimeout(run.loadTimer)
            startCompute(run)
            setState('running', '正在运行…')
            run.port.postMessage({ channel: CHANNEL, type: 'start', runId: run.runId })
        } else if (data.type === 'output' && run.ready && isText(data.text, MAX_TEXT) && data.text.length && run.outputUnits < MAX_OUTPUT_UNITS) {
            var text = data.text.slice(0, MAX_OUTPUT_UNITS - run.outputUnits)
            run.outputUnits += text.length
            root.TeachingPythonOutput.append(root.document.getElementById('output'), text)
        } else if (data.type === 'input' && run.ready && !run.pendingInput && isText(data.requestId, 32) && /^[0-9]+$/.test(data.requestId) && isText(data.prompt, MAX_TEXT)) {
            pauseCompute(run)
            run.pendingInput = data.requestId
            root.document.getElementById('python-execution-input-prompt').textContent = data.prompt || '请输入内容：'
            var input = root.document.getElementById('python-execution-input')
            input.value = ''
            root.document.getElementById('python-execution-input-form').hidden = false
            setState('waiting-input', '等待输入…')
            input.focus()
        } else if (data.type === 'done' && run.ready) {
            run.mainDone = true
            if (!run.callbacks.size && !run.pendingInput) { pauseCompute(run); setState('completed', '执行完毕') }
        } else if (data.type === 'callback-start' && run.ready && isText(data.requestId, 32) && /^[0-9]+$/.test(data.requestId) && !run.callbacks.has(data.requestId)) {
            if (run.callbacks.size >= 32) { expire(run, 'error', '操作过于频繁，已停止。请减少重复操作后重试。'); return }
            if (run.mainDone && !run.callbacks.size) run.remainingMs = COMPUTE_MS
            run.callbacks.add(data.requestId)
            if (!run.pendingInput) {
                if (!run.computeStarted) startCompute(run)
                setState('running', '正在运行…')
            }
        } else if (data.type === 'callback-done' && run.ready && isText(data.requestId, 32) && run.callbacks.has(data.requestId)) {
            run.callbacks.delete(data.requestId)
            if (run.mainDone && !run.callbacks.size && !run.pendingInput) { pauseCompute(run); setState('completed', '执行完毕') }
        } else if (data.type === 'error' && isText(data.text, MAX_TEXT)) {
            root.TeachingPythonOutput.append(root.document.getElementById('output'), '\n' + data.text + '\n')
            expire(run, 'error', '程序出错，可以修改后重新运行。')
        } else if (data.type === 'graphics' && run.ready && !run.graphics) {
            run.graphics = true
            var host = root.document.getElementById('mycanvas')
            if (host) host.setAttribute('data-graphics', 'true')
        }
    }
    function installFramePolicy () {
        if (policyInstalled) return
        // A srcdoc frame needs no navigation source. This also blocks its self-navigation to static paths with data in a query.
        var policy = root.document.createElement('meta')
        policy.httpEquiv = 'Content-Security-Policy'
        policy.content = "frame-src 'none'"
        root.document.head.appendChild(policy)
        policyInstalled = true
    }
    function escapeAttribute (text) { return text.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;') }
    function frameDocument () {
        var scripts = ['runner-loader.js', 'static/js/vendor.js', 'static/js/app.js', 'turtle-renderer.js', 'runner.js'].map(function (path) { return new URL(path, scriptBase).href })
        var workerScripts = ['worker-turtle.js', 'worker.js'].map(function (path) { return new URL(path, scriptBase).href })
        var style = new URL('runner.css', scriptBase).href
        var sources = scripts.concat(workerScripts).map(escapeAttribute).join(' ')
        // The document is constant apart from fixed resource URLs. Student code is sent only through the private port handshake.
        return '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="referrer" content="no-referrer"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; script-src ' + sources + ' \'unsafe-eval\'; style-src ' + escapeAttribute(style) + ' \'unsafe-inline\'; connect-src \'none\'; img-src data:; media-src \'none\'; font-src \'none\'; frame-src \'none\'; child-src \'none\'; worker-src blob:; object-src \'none\'; form-action \'none\'; base-uri ' + escapeAttribute(scriptBase) + '"><base href="' + escapeAttribute(scriptBase) + '"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Python 绘图区</title><link rel="stylesheet" href="' + escapeAttribute(style) + '"></head><body><div id="mycanvas" tabindex="0" aria-label="程序绘图"></div>' + scripts.map(function (url) { return '<script src="' + escapeAttribute(url) + '"></script>' }).join('') + '</body></html>'
    }
    function launch (code, runId) {
        hideInput()
        var host = root.document.getElementById('mycanvas')
        if (!host) { setState('error', '绘图区尚未准备好，请重新打开页面。'); return null }
        ensureControls(host)
        root.TeachingPythonOutput.clear(root.document.getElementById('output'))
        if (typeof code !== 'string' || code.length > MAX_CODE) { setState('error', '代码过长，请减少内容后重试。'); return null }
        if (!root.Worker || !root.MessageChannel || !root.crypto || !root.crypto.getRandomValues || !('srcdoc' in root.document.createElement('iframe'))) {
            setState('error', '当前浏览器无法运行此程序，请使用较新的浏览器重新打开。')
            return null
        }
        installFramePolicy()
        var frame = root.document.createElement('iframe')
        frame.className = 'python-execution-frame'
        frame.title = '程序绘图'
        frame.setAttribute('sandbox', 'allow-scripts')
        frame.setAttribute('referrerpolicy', 'no-referrer')
        var channel = new root.MessageChannel()
        var current = active = { runId: runId, state: 'loading', frame: frame, port: channel.port1, remainingMs: COMPUTE_MS, computeStarted: 0, ready: false, mainDone: false, callbacks: new Set(), graphics: false, pendingInput: null, outputUnits: 0 }
        runs.add(current)
        channel.port1.onmessage = function (event) { receive(current, event) }
        channel.port1.start()
        frame.onload = function () {
            if (active !== current) return
            frame.onload = null
            // The transfer is tied to this exact current WindowProxy. No execution object from the parent is sent.
            frame.contentWindow.postMessage({ channel: CHANNEL, type: 'run', runId: runId, code: code }, '*', [channel.port2])
            current.handshakeSent = true
            code = null
        }
        current.loadTimer = root.setTimeout(function () { expire(current, 'error', '运行环境加载失败，请重新运行。') }, LOAD_MS)
        current.sessionTimer = root.setTimeout(function () { expire(current, 'expired', '本次运行已结束，重新运行可继续。') }, SESSION_MS)
        host.classList.add('python-execution-host')
        host.setAttribute('data-graphics', 'false')
        frame.srcdoc = frameDocument()
        host.appendChild(frame)
        setState('loading', '正在准备运行…')
        return runId
    }
    function run (code) {
        var host = root.document.getElementById('mycanvas')
        if (!host) { setState('error', '绘图区尚未准备好，请重新打开页面。'); return null }
        ensureControls(host)
        if (typeof code !== 'string' || code.length > MAX_CODE) { setState('error', '代码过长，请减少内容后重试。'); return null }
        if (!root.crypto || !root.crypto.getRandomValues) { setState('error', '当前浏览器无法运行此程序，请使用较新的浏览器重新打开。'); return null }
        var bytes = new Uint8Array(16)
        root.crypto.getRandomValues(bytes)
        var runId = Array.prototype.map.call(bytes, function (byte) { return ('0' + byte.toString(16)).slice(-2) }).join('')
        if (!active) return launch(code, runId)
        // Keep only the latest request. Never create a second computation Worker until the old host confirms terminate().
        pendingRun = { runId: runId, code: code }
        hideInput()
        if (active.stopping && active.state === 'stop-error') requestStop(active)
        setState('stopping', '正在停止上一次运行…')
        retire(active, 'stopped', '已停止').then(function () {
            if (!pendingRun) return
            var next = pendingRun
            pendingRun = null
            launch(next.code, next.runId)
        })
        return runId
    }
    root.addEventListener('pagehide', function () {
        runs.forEach(function (run) {
            if (run.handshakeSent && run.port) run.port.postMessage({ channel: CHANNEL, type: 'stop', runId: run.runId })
        })
    })
    root.TeachingPythonExecution = {
        run: run,
        stop: stopRun,
        clear: clear,
        getState: function () {
            return { runId: active ? active.runId : null, pendingRunId: pendingRun ? pendingRun.runId : null, state: active ? active.state : lastState, remainingMs: active ? Math.max(0, active.remainingMs - (active.computeStarted ? Date.now() - active.computeStarted : 0)) : 0 }
        }
    }
}(window))
