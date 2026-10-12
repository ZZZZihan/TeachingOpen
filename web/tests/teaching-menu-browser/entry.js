import Vue from 'vue'
import Vuex from 'vuex'
import VueRouter from 'vue-router'
import Antd from 'ant-design-vue'
import 'ant-design-vue/dist/antd.css'
import Header from 'fixture-header'
Vue.use(Vuex); Vue.use(VueRouter); Vue.use(Antd)
Vue.ls = { get: () => null }
const store = new Vuex.Store({ state: { user: { token: null, menuList: [] } }, getters: { userInfo: () => null, sysConfig: () => ({ brandName: '菜单安全合成环境' }) } })
const router = new VueRouter({ routes: [{ path: '*', component: { render: h => h('p', '站内页面') } }] })
const leaf = (id, title, url, extra = {}) => ({ id, title, url, route: false, internalOrExternal: false, needLogin: 0, ...extra })
window.__menuProbe = { top: 0, group: 0, child: 0 }
const fixtures = {
  unsafe: [leaf('top', '历史危险顶级', 'javascript:void(window.__menuProbe.top+=1)'), leaf('group', '历史危险分组', 'javascript:void(window.__menuProbe.group+=1)', { children: [leaf('child', '历史危险子项', 'javascript:void(window.__menuProbe.child+=1)'), leaf('safe-child', '正常子项', '/safe-child', { route: true })] })],
  route: [leaf('route', '站内课程', '/courseList?source=menu#safe', { route: true })],
  native: [leaf('native', '静态编辑器', '/scratch3/index.html?scene=create')],
  https: [leaf('https', 'HTTPS 同页', 'https://menu-fixture.invalid/learning')],
  popup: [leaf('popup', 'HTTPS 新页', 'https://menu-fixture.invalid/learning', { route: true, internalOrExternal: true })],
  group: [leaf('safe-group', '正常分组', '/courseList', { route: true, children: [leaf('normal-child', '正常子项', '/safe-child', { route: true })] })]
}
new Vue({ store, router, render: h => h('div', { attrs: { id: 'app' } }, [h(Header), h('main', { style: { padding: '40px' } }, [h('h1', '真实 Header + TMenu 导航回归'), h('p', '独立合成菜单；危险链接只增加当前页面的无害计数器。外链请求由测试浏览器拦截。'), h('router-view')])]) }).$mount('#app')
window.setFixture = async name => { store.state.user.menuList = fixtures[name]; await Vue.nextTick(); return true }
window.__headerFixtureReady = true
window.setFixture('unsafe')
