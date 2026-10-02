/* Same-origin child: recreating it on load/retry also cancels stale vendor callbacks. */
(function () {
  'use strict'
  function call(method) {
    if (window.parent === window || !window.parent.TeachingJunior) return
    window.parent.TeachingJunior[method](window)
  }
  window.scratchJrPage = 'editor'
  window.JrConfig = {
    onLoaded: function () { call('loaded') },
    onChanged: function () { call('changed') },
    requestSave: function () { call('save') }
  }
  window.addEventListener('error', function () { call('failed') })
})()
