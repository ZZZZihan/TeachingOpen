const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { resolve } = require('node:path')
const { test } = require('node:test')
const vm = require('node:vm')
const Vue = require('vue')

test('暖缓存菜单在鉴权拒绝后撤销，导航同步更新且能显示新菜单', () => {
  const source = readFileSync(resolve(__dirname, '../src/views/home/modules/Header.vue'), 'utf8')
  const script = source.match(/<script>([\s\S]*?)<\/script>/)[1]
    .replace(/^import .*$/gm, '').replace('export default', 'this.component =')
  const context = { window: { removeEventListener: () => {} }, TMenu: {}, mapActions: () => ({}), mapGetters: () => ({ avatar: () => null }),
    getFileAccessHttpUrl: value => value }
  vm.runInNewContext(script, context)
  const state = Vue.observable({ user: { menuList: [{ title: '旧菜单' }] } })
  const store = { state, getters: { sysConfig: {} } }
  Object.defineProperty(store.getters, 'menuList', { get: () => state.user.menuList })
  const header = new Vue({ ...context.component, beforeCreate () { this.$store = store } })
  assert.equal(header.menus[0].title, '旧菜单')
  state.user.menuList = []
  assert.equal(header.menus.length, 0, '后台撤销应立即从导航移除旧菜单')
  state.user.menuList = [{ title: '新菜单' }]
  assert.equal(header.menus[0].title, '新菜单')
  header.$destroy()
})
