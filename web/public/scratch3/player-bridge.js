/* eslint-env browser */
/* global urlParams, getUserToken */
/* Load the actual project before binding its cloud identity. File requests never carry JWTs. */
(function () {
    'use strict'
    var vm; var cloud; var loading = false; var workId = urlParams('workId'); var workUrl = urlParams('workUrl')
    function token () { try { return getUserToken() || '' } catch (error) { return '' } }
    function state (message, retry) {
        document.getElementById('player-status').textContent = message
        document.getElementById('retry-project').hidden = !retry
    }
    async function read (url, headers, binary) {
        var controller = new AbortController(); var timer = setTimeout(function () { controller.abort() }, 60000)
        try {
            var response = await fetch(url, { headers: headers || {}, credentials: 'same-origin', signal: controller.signal })
            if (!response.ok) throw new Error(response.status === 401 || response.status === 403 ? '请登录有权查看此作品的账号后重试。' : '作品暂时无法读取，请重试。')
            return await (binary ? response.arrayBuffer() : response.json())
        } finally { clearTimeout(timer) }
    }
    async function start () {
        if (loading || !vm) return
        loading = true; vm.stopAll(); cloud.requestCloseConnection(); state('正在打开作品…', false)
        var identity = token()
        try {
            var file = workUrl
            if (!file && workId) {
                var result = await read('/api/teaching/teachingWork/studentWorkInfo?workId=' + encodeURIComponent(workId), identity ? { 'X-Access-Token': identity } : {})
                if (!result || result.success === false || !result.result || !result.result.workFileKey_url) throw new Error('作品不存在或暂时无法读取。')
                file = result.result.workFileKey_url
            }
            if (!file) { state('未指定作品。', false); return }
            var url = new URL(file, window.location.href)
            if (!['http:', 'https:'].includes(url.protocol)) throw new Error('作品地址无效。')
            var bytes = await read(url.href, null, true)
            if (identity !== token()) throw new Error('登录状态已变化，请重试打开作品。')
            await vm.loadProject(bytes)
            if (identity !== token()) throw new Error('登录状态已变化，请重试打开作品。')
            if (!workUrl) cloud.bind(workId)
            else cloud.requestCloseConnection()
            vm.runtime.start(); state('', false)
        } catch (error) { state(error.message || '作品未能打开，请重试。', true) } finally { loading = false }
    }
    window.TeachingScratchPlayer = {
        initialize: function (value) { vm = value; window.vm = value; cloud = window.TeachingScratchCloud.mount(vm, { getToken: token, seed: false }) },
        start: function () { document.getElementById('retry-project').onclick = start; return start() }
    }
})()
