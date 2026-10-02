/* API, VM and accessible status controls; no changes to the vendor bundle. */
(function () {
  'use strict'
  var session, vm, started = false
  var params = window.ScratchPersistence.query(window.location.search)
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
  async function capture() {
    vm.stopAll()
    var cover = bounded(new Promise(function (resolve, reject) {
      try { vm.renderer.draw(); vm.renderer.canvas.toBlob(function (blob) { blob ? resolve(blob) : reject(new Error()) }, 'image/png') } catch (error) { reject(error) }
    }), '封面生成')
    var project = bounded(vm.saveProjectSb3(), '作品生成')
    var values = await window.ScratchPersistence.pair(project, cover)
    return { project: values[0], cover: values[1], hasCloudData: vm.runtime.hasCloudData() }
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
      if (cloud) path = await cloudUpload(file, name, credential.keyPrefix + 'project3/' + group + suffix, credential, config)
      else {
        var form = new FormData(); form.append('file', file, name); form.append('bizPath', 'project3')
        var response = await request('/sys/common/upload', form)
        if (!response.success || typeof response.message !== 'string' || !response.message.trim()) throw new Error(label + '上传失败')
        path = response.message
      }
      var registered = await request('/system/sysFile/add', { fileType: 2, fileName: name, fileTag: '学生作业-' + label, filePath: path, fileLocation: cloud ? 2 : 1 })
      if (!registered.success || !registered.result || !registered.result.id || registered.result.filePath !== path) throw new Error(label + '登记失败')
      return registered.result.id
    }
    var values = await window.ScratchPersistence.pair(transfer(snapshot.project, '.sb3', 'sb3'), transfer(snapshot.cover, '.png', '封面'))
    return { project: values[0], cover: values[1] }
  }
  function update(state) {
    document.getElementById('persistence-status').textContent = state.message
    document.getElementById('persistence-status').dataset.phase = state.phase
    document.getElementById('retry-load').hidden = state.phase !== 'load-error'
    ;['save-draft', 'submit-work'].forEach(function (id) { document.getElementById(id).disabled = state.busy || !state.ready })
    var editor = document.getElementById('scratch')
    editor.inert = state.busy || !state.ready
    editor.setAttribute('aria-busy', String(state.busy))
    document.getElementById('editor-unavailable').hidden = state.ready && !state.busy
  }
  function setCloud(id) { if (id) window.scratch.setCloudId(id) }
  function start() {
    if (started) return
    started = true; clearTimeout(bootTimer)
    session = window.ScratchPersistence.create({ params: params, title: function () { return window.scratch.getProjectName() }, capture: capture, upload: upload,
      info: async function (id) { return (await request('/teaching/teachingWork/studentWorkInfo?workId=' + encodeURIComponent(id))).result },
      unit: async function (id) { return (await request('/teaching/teachingCourseUnit/getUnitWorkInfo?unitId=' + encodeURIComponent(id))).result },
      open: async function (url, title) { var bytes = await readProject(url); try { await vm.loadProject(bytes) } catch (error) { throw new Error('Scratch 无法读取这个项目文件') } window.scratch.setProjectName(title) },
      opened: setCloud,
      submit: async function (body) { return (await request('/teaching/teachingWork/submit', body)).result },
      saved: function (id) {
        var url = new URL(window.location.href)
        url.searchParams.set('workId', id); url.searchParams.set('queryEncoding', 'uri')
        ;['workFile', 'resetTemplate', 'workName'].forEach(function (key) { url.searchParams.delete(key) })
        window.history.replaceState(null, '', url.href); setCloud(id)
      }, notify: update
    })
    document.getElementById('save-draft').onclick = function () { session.save(0) }
    document.getElementById('submit-work').onclick = function () { session.save(1) }
    document.getElementById('retry-load').onclick = function () { session.load() }
    vm.on('PROJECT_CHANGED', function () { session.changed() })
    document.getElementById('scratch').addEventListener('input', function () { session.changed() })
    window.onbeforeunload = function (event) {
      if (session.state.busy || session.state.dirty) { event.preventDefault(); event.returnValue = '' }
    }
    session.load()
  }
  var bootTimer = setTimeout(function () {
    if (started) return
    document.getElementById('persistence-status').textContent = '编辑器未能启动。请检查网络后重新打开。'
    var retry = document.getElementById('retry-load'); retry.hidden = false; retry.onclick = function () { window.location.reload() }
  }, 60000)
  window.TeachingScratch = { initialize: function (value) { vm = value; window.vm = value }, start: start }
})()
