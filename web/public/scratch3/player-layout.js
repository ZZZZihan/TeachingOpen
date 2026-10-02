/* The bundled player fixes its stage scale at boot. Fit the complete stage
 * (canvas, monitors and overlays) without reloading the running project.
 * Keep the controls at their native size and leave fullscreen to the engine.
 * These class prefixes belong to the checked-in Scratch player bundle. */
(function () {
  var root = document.getElementById('scratch')
  if (!root) return
  var pending = false
  function assign (node, name, value) {
    if (node.style[name] !== value) node.style[name] = value
  }
  function fit () {
    pending = false
    var stage = root.querySelector('[class*="stage_stage_"]')
    var wrapper = root.querySelector('[class*="stage_stage-wrapper_"]')
    var area = root.querySelector('[class*="stage-wrapper_stage-canvas-wrapper_"]')
    if (!stage || !wrapper || !area) return
    if (stage.className.indexOf('stage_full-screen_') !== -1) {
      for (var name of ['width', 'height', 'transform', 'transformOrigin']) assign(wrapper, name, '')
      assign(area, 'height', '')
      return
    }
    var width = stage.offsetWidth
    var height = stage.offsetHeight
    if (!width || !height || !area.clientWidth) return
    var scale = area.clientWidth / width
    assign(wrapper, 'width', width + 'px')
    assign(wrapper, 'height', height + 'px')
    assign(wrapper, 'transformOrigin', 'top left')
    assign(wrapper, 'transform', 'scale(' + scale + ')')
    assign(area, 'height', height * scale + 'px')
  }
  function schedule () {
    if (!pending) { pending = true; window.requestAnimationFrame(fit) }
  }
  // React inserts the stage asynchronously and changes its class at fullscreen.
  // Ignore style mutations from our own fit to avoid an observer feedback loop.
  var mutation = new MutationObserver(schedule)
  mutation.observe(root, { childList: true, subtree: true, attributes: true, attributeFilter: ['class'] })
  var resize = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(schedule)
  if (resize) resize.observe(root)
  window.addEventListener('resize', schedule)
  window.addEventListener('pagehide', function (event) {
    if (event.persisted) return
    mutation.disconnect()
    if (resize) resize.disconnect()
    window.removeEventListener('resize', schedule)
  })
  schedule()
})()
