/* This opaque document renders trusted turtle calls. Student Python and JavaScript run only in its Worker. */
(function (root) {
    'use strict'
    var CHANNEL = 'teaching-python-v1'
    var MAX_TEXT = 2048
    var MAX_CODE = 256000
    var RETIRE_COOLDOWN_MS = 2500
    var NativeWorker = root.Worker
    var NativeBlob = root.Blob
    var createObjectURL = root.URL.createObjectURL.bind(root.URL)
    var revokeObjectURL = root.URL.revokeObjectURL.bind(root.URL)
    var NativeMessageChannel = root.MessageChannel
    var then = Function.prototype.call.bind(root.Promise.prototype.then)
    var base = new URL('.', root.document.currentScript.src).href
    var started = false

    function smallPacket (value) {
        var nodes = 0
        function visit (item, depth) {
            if (++nodes > 256 || depth > 8) return false
            if (item === null || typeof item === 'boolean') return true
            if (typeof item === 'string') return item.length <= MAX_TEXT
            if (typeof item === 'number') return Number.isFinite(item)
            if (typeof item !== 'object') return false
            var keys = Object.keys(item)
            if (keys.length > (Array.isArray(item) ? 32 : 16)) return false
            return keys.every(function (key) { return key.length <= 64 && visit(item[key], depth + 1) })
        }
        return visit(value, 0)
    }
    function bootstrap (event) {
        var data = event.data
        if (started || event.source !== root.parent || !data || data.channel !== CHANNEL || data.type !== 'run' ||
            typeof data.runId !== 'string' || !/^[a-f0-9]{32}$/.test(data.runId) || typeof data.code !== 'string' || data.code.length > MAX_CODE || event.ports.length !== 1) return
        started = true
        root.removeEventListener('message', bootstrap)
        var runId = data.runId
        var code = data.code
        var parentPort = event.ports[0]
        var postParent = parentPort.postMessage.bind(parentPort)
        var worker = null
        var workerPort = null
        var bridge = null
        var graphics = false
        var workerReady = false
        var stopped = false
        var requestCount = 0
        var pending = Object.create(null)
        var pendingCount = 0
        var rateStarted = Date.now()
        var rateCount = 0
        var blobURL = null
        var workerEverStarted = false
        var stopAckTimer = null
        var stopAcknowledged = false
        data = null
        event = null

        function send (type, fields) {
            var message = { channel: CHANNEL, type: type, runId: runId }
            if (fields) Object.keys(fields).forEach(function (key) { message[key] = fields[key] })
            postParent(message)
        }
        function halt () {
            stopped = true
            if (worker) { worker.terminate(); worker = null }
            if (workerPort) { workerPort.onmessage = null; workerPort.close(); workerPort = null }
            if (bridge) {
                try { bridge.dispose() } catch (ignore) { /* A drawing cleanup failure cannot skip Worker termination acknowledgment. */ }
                bridge = null
            }
            if (blobURL) { revokeObjectURL(blobURL); blobURL = null }
            code = null
        }
        function fail (error) {
            if (stopped) return
            halt()
            send('error', { text: String(error).slice(0, MAX_TEXT) })
        }
        function rendererReply (packet) {
            if (stopped || !workerPort || !packet) return
            if (packet.type === 'graphics') {
                if (!graphics) { graphics = true; send('graphics') }
                return
            }
            if (!['turtle-result', 'turtle-event'].includes(packet.type)) return
            if (packet.type === 'turtle-result' && Object.prototype.hasOwnProperty.call(pending, packet.requestId)) {
                var request = pending[packet.requestId]
                delete pending[packet.requestId]
                pendingCount--
                // Event-only turtle programs need a clickable/focusable surface before the first lazy canvas is created.
                if (!packet.error && request.op === 'init' && !graphics) { graphics = true; send('graphics') }
            }
            workerPort.postMessage(Object.assign({ channel: CHANNEL, runId: runId }, packet))
        }
        parentPort.onmessage = function (messageEvent) {
            var reply = messageEvent.data
            if (!reply || reply.channel !== CHANNEL || reply.runId !== runId) return
            if (reply.type === 'stop') {
                halt()
                // Chromium permits a brief graceful shutdown interval. Space rapid runs; this timer is not proof of CPU death.
                // The acknowledgment is generated here after terminate(), never forwarded from user code.
                if (!workerEverStarted || stopAcknowledged) send('stopped')
                else if (!stopAckTimer) stopAckTimer = root.setTimeout(function () {
                    stopAcknowledged = true
                    send('stopped')
                }, RETIRE_COOLDOWN_MS)
            } else if (!stopped && workerPort && reply.type === 'start' && workerReady) {
                workerPort.postMessage({ channel: CHANNEL, type: 'start', runId: runId })
            } else if (!stopped && workerPort && reply.type === 'input-result' && typeof reply.requestId === 'string' && reply.requestId.length <= 32 && typeof reply.value === 'string' && reply.value.length <= 4096) {
                workerPort.postMessage(reply)
            }
        }
        parentPort.start()
        root.addEventListener('pagehide', halt)
        root.setTimeout(function initialize () {
            if (stopped) return
            try {
                if (!NativeWorker || !NativeBlob || !NativeMessageChannel) throw new Error('当前浏览器无法运行此程序，请使用较新的浏览器重新打开。')
                var sk = root.TeachingPythonRuntime()
                var target = root.document.getElementById('mycanvas')
                sk.configure({
                    read: function (path) {
                        if (!Object.prototype.hasOwnProperty.call(sk.builtinFiles.files, path)) throw new Error("File not found: '" + path + "'")
                        return sk.builtinFiles.files[path]
                    },
                    __future__: sk.python2,
                    execLimit: 30000,
                    yieldLimit: 100
                })
                sk.TurtleGraphics = { target: 'mycanvas', width: Math.max(1, root.innerWidth), height: Math.max(1, root.innerHeight), allowUndo: true }
                bridge = root.TeachingPythonTurtleRenderer.create(sk, target, rendererReply)
                delete root.TeachingPythonTurtleRenderer
                var observer = new root.MutationObserver(function () {
                    if (!stopped && !graphics && target.querySelector('canvas')) { graphics = true; send('graphics') }
                })
                observer.observe(target, { childList: true })
                root.addEventListener('resize', function () {
                    var scale = Math.min(Math.max(1, root.innerWidth) / sk.TurtleGraphics.width, Math.max(1, root.innerHeight) / sk.TurtleGraphics.height)
                    target.style.width = sk.TurtleGraphics.width + 'px'
                    target.style.height = sk.TurtleGraphics.height + 'px'
                    target.style.transformOrigin = 'top left'
                    target.style.transform = 'scale(' + scale + ')'
                })
                var urls = ['runner-loader.js', 'static/js/vendor.js', 'static/js/app.js', 'worker-turtle.js', 'worker.js'].map(function (path) { return new URL(path, base).href })
                var source = 'self.window=self;importScripts(' + urls.map(function (url) { return JSON.stringify(url) }).join(',') + ');'
                blobURL = createObjectURL(new NativeBlob([source], { type: 'text/javascript' }))
                worker = new NativeWorker(blobURL)
                workerEverStarted = true
                worker.onerror = function (error) { fail(error.message || '计算环境加载失败，请重新运行。') }
                worker.onmessageerror = function () { fail('计算环境消息无法读取，请重新运行。') }
                var channel = new NativeMessageChannel()
                workerPort = channel.port1
                workerPort.onmessage = function (workerEvent) {
                    var packet = workerEvent.data
                    if (stopped || !packet || packet.channel !== CHANNEL || packet.runId !== runId) return
                    if (packet.type === 'turtle-request') {
                        if (!smallPacket(packet) || !Number.isInteger(packet.requestId) || packet.requestId < 1 || packet.requestId > 1000000000 || Object.prototype.hasOwnProperty.call(pending, packet.requestId)) { fail('绘图请求无法处理，请修改程序后重试。'); return }
                        if (Date.now() - rateStarted >= 1000) { rateStarted = Date.now(); rateCount = 0 }
                        if (++rateCount > 500 || ++requestCount > 10000 || pendingCount >= 32) { fail('绘图操作过于频繁，已停止。请减少绘图次数后重试。'); return }
                        pending[packet.requestId] = { op: packet.op }
                        pendingCount++
                        try {
                            var result = bridge.handle(packet)
                            if (result && typeof result.then === 'function') then(result, function () {}, fail)
                        } catch (error) { fail(error) }
                    } else if (packet.type === 'ready' && !workerReady) {
                        workerReady = true
                        send('ready')
                    } else if (packet.type === 'output' && workerReady && typeof packet.text === 'string' && packet.text.length <= MAX_TEXT) {
                        send('output', { text: packet.text })
                    } else if (packet.type === 'input' && workerReady && typeof packet.requestId === 'string' && packet.requestId.length <= 32 && typeof packet.prompt === 'string' && packet.prompt.length <= MAX_TEXT) {
                        send('input', { requestId: packet.requestId, prompt: packet.prompt })
                    } else if (packet.type === 'resumed' && typeof packet.requestId === 'string' && packet.requestId.length <= 32) {
                        send('resumed', { requestId: packet.requestId })
                    } else if (packet.type === 'done' && workerReady) {
                        send('done')
                    } else if ((packet.type === 'callback-start' || packet.type === 'callback-done') && workerReady && typeof packet.requestId === 'string' && packet.requestId.length <= 32 && /^[0-9]+$/.test(packet.requestId)) {
                        send(packet.type, { requestId: packet.requestId })
                    } else if (packet.type === 'error' && typeof packet.text === 'string' && packet.text.length <= MAX_TEXT) {
                        fail(packet.text)
                    }
                }
                workerPort.start()
                worker.postMessage({ channel: CHANNEL, type: 'run', runId: runId, code: code }, [channel.port2])
                code = null
            } catch (error) { fail(error) }
        }, 0)
    }
    root.addEventListener('message', bootstrap)
}(window))
