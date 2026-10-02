// Optional notification transport. The caller owns its lifetime and visible UI.
export function createNotificationSocket ({ baseUrl, pageUrl, userId, getToken, onNotice, WebSocketCtor = WebSocket }) {
    let stopped = false
    let socket = null
    let timer = null
    let credential = null
    let ready = false
    const clearTimer = () => { clearTimeout(timer); timer = null }
    const sameSession = () => credential && credential === getToken()

    function stop () {
        stopped = true
        clearTimer()
        if (socket) {
            const previous = socket
            socket = null
            previous.onclose = null
            previous.onmessage = null
            previous.onopen = null
            previous.onerror = null
            previous.close()
        }
        credential = null
    }

    function heartbeat () {
        clearTimer()
        timer = setTimeout(() => {
            if (!sameSession()) return stop()
            if (socket && socket.readyState === 1 && ready) {
                socket.send('HeartBeat')
                heartbeat()
            }
        }, 20000)
    }

    function connect () {
        if (stopped) return
        if (credential && !sameSession()) return stop()
        credential = getToken()
        if (!credential || !userId) return stop()
        const url = new URL(baseUrl, pageUrl)
        if (!['http:', 'https:'].includes(url.protocol)) return stop()
        url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
        url.pathname = url.pathname.replace(/\/$/, '') + '/websocket/' + encodeURIComponent(userId)
        url.search = ''
        url.hash = ''
        const current = new WebSocketCtor(url.toString())
        socket = current
        ready = false
        timer = setTimeout(stop, 10000)
        current.onopen = () => {
            if (socket !== current || !sameSession()) return stop()
            current.send(JSON.stringify({ type: 'authenticate', token: credential }))
        }
        current.onmessage = event => {
            if (socket !== current || !sameSession()) return stop()
            let data
            try { data = JSON.parse(event.data) } catch (_) { return stop() }
            if (!data || typeof data !== 'object') return stop()
            if (!ready) {
                if (data.cmd !== 'authenticated') return stop()
                ready = true
                heartbeat()
            } else if (data.cmd === 'topic' || data.cmd === 'user') {
                onNotice()
            }
        }
        current.onclose = event => {
            if (socket !== current) return
            socket = null
            clearTimer()
            // Policy rejection and intentional closure need a new caller action/login.
            if (stopped || !sameSession() || event.code === 1008 || event.code === 1000) return stop()
            timer = setTimeout(connect, 5000)
        }
        current.onerror = () => {} // close determines whether reconnection is appropriate
    }

    connect()
    return { stop }
}
