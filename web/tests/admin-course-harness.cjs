const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const cp = require('node:child_process')
const babel = require('@babel/core')
const root = path.resolve(__dirname, '..')
const baseline = 'fbf8097'
const flush = () => new Promise(resolve => setImmediate(resolve))

// Execute the real component and inherited mixin methods with controlled API order.
// Vue rendering and keyboard/layout behavior are checked separately in the CLI preview.
function mount (kind, { old = false, courseId } = {}) {
  const read = file => old ? cp.execFileSync('git', ['show', `${baseline}:web/${file}`], { cwd: root, encoding: 'utf8' }) : fs.readFileSync(path.join(root, file), 'utf8')
  const calls = [], notices = [], confirms = [], routes = [], entries = []
  const request = method => (url, data) => new Promise((resolve, reject) => calls.push({ method, url, data: { ...data }, resolve, reject }))
  const context = {
    component: null, JeecgListMixin: null, console: { log () {} }, Vue: { ls: { get: () => undefined } }, ACCESS_TOKEN: 'synthetic-unused',
    TeachingCourseModal: {}, TeachingCourseUnitModal: {}, JSelectDepart: {}, DictItemList: {}, JDictSelectTag: {},
    URL, Blob, Uint8Array, setTimeout, clearTimeout, getFileAccessHttpUrl: value => value,
    window: { _CONFIG: { domianURL: '' }, location: { origin: 'http://synthetic.local' }, navigator: {}, URL: { createObjectURL: () => 'blob:synthetic', revokeObjectURL () {} } },
    document: { createElement: () => ({ style: {}, setAttribute () {}, click () {}, remove () {} }), body: { appendChild () {}, removeChild () {} } },
    getAction: request('GET'), deleteAction: request('DELETE'), downFile: request('DOWNLOAD'),
    filterObj: null
  }
  vm.createContext(context)
  const util = read('src/utils/util.js').match(/export function filterObj\(obj\) \{[\s\S]*?\n\}/)[0].replace('export ', '')
  vm.runInContext(util, context)
  let mixin = read('src/mixins/JeecgListMixin.js').replace(/^import .*$/gm, '').replace('export const JeecgListMixin =', 'JeecgListMixin =')
  mixin = babel.transformSync(mixin, { cwd: root, babelrc: false, configFile: false, presets: [[require.resolve('@vue/babel-preset-app'), { useBuiltIns: false }]] }).code
  vm.runInContext(mixin, context)
  const source = read(`src/views/teaching/${kind === 'course' ? 'TeachingCourseList' : 'TeachingCourseUnitList'}.vue`)
  vm.runInContext(source.match(/<script>([\s\S]*?)<\/script>/)[1].replace(/^\s*import [^\n]*$/gm, '').replace('export default', 'component ='), context)
  const c = context.component, m = context.JeecgListMixin
  const i = { ...m.data(), ...c.data(), $route: { query: courseId ? { courseId } : {} },
    $message: Object.fromEntries(['success', 'warning', 'error', 'info'].map(type => [type, text => notices.push({ type, text })])),
    $confirm: value => { confirms.push(value); return { destroy () {} } }, $set: (o, k, v) => { o[k] = v }, $nextTick: fn => { if (fn) fn() },
    $router: { push: value => routes.push(value) }, $refs: { modalForm: { add: () => entries.push('add'), edit: row => entries.push({ edit: row }) }, dictItemList: { open: code => entries.push({ dict: code }) } }
  }
  for (const [key, fn] of Object.entries({ ...m.methods, ...c.methods })) i[key] = fn.bind(i)
  for (const [key, fn] of Object.entries({ ...m.computed, ...c.computed })) Object.defineProperty(i, key, { get: () => (typeof fn === 'function' ? fn : fn.get).call(i) })
  const created = () => { m.created?.call(i); c.created?.call(i) }
  const destroy = () => { m.beforeDestroy?.call(i); c.beforeDestroy?.call(i) }
  return { i, c, calls, notices, confirms, routes, entries, created, destroy }
}
const row = kind => kind === 'course' ? { id: 'synthetic-course-1', courseName: '合成观察课程', isShared: false, showHome: false } : { id: 'synthetic-unit-1', courseId: 'synthetic-course-1', unitName: '合成观察单元' }
const success = (kind, total = 1, records = [row(kind)]) => ({ success: true, result: { records, total } })
module.exports = { mount, flush, row, success, baseline }
