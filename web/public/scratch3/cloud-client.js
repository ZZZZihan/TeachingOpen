/* eslint-env browser */
/* Scratch VM cloud provider. One work/session per socket; no offline write replay. */
(function (root, factory) {
    if (typeof module === 'object' && module.exports) module.exports = factory()
    else root.TeachingScratchCloud = factory()
})(typeof window === 'undefined' ? this : window, function () {
    'use strict'
    function endpoint (origin) {
        var url = new URL('/api/websocket/scratch/cloudData', origin)
        if (!['http:', 'https:'].includes(url.protocol)) throw new Error('Unsupported origin')
        url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
        return url.href
    }
    function create (options) {
        var vm = options.vm; var Socket = options.WebSocket; var socket = null; var project = ''; var credential = ''; var ready = false
        var stopped = false; var disposed = false; var retries = 0; var retryTimer; var deadline; var pending = null; var queue = []; var known = new Set()
        var later = options.setTimeout || setTimeout; var cancel = options.clearTimeout || clearTimeout
        function status (phase, message, retry) { if (options.onStatus) options.onStatus({ phase: phase, message: message, retry: !!retry }) }
        function token () { try { return options.getToken() || '' } catch (error) { return '' } }
        function validName (name) { return typeof name === 'string' && name.trim() && name.length <= 128 && !name.includes('\0') }
        function validValue (value) { return (typeof value === 'string' || typeof value === 'number' && Number.isFinite(value)) && String(value).length <= 1024 }
        function variables () { var stage = vm.runtime.getTargetForStage(); return stage ? Object.values(stage.variables).filter(function (v) { return v.isCloud }) : [] }
        function disconnect () {
            ready = false; pending = null; queue = []; known.clear(); cancel(retryTimer); cancel(deadline); retryTimer = null; deadline = null
            var old = socket; socket = null
            if (old) { old.onopen = old.onmessage = old.onerror = old.onclose = null; try { old.close() } catch (error) {} }
        }
        function halt (phase, message) { stopped = true; disconnect(); status(phase, message, !!project) }
        function checkSession () {
            if (project && token() !== credential) { halt('session', '登录状态已变化。重新打开作品或重试连接；当前编辑内容保留在本机。'); return false }
            return !disposed && !stopped
        }
        function transient () {
            disconnect()
            if (!checkSession() || !project) return
            if (retries >= 5) { halt('offline', '云变量连接未恢复。当前修改仅在本机生效，可手动重试。'); return }
            var delay = Math.min(500 * Math.pow(2, retries++), 8000)
            status('offline', '云变量连接中断，正在重连。未确认的修改不自动补发，重连后读取云端值。', true)
            retryTimer = later(connect, delay)
        }
        function send (message) {
            if (!checkSession() || !socket || socket.readyState !== 1) return false
            try { socket.send(JSON.stringify(Object.assign({ project_id: project, token: credential }, message)) + '\n'); return true } catch (error) { transient(); return false }
        }
        function pump () {
            if (!ready || pending || !queue.length || !checkSession()) return
            pending = queue.shift()
            if (send(pending)) deadline = later(transient, 8000)
        }
        function change (method, name, value, newName) {
            if (!validName(name) || (['set', 'create'].includes(method) && !validValue(value)) || (method === 'rename' && !validName(newName))) {
                status('error', '云变量名称或值超出支持范围，修改未同步。', false); return false
            }
            if (!project) { status('local', options.localMessage || '当前变量仅在本机运行。'); return false }
            if (!checkSession()) return false
            if (!ready) { if (!socket && !retryTimer) connect(); status('offline', '云变量尚未连接，当前修改仅在本机生效。连接后读取云端值。', true); return false }
            if (!credential) { status('readonly', '公开作品的云变量为只读；登录后才可同步修改。'); return false }
            if (queue.length >= 64) { halt('error', '云变量修改过于频繁，已停止同步。当前修改保留在本机。'); return false }
            var request = { method: method, name: name }
            if (value !== undefined) request.value = String(value)
            if (newName !== undefined) request.new_name = newName
            queue.push(request); pump(); return true
        }
        function connect () {
            retryTimer = null
            if (!project || !checkSession() || socket) return
            if (!vm.runtime.hasCloudData()) { status('empty', '当前作品没有云变量。'); return }
            status('connecting', '正在连接云变量…')
            var current
            try { current = new Socket(endpoint(options.origin)); socket = current } catch (error) { transient(); return }
            deadline = later(transient, 8000)
            current.onopen = function () { if (socket === current) send({ method: 'handshake' }) }
            current.onmessage = function (event) {
                if (socket !== current || !checkSession()) return
                try {
                    if (typeof event.data !== 'string' || event.data.length > 65536) throw new Error()
                    var lines = event.data.split('\n').filter(Boolean)
                    if (lines.length > 128) throw new Error()
                    for (var i = 0; i < lines.length; i++) {
                        var message = JSON.parse(lines[i])
                        if (message.method === 'set') {
                            if (message.project_id !== project || !validName(message.name) || !validValue(message.value)) throw new Error()
                            known.add(message.name)
                            if (variables().some(function (v) { return v.name === message.name })) vm.postIOData('cloud', { varUpdate: { name: message.name, value: String(message.value) } })
                        } else if (message.method === 'ack') {
                            if (!ready) {
                                if (message.reply !== 'OK' || message.name != null) throw new Error()
                                cancel(deadline); ready = true; retries = 0
                                status(credential ? 'ready' : 'readonly', credential ? '云变量已连接。' : '云变量已连接；匿名浏览为只读。')
                                if (options.seed && credential) variables().forEach(function (v) { if (!known.has(v.name)) change('create', v.name, v.value) })
                            } else {
                                if (!pending || message.name !== pending.name || !['OK', 'FAIL'].includes(message.reply)) throw new Error()
                                cancel(deadline)
                                if (message.reply === 'FAIL') status('error', '云端未接受这次修改，请检查登录、作品权限或变量数量。当前编辑内容保留。', true)
                                pending = null; pump()
                            }
                        } else throw new Error()
                    }
                } catch (error) { halt('error', '云变量响应无法处理，已停止同步。可重试连接。') }
            }
            current.onerror = function () { /* close or deadline owns recovery; never log credentials. */ }
            current.onclose = function (event) {
                if (socket !== current) return
                if ([1008, 1009].includes(event.code)) halt('denied', '无法连接此作品的云变量。请检查登录与作品权限，再手动重试。')
                else transient()
            }
        }
        var api = {
            bind: function (id) {
                if (disposed) return
                if (project === id && !stopped && credential === token()) return
                disconnect(); project = ''; stopped = false; retries = 0
                if (typeof id !== 'string' || !/^[A-Za-z0-9_-]{1,64}$/.test(id) || id === 'create') { status('local', options.localMessage || '当前变量仅在本机运行。'); return }
                project = id; credential = token(); vm.setCloudProvider(api); connect()
            },
            retry: function () { if (disposed || !project) return; disconnect(); stopped = false; retries = 0; credential = token(); vm.setCloudProvider(api); connect() },
            checkSession: checkSession,
            pause: function () { disconnect(); stopped = true; status('paused', '云变量已暂停。') },
            resume: function () { if (project && token() !== credential) { halt('session', '登录状态已变化，请重新打开作品或重试连接。'); return }; api.retry() },
            requestCloseConnection: function () { disconnect(); project = ''; stopped = true; status('local', options.localMessage || '当前变量仅在本机运行。') },
            createVariable: function (name, value) { return change('create', name, value) },
            updateVariable: function (name, value) { return change('set', name, value) },
            renameVariable: function (name, newName) { return change('rename', name, undefined, newName) },
            deleteVariable: function (name) { return change('delete', name) },
            destroy: function () { api.requestCloseConnection(); disposed = true }
        }
        return api
    }
    function mount (vm, options) {
        var statusNode = document.getElementById('cloud-status'); var retry = document.getElementById('retry-cloud')
        var client = create({ vm: vm,
            origin: window.location.origin,
            WebSocket: window.WebSocket,
            getToken: options.getToken,
            seed: options.seed,
            localMessage: options.seed ? '当前为本地变量。保存作品后才连接云端。' : '案例中的变量仅在本机运行，不连接云端。',
            onStatus: function (state) {
                if (statusNode) { statusNode.textContent = state.message; statusNode.dataset.phase = state.phase }
                if (retry) retry.hidden = !state.retry
            } })
        if (retry) retry.onclick = client.retry
        var timer = setInterval(client.checkSession, 1000)
        window.addEventListener('storage', client.checkSession)
        window.addEventListener('pagehide', function (event) {
            if (event.persisted) { client.pause(); return }
            clearInterval(timer); window.removeEventListener('storage', client.checkSession); client.destroy()
        })
        window.addEventListener('pageshow', function (event) { if (event.persisted) client.resume() })
        return client
    }
    return { endpoint: endpoint, create: create, mount: mount }
})
