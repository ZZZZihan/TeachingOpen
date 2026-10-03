/* Shared source loading for the inherited editor and preview. Source files never receive the API token. */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory(globalThis)
  else root.PythonSourceLoading = factory(root)
})(typeof window !== 'undefined' ? window : this, function (root) {
  'use strict'
  var LOAD_MS = 15000, APPLY_MS = 2000, MAX_BYTES = 10 * 1024 * 1024
  var preview = null
  function failure(message) {
    var error = new Error(message)
    error.name = 'PythonSourceError'
    return error
  }
  function address(value) {
    if (typeof value !== 'string' || !value.trim() || value.length > 32768 || /[\u0000-\u001f\u007f]/.test(value)) throw failure('程序文件地址不可用，请从作品页面重新打开。')
    var url
    try { url = new URL(value, root.location && root.location.href) } catch (error) { throw failure('程序文件地址不可用，请从作品页面重新打开。') }
    if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password) throw failure('程序文件地址不可用，请从作品页面重新打开。')
    return url.href
  }
  function read(value) {
    return new Promise(function (resolve, reject) {
      var url
      try { url = address(value) } catch (error) { reject(error); return }
      if (!root.fetch || !root.AbortController) { reject(failure('当前浏览器无法打开程序文件，请使用较新的浏览器重试。')); return }
      var controller = new root.AbortController(), settled = false
      var timer = root.setTimeout(function () {
        finish(failure('程序文件加载超时，请检查网络后重试。'))
        controller.abort()
      }, LOAD_MS)
      function finish(error, body) {
        if (settled) return
        settled = true
        root.clearTimeout(timer)
        if (error) reject(error)
        else resolve(body)
      }
      Promise.resolve().then(function () {
        // Existing same-origin media cookies remain available. Cross-origin file hosts receive no credentials or JWT.
        return root.fetch(url, { method: 'GET', credentials: 'same-origin', signal: controller.signal })
      }).then(function (response) {
        if (settled) return
        if (!response.ok) {
          if (response.status === 404) throw failure('程序文件不存在或已被移除（404），请检查作品地址后重试。')
          if (response.status === 401 || response.status === 403) throw failure('暂时没有权限打开程序文件，请确认登录状态或作品权限后重试。')
          throw failure('程序文件服务暂时不可用（' + response.status + '），请稍后重试。')
        }
        var type = response.headers.get('Content-Type') || ''
        if (/text\/html|application\/json/i.test(type)) throw failure('返回内容不是程序文件，请检查作品地址后重试。')
        return response.text().then(function (body) {
          if (typeof body !== 'string' || new root.Blob([body]).size > MAX_BYTES) throw failure('程序文件格式不正确或超过 10 MB，请检查文件后重试。')
          finish(null, body)
        })
      }).catch(function (error) {
        finish(error && error.name === 'PythonSourceError' ? error : failure('网络暂时不可用，程序文件尚未打开，请检查网络后重试。'))
      })
    })
  }
  function contents(host) {
    var editor = host.$refs && host.$refs.codeEditor
    var raw = editor && (editor.editor || editor.coder)
    if (raw && typeof raw.getValue === 'function') return raw.getValue()
    if (editor && typeof editor.getCodeContent === 'function') return editor.getCodeContent()
    if (typeof host.getCode === 'function') return host.getCode()
    return host.code
  }
  function normalized(value) { return typeof value === 'string' ? value.replace(/\r\n?/g, '\n') : value }
  function setReadOnly(host, value) {
    var editor = host.$refs && host.$refs.codeEditor
    if (editor && editor.editor && typeof editor.editor.setReadOnly === 'function') editor.editor.setReadOnly(value)
    if (editor && editor.coder && typeof editor.coder.setOption === 'function') editor.coder.setOption('readOnly', value)
  }
  function apply(host, code, unchanged) {
    return new Promise(function (resolve, reject) {
      var started = Date.now(), expected = normalized(code)
      function write() {
        var editor = host.$refs && host.$refs.codeEditor
        var raw = editor && (editor.editor || editor.coder)
        if (!raw || typeof raw.setValue !== 'function' || typeof raw.getValue !== 'function') {
          if (Date.now() - started >= APPLY_MS) { reject(failure('编辑器尚未准备好，请重新加载程序文件。')); return }
          root.setTimeout(write, 15)
          return
        }
        if (host._isDestroyed || unchanged && !unchanged()) { reject(failure('加载期间代码已修改，已保留当前内容。请先备份，再重新加载。')); return }
        try {
          setReadOnly(host, true)
          // The real Ace/CodeMirror setters are synchronous. Never schedule the inherited 300ms wrapper setter.
          if (editor.editor) raw.setValue(expected, -1)
          else raw.setValue(expected)
          editor.code = raw.getValue()
          if ('hasCode' in editor) editor.hasCode = !!editor.code
          host.code = editor.code
        } catch (error) { reject(failure('程序内容未能写入编辑器，请重新加载后再运行。')); return }
        var complete = function () {
          var wrapped = typeof editor.getCodeContent === 'function' ? editor.getCodeContent() : editor.code
          if (!host._isDestroyed && host.$refs.codeEditor === editor && normalized(contents(host)) === expected && normalized(wrapped) === expected && normalized(host.code) === expected) resolve()
          else reject(failure('程序内容应用期间发生变化，已保留当前内容，请重新加载后再运行。'))
        }
        if (typeof host.$nextTick === 'function') host.$nextTick(complete)
        else root.setTimeout(complete, 0)
      }
      root.setTimeout(write, 0)
    })
  }
  function show(host, phase, message, busy, ready) {
    host.$set(host, 'sourceBusy', busy)
    host.$set(host, 'sourceReady', ready)
    var status = root.document.getElementById('persistence-status')
    if (status) { status.textContent = message; status.dataset.phase = phase }
    var retry = root.document.getElementById('retry-load')
    if (retry) retry.hidden = phase !== 'load-error'
  }
  function mountPreview(host) {
    if (preview) return preview.promise
    var record = preview = { host: host, busy: false, promise: null }
    function load() {
      if (record.busy) return record.promise
      record.busy = true
      var before = contents(host)
      show(host, 'loading', '正在打开程序文件…', true, false)
      record.promise = Promise.resolve().then(function () {
        var params = root.PythonPersistence.query(root.location.search)
        if (!params.url) throw failure('没有指定程序文件，请从作品页面重新打开。')
        return read(params.url)
      }).then(function (code) {
        if (contents(host) !== before) throw failure('加载期间代码已修改，已保留当前内容。请先备份，再重新加载。')
        return apply(host, code, function () { return contents(host) === before })
      }).then(function () {
        record.busy = false
        show(host, 'ready', '程序已打开，可以运行。', false, true)
        return true
      }).catch(function (error) {
        record.busy = false
        show(host, 'load-error', '未能打开程序。' + error.message, false, false)
        return false
      })
      return record.promise
    }
    var retry = root.document.getElementById('retry-load')
    if (retry) retry.onclick = load
    return load()
  }
  return { read: read, apply: apply, contents: contents, setReadOnly: setReadOnly, mountPreview: mountPreview }
})
