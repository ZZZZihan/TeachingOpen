/* Small adapter for the inherited Vue/Ace editor; network and UI state stay here. */
(function () {
  'use strict'
  var host, session, savedSnapshot = '', loadSnapshot = '', initialized = false
  var params = window.PythonPersistence.query(window.location.search)
  function token() { try { return window.getUserToken() || '' } catch (error) { return '' } }
  function message(error) {
    if (error && (error.status === 401 || error.status === 403)) return '登录已失效或无权操作，请重新登录后再试'
    return '网络或服务暂时不可用'
  }
  function request(path, data) {
    return new Promise(function (resolve, reject) {
      var multipart = data instanceof FormData, headers = {}, access = token()
      if (access) headers['X-Access-Token'] = access
      $.ajax({ url: '/api' + path, type: data ? 'POST' : 'GET', headers: headers, timeout: 60000,
        data: data ? multipart ? data : JSON.stringify(data) : undefined,
        contentType: multipart ? false : 'application/json', processData: !multipart, dataType: 'json',
        success: function (result) {
          if (!result || result.success === false || result.code !== undefined && result.code !== 0 && result.code !== 200) { reject(new Error('服务未能完成操作')); return }
          resolve(result)
        }, error: function (error) { reject(new Error(message(error))) }
      })
    })
  }
  async function upload(title, code) {
    var config = (await request('/sys/config/getCurrentConfig')).result
    if (!config || !['local', 'qiniu'].includes(config.uploadType || 'local')) throw new Error('上传配置不可用')
    var name = title.replace(/[\\/\u0000-\u001f]/g, '_') + '.py', file = new Blob([code], { type: 'text/plain;charset=utf-8' })
    var path, location = 1
    if (config.uploadType === 'qiniu') {
      var credential = await request('/common/qiniu/getToken')
      if (!credential.result || !credential.keyPrefix || !qiniu.region[config.qiniuArea]) throw new Error('无法获取上传凭证或存储区域')
      var key = credential.keyPrefix + 'python/' + window.uuid() + '.py'
      path = await new Promise(function (resolve, reject) {
        var subscription, finished = false
        var timer = setTimeout(function () { finished = true; if (subscription) subscription.unsubscribe(); reject(new Error('文件上传超时')) }, 60000)
        try {
          subscription = qiniu.upload(file, key, credential.result, { fname: name }, {
            useCdnDomain: true, region: qiniu.region[config.qiniuArea], disableStatisticsReport: true
          }).subscribe({ next: function () {}, error: function () { if (finished) return; finished = true; clearTimeout(timer); reject(new Error('文件上传失败')) },
            complete: function (result) { if (finished) return; finished = true; clearTimeout(timer); result.key === key ? resolve(key) : reject(new Error('上传结果不一致')) }
          })
        } catch (error) { finished = true; clearTimeout(timer); reject(new Error('文件上传失败')) }
      })
      location = 2
    } else {
      var form = new FormData()
      form.append('file', file, name); form.append('bizPath', 'python')
      var transfer = await request('/sys/common/upload', form)
      if (!transfer.success || typeof transfer.message !== 'string' || !transfer.message.trim()) throw new Error('文件上传失败')
      path = transfer.message
    }
    var registered = await request('/system/sysFile/add', { fileType: 2, fileName: name, fileTag: '学生作业-python', filePath: path, fileLocation: location })
    if (!registered.success || !registered.result || !registered.result.id || registered.result.filePath !== path) throw new Error('文件登记失败')
    return registered.result
  }
  function readText(value) {
    return window.PythonSourceLoading.read(value)
  }
  function snapshot() { return host.projectName + '\n' + window.PythonSourceLoading.contents(host) }
  function update(state) {
    if (state.phase === 'loading') loadSnapshot = snapshot()
    host.$set(host, 'persistBusy', state.busy)
    host.$set(host, 'persistReady', state.ready)
    window.PythonSourceLoading.setReadOnly(host, !state.ready || state.busy)
    var status = document.getElementById('persistence-status')
    status.textContent = state.message; status.dataset.phase = state.phase
    document.getElementById('retry-load').hidden = state.phase !== 'load-error'
    if (state.phase === 'saved') savedSnapshot = snapshot()
  }
  function mount(editor) {
    if (host) return session
    host = editor
    editor.$set(editor, 'persistBusy', true); editor.$set(editor, 'persistReady', false)
    session = window.PythonPersistence.create({ params: params,
      info: async function (id) { return (await request('/teaching/teachingWork/studentWorkInfo?workId=' + encodeURIComponent(id))).result },
      unit: async function (id) { return (await request('/teaching/teachingCourseUnit/getUnitWorkInfo?unitId=' + encodeURIComponent(id))).result },
      text: readText, upload: upload, submit: async function (body) { return (await request('/teaching/teachingWork/submit', body)).result },
      apply: async function (title, code) {
        var current = host
        if (snapshot() !== loadSnapshot) throw new Error('加载期间代码已修改，已保留当前内容；请先备份，再重新打开')
        await window.PythonSourceLoading.apply(current, code, function () { return host === current && !current._isDestroyed && snapshot() === loadSnapshot })
        if (host !== current || current._isDestroyed) throw new Error('编辑器已经关闭，请重新打开作品')
        host.projectName = title
        savedSnapshot = snapshot(); initialized = true
      },
      saved: function (id) {
        var url = new URL(window.location.href)
        url.searchParams.set('workId', id); url.searchParams.set('queryEncoding', 'uri')
        ;['workFile', 'url', 'resetTemplate', 'workName'].forEach(function (key) { url.searchParams.delete(key) })
        window.history.replaceState(null, '', url.href)
      }, notify: update
    })
    document.getElementById('retry-load').onclick = function () { session.load() }
    window.addEventListener('beforeunload', function (event) {
      if (session.state.busy || initialized && snapshot() !== savedSnapshot) { event.preventDefault(); event.returnValue = '' }
    })
    function changed() { if (initialized) session.changed(snapshot() !== savedSnapshot) }
    host.$watch('projectName', changed)
    host.$refs.codeEditor.$watch('code', changed)
    session.load()
    return session
  }
  window.TeachingPython = { mount: mount }
  window.submitCode = function (title, code) { if (session) return session.save(title, code) }
})()
