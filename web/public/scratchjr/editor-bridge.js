/* Platform-owned context and I/O; the child owns the inherited ScratchJr engine. */
(function () {
  'use strict'
  var params = window.ScratchPersistence.query(window.location.search)
  var readOnly = params.mode === 'look', frame, pending, objectUrl, session
  var titleInput = document.getElementById('project-name')
  function token() { try { return window.getUserToken() || '' } catch (error) { return '' } }
  function networkError(status) { return new Error(status === 401 || status === 403 ? '登录已失效或无权操作，请重新登录后再试' : '网络或服务暂时不可用') }
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
        }, error: function (error) { reject(networkError(error.status)) }
      })
    })
  }
  function readProject(value) {
    return new Promise(function (resolve, reject) {
      var url
      try { url = new URL(value, window.location.href); if (!['http:', 'https:'].includes(url.protocol)) throw new Error() } catch (error) { reject(new Error('作品地址不可用')); return }
      // Same-origin media cookie is sent by the browser. Never put a platform JWT on a file request.
      var xhr = new XMLHttpRequest()
      xhr.open('GET', url.href); xhr.responseType = 'arraybuffer'; xhr.timeout = 60000
      xhr.onload = function () {
        if (xhr.status < 200 || xhr.status >= 300) { reject(networkError(xhr.status)); return }
        var type = xhr.getResponseHeader('Content-Type') || ''
        if (/text\/html|application\/json/i.test(type) || !xhr.response || !xhr.response.byteLength) { reject(new Error('作品文件为空或格式不正确')); return }
        resolve(xhr.response)
      }
      xhr.onerror = xhr.ontimeout = function () { reject(networkError(0)) }
      xhr.send()
    })
  }
  function bounded(promise, label) {
    return new Promise(function (resolve, reject) {
      var timer = setTimeout(function () { reject(new Error(label + '超时，请重试')) }, 60000)
      Promise.resolve(promise).then(function (value) { clearTimeout(timer); resolve(value) }, function () { clearTimeout(timer); reject(new Error(label + '失败')) })
    })
  }
  function cloudUpload(file, name, key, credential, config) {
    return new Promise(function (resolve, reject) {
      var subscription, finished = false
      var timer = setTimeout(function () { finished = true; if (subscription) subscription.unsubscribe(); reject(new Error('文件上传超时')) }, 60000)
      function fail() { if (finished) return; finished = true; clearTimeout(timer); reject(new Error('文件上传失败')) }
      try {
        subscription = qiniu.upload(file, key, credential.result, { fname: name }, {
          useCdnDomain: true, region: qiniu.region[config.qiniuArea], disableStatisticsReport: true
        }).subscribe({ next: function () {}, error: fail, complete: function (result) {
          if (finished) return; finished = true; clearTimeout(timer)
          result && result.key === key ? resolve(key) : reject(new Error('上传结果不一致'))
        } })
      } catch (error) { fail() }
    })
  }
  async function upload(title, snapshot) {
    var config = (await request('/sys/config/getCurrentConfig')).result
    if (!config || !['local', 'qiniu'].includes(config.uploadType || 'local')) throw new Error('上传配置不可用')
    var credential, group = window.uuid(), cloud = config.uploadType === 'qiniu'
    if (cloud) {
      credential = await request('/common/qiniu/getToken')
      if (!credential.result || !credential.keyPrefix || !qiniu.region[config.qiniuArea]) throw new Error('无法获取上传凭证或存储区域')
    }
    async function transfer(file, suffix, label) {
      var name = title.replace(/[\\/\u0000-\u001f]/g, '_') + suffix, path
      if (cloud) path = await cloudUpload(file, name, credential.keyPrefix + 'scratchjr/' + group + suffix, credential, config)
      else {
        var form = new FormData(); form.append('file', file, name); form.append('bizPath', 'scratchjr')
        var response = await request('/sys/common/upload', form)
        if (!response.success || typeof response.message !== 'string' || !response.message.trim()) throw new Error(label + '上传失败')
        path = response.message
      }
      var registered = await request('/system/sysFile/add', { fileType: 2, fileName: name, fileTag: '学生作业-' + label, filePath: path, fileLocation: cloud ? 2 : 1 })
      if (!registered.success || !registered.result || !registered.result.id || registered.result.filePath !== path) throw new Error(label + '登记失败')
      return registered.result.id
    }
    var values = await window.ScratchPersistence.pair(transfer(snapshot.project, '.sjr', 'sjr'), transfer(snapshot.cover, '.png', '封面'))
    return { project: values[0], cover: values[1] }
  }

  function childIsCurrent(child) { return frame && frame.contentWindow === child }
  function discard() {
    if (frame) { frame.remove(); frame = null }
    if (objectUrl) { URL.revokeObjectURL(objectUrl); objectUrl = null }
  }
  async function open(url, title) {
    discard()
    // pmd5 is only meaningful for unsaved projects created in ScratchJr's local home.
    var local = params.pmd5 && !params.workId && !params.unitId && !params.workFile
    var bytes = local ? null : await readProject(url)
    if (bytes) objectUrl = URL.createObjectURL(new Blob([bytes], { type: 'application/octet-stream' }))
    return new Promise(function (resolve, reject) {
      var timer = setTimeout(function () { finish(new Error('编辑器读取超时')); discard() }, 60000)
      function finish(error, child) {
        clearTimeout(timer); pending = null
        if (error) { discard(); reject(error); return }
        try {
          var name = local ? child.ScratchJr.getProjectName() : title
          titleInput.value = name || 'ScratchJr 作品'
          child.ScratchJr.setProjectName(titleInput.value)
          resolve()
        } catch (error) { discard(); reject(new Error('作品名称读取失败')) }
      }
      pending = finish
      frame = document.createElement('iframe'); frame.title = 'ScratchJr 积木编辑器'
      // A blob URL contains no query delimiters; the vendor's legacy parser reads it verbatim.
      frame.src = 'engine.html?mode=' + (readOnly ? 'look' : 'edit') + (local ? '&pmd5=' + encodeURIComponent(params.pmd5) : '&workFile=' + objectUrl)
      frame.setAttribute('aria-busy', 'true')
      document.getElementById('engine-host').appendChild(frame)
    })
  }
  async function capture() {
    var engine = frame.contentWindow.ScratchJr
    engine.stopStrips(); engine.setProjectName(titleInput.value.trim())
    var project = await bounded(new Promise(function (resolve, reject) {
      try { engine.getProjectSjr(resolve) } catch (error) { reject(error) }
    }), '作品生成')
    var cover = await bounded(new Promise(function (resolve, reject) {
      try {
        engine.getProjectCover(function (data) {
          try {
            if (!/^data:image\/png;base64,/.test(data)) throw new Error()
            var raw = atob(data.split(',')[1]), bytes = new Uint8Array(raw.length)
            for (var i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i)
            resolve(new Blob([bytes], { type: 'image/png' }))
          } catch (error) { reject(error) }
        })
      } catch (error) { reject(error) }
    }), '封面生成')
    return { project: project, cover: cover }
  }
  function update(state) {
    document.getElementById('persistence-status').textContent = readOnly && state.phase === 'ready' ? '作品预览' : state.message
    document.getElementById('persistence-status').dataset.phase = state.phase
    document.getElementById('retry-load').hidden = state.phase !== 'load-error'
    ;['save-draft', 'submit-work'].forEach(function (id) { document.getElementById(id).disabled = state.busy || !state.ready || readOnly })
    titleInput.disabled = state.busy || !state.ready || readOnly
    document.getElementById('engine-host').inert = state.busy || !state.ready
    if (frame) frame.setAttribute('aria-busy', String(state.busy))
  }
  session = window.ScratchPersistence.create({ params: params, workType: 3, acceptedTypes: ['3'], defaultTitle: 'ScratchJr 作品', defaultFile: './project.sjr',
    title: function () { return titleInput.value }, capture: capture, upload: upload, open: open, opened: function () {},
    info: async function (id) { return (await request('/teaching/teachingWork/studentWorkInfo?workId=' + encodeURIComponent(id))).result },
    unit: async function (id) { return (await request('/teaching/teachingCourseUnit/getUnitWorkInfo?unitId=' + encodeURIComponent(id))).result },
    submit: async function (body) { return (await request('/teaching/teachingWork/submit', body)).result },
    saved: function (id) {
      var url = new URL(window.location.href)
      url.searchParams.set('workId', id); url.searchParams.set('queryEncoding', 'uri')
      ;['workFile', 'resetTemplate', 'workName', 'pmd5'].forEach(function (key) { url.searchParams.delete(key) })
      window.history.replaceState(null, '', url.href)
    }, notify: update
  })
  window.TeachingJunior = {
    loaded: function (child) { if (childIsCurrent(child) && pending) pending(null, child) },
    failed: function (child) { if (childIsCurrent(child) && pending) pending(new Error('ScratchJr 无法读取这个项目文件')) },
    changed: function (child) { if (childIsCurrent(child) && !readOnly) session.changed() },
    save: function (child) {
      if (!childIsCurrent(child) || readOnly || !session.state.ready || session.state.busy) return
      titleInput.value = child.ScratchJr.getProjectName() || titleInput.value
      session.save(1)
    }
  }
  document.getElementById('save-draft').onclick = function () { return session.save(0) }
  document.getElementById('submit-work').onclick = function () { return session.save(1) }
  document.getElementById('retry-load').onclick = function () { return session.load() }
  titleInput.oninput = function () { if (frame) frame.contentWindow.ScratchJr.setProjectName(titleInput.value); session.changed() }
  if (readOnly) document.querySelector('.actions').hidden = true
  window.onbeforeunload = function (event) {
    if (!readOnly && (session.state.busy || session.state.dirty)) { event.preventDefault(); event.returnValue = '' }
  }
  session.load()
})()
