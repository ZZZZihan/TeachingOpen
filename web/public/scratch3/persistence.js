/* Readable persistence boundary for the inherited Scratch VM. */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory()
  else root.ScratchPersistence = factory()
})(typeof window !== 'undefined' ? window : this, function () {
  'use strict'
  function query(search) {
    var params = new URLSearchParams(search), standard = params.get('queryEncoding') === 'uri', result = {}
    ;['workId', 'unitId', 'departId', 'additionalId', 'workName', 'scene', 'workFile', 'resetTemplate'].forEach(function (key) {
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
    async function load() {
      if (state.busy) return false
      state.busy = true; state.ready = false; notify('loading', '正在打开作品…')
      try {
        var title = context.workName || 'Scratch 作品', url = context.workFile || './static/project.sb3'
        if (state.workId && context.resetTemplate !== '1') {
          var info = await options.info(state.workId)
          if (!info || !info.workFileKey_url || !['1', '2'].includes(String(info.workType))) throw new Error('作品信息不完整或类型不匹配')
          title = info.workName || title; url = info.workFileKey_url
          context.unitId = info.courseId || ''; context.additionalId = info.additionalId || ''; context.departId = info.departId || ''
        } else if (!context.workFile && context.unitId) {
          var unit = await options.unit(context.unitId)
          if (!unit || !unit.courseWork_url) throw new Error('课程尚未提供练习文件')
          title = context.workName || unit.unitName || title; url = unit.courseWork_url
        }
        await options.open(url, title)
        options.opened(state.workId)
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
          workType: 2, workStatus: status, courseId: context.unitId || '', additionalId: context.additionalId || '', departId: context.departId || '',
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
