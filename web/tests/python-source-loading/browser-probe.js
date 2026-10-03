/* Optional small snapshot helper for an owned loopback editor/player.
 * Root performs the actual route controls, interactions and screenshots. */
(function () {
  'use strict'
  function host () {
    var queue = Array.from(document.querySelectorAll('*')).map(function (node) { return node.__vue__ }).filter(Boolean), seen = new Set()
    while (queue.length) {
      var instance = queue.shift()
      if (seen.has(instance)) continue
      seen.add(instance)
      if (instance.$options && instance.$options.name === 'PythonEditor') return instance
      queue.push.apply(queue, instance.$children || [])
    }
    throw new Error('Actual mounted PythonEditor not found')
  }
  function snapshot () {
    var value = host(), child = value.$refs.codeEditor, raw = child && (child.editor || child.coder)
    var status = document.getElementById('persistence-status'), retry = document.getElementById('retry-load')
    return { phase: status && status.dataset.phase, message: status && status.textContent,
      retryVisible: !!retry && !retry.hidden, editorReady: !!raw && typeof raw.getValue === 'function', code: raw && raw.getValue ? raw.getValue() : null, title: value.projectName || '',
      persistReady: value.persistReady, persistBusy: value.persistBusy, sourceReady: value.sourceReady, sourceBusy: value.sourceBusy,
      readOnly: !raw ? null : raw.getReadOnly ? raw.getReadOnly() : raw.getOption('readOnly'),
      buttons: Array.from(document.querySelectorAll('button')).map(function (button) { return { text: button.textContent.trim(), title: button.title, disabled: button.disabled } }),
      entryScripts: Array.from(document.scripts).map(function (script) { return script.src }).filter(function (src) { return /\/app(?:Player)?\.js$/.test(src) }),
      frameCount: document.querySelectorAll('#mycanvas iframe').length }
  }
  window.TeachingPythonSourceProbe = { host: host, snapshot: snapshot }
}())
