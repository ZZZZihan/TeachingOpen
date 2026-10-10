/* Python editor persistence. Kept readable because the inherited editor is prebuilt. */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory()
  else root.PythonPersistence = factory()
})(typeof window !== 'undefined' ? window : this, function () {
  'use strict'
  function query(search) {
    var params = new URLSearchParams(search), standard = params.get('queryEncoding') === 'uri'
    var result = {}
    ;['workId', 'unitId', 'departId', 'additionalId', 'workName', 'scene', 'workFile', 'url', 'resetTemplate'].forEach(function (key) {
      var match = search.match(new RegExp('[?&]' + key + '=([^&]*)'))
      var value = standard ? params.get(key) : match && match[1]
      var fileValue = key === 'url' || key === 'workFile'
      // Legacy file URLs own their percent escapes and literal plus signs.
      if (!standard && value && (!fileValue || !/^(https?:\/\/|\/|\.\.?\/)/.test(value))) {
        try {
          var decoded = decodeURIComponent(value)
          // Only recognize whole encoded addresses; unknown relative values stay literal.
          if (!fileValue || /^(https?:\/\/|\/|\.\.?\/)/.test(decoded)) value = decoded
        } catch (error) { /* A literal percent is a valid name or file path. */ }
      }
      result[key] = !value || value === 'undefined' || value === 'null' ? '' : value
    })
    return result
  }
  function create(options) {
    var context = Object.assign({}, options.params)
    var state = { phase: 'idle', ready: false, busy: false, message: '', workId: context.workId || '' }
    var version = 0, prepared = null
    function notify(phase, message) { state.phase = phase; state.message = message; options.notify(Object.assign({}, state)) }
    function hasFile(value) { return typeof value === 'string' && Boolean(value.trim()) }
    async function readUnit(id) {
      if (typeof options.unit !== 'function') throw new Error('课程信息暂时不可用')
      var unit = await options.unit(id)
      if (!unit || typeof unit !== 'object') throw new Error('课程信息暂时不可用')
      if (unit.id && String(unit.id) !== String(id)) throw new Error('课程单元信息不一致')
      if (unit.courseWorkType !== undefined && unit.courseWorkType !== null && unit.courseWorkType !== '' && String(unit.courseWorkType) !== '4') throw new Error('课程练习类型不匹配')
      if (unit.mineWorkId !== undefined && unit.mineWorkId !== null && typeof unit.mineWorkId !== 'string') throw new Error('课程作品编号不可用')
      return unit
    }
    async function readWork(id) {
      var info = await options.info(id)
      if (!info || !hasFile(info.workFileKey_url) || String(info.workType) !== '4') throw new Error('作品信息不完整或类型不匹配')
      if (info.id && String(info.id) !== String(id)) throw new Error('作品编号与读取结果不一致')
      return info
    }
    async function load() {
      if (state.busy) return false
      var turn = ++version
      state.ready = false; state.busy = true; notify('loading', '正在打开作品…')
      try {
        var title = context.workName || '', url = context.workFile || context.url || './static/defaultPython.py'
        var workId = state.workId, reset = context.resetTemplate === '1', next = Object.assign({}, context), unit, info
        var fromUnit = !workId && Boolean(context.unitId)
        // An entry URL is a template hint, never evidence that the student's course work is absent.
        if (fromUnit) {
          unit = await readUnit(context.unitId)
          workId = unit.mineWorkId || ''
        }
        if (workId) {
          info = await readWork(workId)
          if (fromUnit && String(info.courseId || '') !== String(context.unitId)) throw new Error('作品与课程单元不一致')
          if (reset && (context.unitId && String(info.courseId || '') !== String(context.unitId) || context.additionalId && String(info.additionalId || '') !== String(context.additionalId))) throw new Error('原作品与重做任务不一致')
          next.unitId = info.courseId || ''; next.additionalId = info.additionalId || ''; next.departId = info.departId || ''
          if (!reset) { title = info.workName || ''; url = info.workFileKey_url }
          else if (next.unitId && !unit) unit = await readUnit(next.unitId)
          else if (!next.unitId && !hasFile(context.workFile || context.url)) throw new Error('重做模板文件不可用')
        }
        if (unit && (!workId || reset)) {
          if (!hasFile(unit.courseWork_url)) throw new Error('课程尚未提供练习文件')
          title = context.workName || unit.unitName || title; url = unit.courseWork_url
        }
        var code = await options.text(url)
        if (turn !== version) return false
        if (typeof code !== 'string') throw new Error('作品内容不可用')
        await options.apply(title, code)
        if (turn !== version) return false
        // A failed read/apply must not turn a later retry into an unrelated workId entry.
        context = next; state.workId = workId
        state.ready = true; state.busy = false
        notify('ready', state.workId && context.resetTemplate !== '1' ? '作品已打开' : '可以开始编写代码')
        return true
      } catch (error) {
        if (turn !== version) return false
        state.busy = false
        var detail = String(error && error.message || '程序文件尚未打开').replace(/[。；;\s]+$/, '')
        notify('load-error', '未能打开作品。' + detail + '。' + (/重试|重新加载|重新打开/.test(detail) ? '当前内容已保留。' : '当前内容已保留，请重试。'))
        return false
      }
    }
    async function save(title, code) {
      if (!state.ready || state.busy) return false
      title = String(title || '').trim()
      if (!title || title.length > 64) { notify('save-error', '请填写 1–64 个字符的作品名称。'); return false }
      if (typeof code !== 'string' || !code.trim()) { notify('save-error', '请先编写代码，再保存或提交。'); return false }
      if (new Blob([code]).size > 10 * 1024 * 1024) { notify('save-error', '代码文件超过 10 MB，请精简后再保存。'); return false }
      state.busy = true; notify('saving', '正在保存，请保持页面打开…')
      try {
        // A retry of the same snapshot reuses its registered file. No global upload callbacks.
        if (!prepared || prepared.code !== code || prepared.title !== title) {
          var file = await options.upload(title, code)
          if (!file || !file.id) throw new Error('文件登记失败')
          prepared = { title: title, code: code, id: file.id }
        }
        var result = await options.submit({ id: state.workId, workName: title, workFile: prepared.id, workCover: '', workType: 4, workStatus: 1,
          courseId: context.unitId || '', additionalId: context.additionalId || '', departId: context.departId || '',
          workScene: context.unitId ? 'course' : context.additionalId ? 'additional' : 'create' })
        if (!result || !result.id) throw new Error('服务器未返回作品编号，请到我的作品核对后重试')
        state.workId = result.id; context.resetTemplate = ''; context.workName = title
        options.saved(result.id)
        state.busy = false; notify('saved', context.unitId || context.additionalId ? '作业已提交。再次修改会更新同一份作品。' : '作品已保存。可以关闭页面，下次继续编辑。')
        return true
      } catch (error) {
        state.busy = false
        notify('save-error', '保存未完成。' + error.message + '；代码仍保留在当前页面，可重试或下载备份。')
        return false
      }
    }
    function changed(dirty) {
      if (!state.ready || state.busy || !dirty && state.phase !== 'dirty') return
      notify(dirty ? 'dirty' : 'ready', dirty ? '有未保存的修改。离开前请提交或下载备份。' : '当前内容未改动')
    }
    return { load: load, save: save, changed: changed, state: state }
  }
  return { query: query, create: create }
})
