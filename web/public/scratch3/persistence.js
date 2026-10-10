/* Shared save/load state machine for the inherited Scratch and ScratchJr engines. */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory()
  else root.ScratchPersistence = factory()
})(typeof window !== 'undefined' ? window : this, function () {
  'use strict'
  function query(search) {
    var params = new URLSearchParams(search), standard = params.get('queryEncoding') === 'uri', result = {}
    ;['workId', 'unitId', 'departId', 'additionalId', 'workName', 'scene', 'workFile', 'resetTemplate', 'pmd5', 'mode'].forEach(function (key) {
      var match = search.match(new RegExp('[?&]' + key + '=([^&]*)'))
      var value = standard ? params.get(key) : match && match[1]
      if (!standard && value && (key !== 'workFile' || !/^(https?:\/\/|\/)/.test(value))) {
        try { value = decodeURIComponent(value) } catch (error) { /* Literal percent signs are valid titles. */ }
      }
      result[key] = !value || value === 'undefined' || value === 'null' ? '' : value
    })
    return result
  }
  // Wait for both operations even when one fails. A late upload cannot cross into a retry.
  async function pair(first, second) {
    var results = await Promise.all([first, second].map(function (promise) {
      return Promise.resolve(promise).then(function (value) { return { value: value } }, function (error) { return { error: error } })
    }))
    var failure = results.find(function (result) { return result.error })
    if (failure) throw failure.error
    return results.map(function (result) { return result.value })
  }
  function create(options) {
    var context = Object.assign({}, options.params)
    var state = { ready: false, busy: false, dirty: false, phase: 'idle', message: '', workId: context.workId || '' }
    function notify(phase, message) { state.phase = phase; state.message = message; options.notify(Object.assign({}, state)) }
    function accepts(type) { return (options.acceptedTypes || ['1', '2']).includes(String(type)) }
    function hasFile(value) { return typeof value === 'string' && Boolean(value.trim()) }
    async function readUnit(id) {
      if (typeof options.unit !== 'function') throw new Error('课程信息暂时不可用')
      var unit = await options.unit(id)
      if (!unit || typeof unit !== 'object') throw new Error('课程信息暂时不可用')
      if (unit.id && String(unit.id) !== String(id)) throw new Error('课程单元信息不一致')
      if (unit.courseWorkType !== undefined && unit.courseWorkType !== null && unit.courseWorkType !== '' && !accepts(unit.courseWorkType)) throw new Error('课程练习类型不匹配')
      if (unit.mineWorkId !== undefined && unit.mineWorkId !== null && typeof unit.mineWorkId !== 'string') throw new Error('课程作品编号不可用')
      return unit
    }
    async function readWork(id) {
      var info = await options.info(id)
      if (!info || !hasFile(info.workFileKey_url) || !accepts(info.workType)) throw new Error('作品信息不完整或类型不匹配')
      if (info.id && String(info.id) !== String(id)) throw new Error('作品编号与读取结果不一致')
      return info
    }
    async function load() {
      if (state.busy) return false
      state.busy = true; state.ready = false; notify('loading', '正在打开作品…')
      try {
        var title = context.workName || options.defaultTitle || 'Scratch 作品', url = context.workFile || options.defaultFile || './static/project.sb3'
        var workId = state.workId, reset = context.resetTemplate === '1', next = Object.assign({}, context), unit, info
        var fromUnit = !workId && Boolean(context.unitId)
        // Course links carry template URLs, but only this lookup can establish that no saved work exists.
        if (fromUnit) {
          unit = await readUnit(context.unitId)
          workId = unit.mineWorkId || ''
        }
        if (workId) {
          info = await readWork(workId)
          if (fromUnit && String(info.courseId || '') !== String(context.unitId)) throw new Error('作品与课程单元不一致')
          if (reset && (context.unitId && String(info.courseId || '') !== String(context.unitId) || context.additionalId && String(info.additionalId || '') !== String(context.additionalId))) throw new Error('原作品与重做任务不一致')
          next.unitId = info.courseId || ''; next.additionalId = info.additionalId || ''; next.departId = info.departId || ''
          if (!reset) { title = info.workName || title; url = info.workFileKey_url }
          else if (next.unitId && !unit) unit = await readUnit(next.unitId)
          else if (!next.unitId && !hasFile(context.workFile)) throw new Error('重做模板文件不可用')
        }
        if (unit && (!workId || reset)) {
          if (!hasFile(unit.courseWork_url)) throw new Error('课程尚未提供练习文件')
          title = context.workName || unit.unitName || title; url = unit.courseWork_url
        }
        await options.open(url, title)
        options.opened(workId)
        // Commit identity and task metadata only after the chosen file has opened successfully.
        context = next; state.workId = workId
        state.ready = true; state.busy = false; state.dirty = context.resetTemplate === '1'
        notify('ready', state.dirty ? '已打开原始模板；保存后将更新这份作业。' : '作品已打开，可以继续编辑。')
        return true
      } catch (error) {
        state.busy = false
        notify('load-error', '未能打开作品。' + error.message + '；请重试，避免覆盖原作品。')
        return false
      }
    }
    async function save(status) {
      if (!state.ready || state.busy || ![0, 1].includes(status)) return false
      var title = String(options.title() || '').trim()
      if (!title || title.length > 64) { notify('save-error', '请填写 1–64 个字符的作品名称。'); return false }
      state.busy = true; notify('saving', status ? '正在提交作业，请保持页面打开…' : '正在保存草稿，请保持页面打开…')
      try {
        var snapshot = await options.capture()
        if (!snapshot || !snapshot.project || !snapshot.project.size || !snapshot.cover || !snapshot.cover.size) throw new Error('作品或封面生成失败')
        // Each call owns an immutable pair. Never retain a key from a previous save.
        var uploaded = await options.upload(title, snapshot)
        if (!uploaded || !uploaded.project || !uploaded.cover) throw new Error('作品文件登记不完整')
        var result = await options.submit({ id: state.workId, workName: title, workFile: uploaded.project, workCover: uploaded.cover,
          workType: options.workType || 2, workStatus: status, courseId: context.unitId || '', additionalId: context.additionalId || '', departId: context.departId || '',
          workScene: context.unitId ? 'course' : context.additionalId ? 'additional' : 'create', hasCloudData: Boolean(snapshot.hasCloudData) })
        if (!result || !result.id) throw new Error('服务器未返回作品编号，请到我的作品核对后重试')
        state.workId = result.id; context.resetTemplate = ''; state.dirty = false
        options.saved(result.id)
        state.busy = false
        notify('saved', status ? '作业已提交。再次修改会更新同一份作品。' : '草稿已保存。下次打开可继续编辑，完成后再提交。')
        return true
      } catch (error) {
        state.busy = false; state.dirty = true
        notify('save-error', '保存未完成。' + error.message + '；作品仍在当前页面，可重试或保存到电脑。')
        return false
      }
    }
    function changed() {
      if (!state.ready || state.busy) return
      state.dirty = true; notify('dirty', '有未保存的修改。离开前请保存草稿或提交作业。')
    }
    return { load: load, save: save, changed: changed, state: state }
  }
  return { query: query, pair: pair, create: create }
})
