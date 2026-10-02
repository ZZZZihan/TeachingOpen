const assert = require('node:assert/strict')
const { test } = require('node:test')
const { readFileSync } = require('node:fs')
const { resolve } = require('node:path')
const vm = require('node:vm')

test('Scratch player: resize preserves stage and overlays, fullscreen releases overrides', () => {
  const stage = { offsetWidth: 722, offsetHeight: 542, className: 'stage_stage_hash' }
  const wrapper = { style: {} }; const area = { clientWidth: 338, style: {} }
  let inserted = false; let queued; let mutation; let resize; let disconnected = 0
  const listeners = new Map()
  const root = { querySelector: selector => inserted ? (selector.includes('stage_stage_') ? stage : selector.includes('canvas-wrapper') ? area : wrapper) : null }
  const window = { requestAnimationFrame: fn => { queued = fn }, addEventListener: (name, fn) => listeners.set(name, fn), removeEventListener: name => listeners.delete(name) }
  const context = { window, document: { getElementById: () => root }, MutationObserver: class { constructor (fn) { mutation = fn } observe () {} disconnect () { disconnected++ } }, ResizeObserver: class { constructor (fn) { resize = fn } observe () {} disconnect () { disconnected++ } } }
  vm.runInNewContext(readFileSync(resolve(__dirname, '../public/scratch3/player-layout.js'), 'utf8'), context)
  queued(); assert.equal(wrapper.style.transform, undefined)
  inserted = true; mutation(); queued()
  assert.equal(wrapper.style.transform, `scale(${338 / 722})`); assert.ok(Math.abs(parseFloat(area.style.height) - 542 * 338 / 722) < 0.001)
  area.clientWidth = 720; resize(); queued()
  assert.equal(wrapper.style.transform, `scale(${720 / 722})`); assert.equal(stage.offsetWidth, 722)
  stage.className += ' stage_full-screen_hash'; mutation(); queued()
  assert.equal(wrapper.style.transform, ''); assert.equal(wrapper.style.width, ''); assert.equal(area.style.height, '')
  stage.className = 'stage_stage_hash'; mutation(); queued()
  assert.equal(wrapper.style.transform, `scale(${720 / 722})`)
  listeners.get('pagehide')({ persisted: true }); assert.equal(disconnected, 0)
  listeners.get('pagehide')({ persisted: false }); assert.equal(disconnected, 2); assert.equal(listeners.has('resize'), false)
})
