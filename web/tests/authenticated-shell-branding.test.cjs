const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { resolve } = require('node:path')
const { test } = require('node:test')
const vm = require('node:vm')
const Vue = require('vue')
const Vuex = require('vuex')
const compiler = require('vue-template-compiler')
const Avatar = require('ant-design-vue/lib/avatar/Avatar').default

Vue.use(Vuex)
const source = file => readFileSync(resolve(__dirname, '../src', file), 'utf8')
const helpers = {}
vm.runInNewContext(source('utils/platformBranding.js').replace(/export /g, '') +
  '\nthis.helpers = { brandingValue, platformBrandName, platformPageTitle }', helpers)
const { brandingValue, platformBrandName, platformPageTitle } = helpers.helpers
const platform = '天津工业大学 · 人工智能教学平台'
const invalid = [undefined, null, '', ' \n\t ', false, true, 0, 42, NaN, {}, [], ['品牌']]
const stub = { render (h) { return h('div', this.$slots.default) } }
const mixins = { ...Vuex }
vm.runInNewContext(source('utils/mixin.js').replace(/^import [^\n]+$/gm, '')
    .replace('export { mixin, mixinDevice }', 'this.mixin = mixin; this.mixinDevice = mixinDevice'), mixins)

function makeStore (config, avatar = '') {
    return new Vuex.Store({
        state: { personalAvatar: avatar,
            user: { sysConfig: config, permissionList: [] },
            app: { device: 'desktop', multipage: false, fixedHeader: false, autoHideHeader: false, sidebar: { opened: true } } },
        getters: { sysConfig: state => state.user.sysConfig,
            avatar: state => state.personalAvatar,
            nickname: () => '合成学生',
            userInfo: () => ({ username: 'synthetic' }) },
        actions: { Logout () {} }
    })
}

// Evaluate the actual existing media URL resolver against the same reactive store.
function resolver (store) {
    const manage = source('api/manage.js')
    const start = manage.indexOf('export function getFileAccessHttpUrl(')
    assert.ok(start >= 0)
    const end = manage.indexOf('\n}', start) + 2
    const context = { store }
    vm.runInNewContext(manage.slice(start, end).replace('export ', ''), context)
    return context.getFileAccessHttpUrl
}

function component (file, store, extras = {}) {
    const parsed = compiler.parseComponent(source(file))
    const document = { title: '' }
    const context = {
        ...helpers.helpers,
        ...Vuex,
        document,
        window: { addEventListener () {}, removeEventListener () {} },
        mixin: mixins.mixin,
        mixinDevice: mixins.mixinDevice,
        getFileAccessHttpUrl: resolver(store),
        HeaderNotice: stub,
        UserPassword: stub,
        SettingDrawer: stub,
        DepartSelect: stub,
        UserMenu: stub,
        SMenu: stub,
        Logo: stub,
        GlobalLayout: stub,
        Contextmenu: stub,
        triggerWindowResizeEvent () {},
        ...extras
    }
    vm.runInNewContext(parsed.script.content.replace(/^\s*import [^\n]+$/gm, '')
        .replace('export default', 'this.component ='), context)
    const compiled = compiler.compileToFunctions(parsed.template.content)
    return { options: { ...context.component, render: compiled.render, staticRenderFns: compiled.staticRenderFns }, document }
}

function harness (file, config, props = {}, avatar = '') {
    const store = makeStore(config, avatar)
    const loaded = component(file, store)
    const route = Vue.observable({ path: '/teaching/workList', fullPath: '/teaching/workList', meta: { title: '学生作业批改' } })
    const pushes = []
    const instance = new Vue({ ...loaded.options,
        store,
        propsData: props,
        components: { ...loaded.options.components, 'a-avatar': Avatar },
        beforeCreate () {
            this.$route = route
            this.$router = { push: value => pushes.push(value) }
            this.$ls = { get () {} }
        }
    })
    return { instance,
        store,
        route,
        document: loaded.document,
        pushes,
        replaceConfig: value => { store.state.user.sysConfig = value } }
}

function nodes (vnode) {
    if (!vnode) return []
    const children = (vnode.children || []).concat(vnode.componentOptions ? vnode.componentOptions.children || [] : [])
    return [vnode, ...children.flatMap(nodes)]
}
const text = vnode => nodes(vnode).map(node => node.text || '').join('')
const image = vnode => nodes(vnode).find(node => node.tag === 'img')
const renderedAvatar = vnode => nodes(vnode).find(node => node.componentOptions && node.componentOptions.Ctor.options.name === 'AAvatar')

test('品牌值仅接受有效字符串，空白和对象不会泄漏到界面', () => {
    for (const value of invalid) assert.equal(brandingValue(value), '', String(value))
    assert.equal(brandingValue('  科学课堂\n '), '科学课堂')
    assert.equal(brandingValue('0'), '0')
})

test('平台名称在缺失或非法配置时可用，有效自定义配置优先且不修改输入', () => {
    for (const config of [undefined, null, {}, { brandName: ' \n ' }, { brandName: false }, { brandName: {} }]) {
        assert.equal(platformBrandName(config), platform)
    }
    const config = Object.freeze({ brandName: '  另一所学校的课堂  ' })
    assert.equal(platformBrandName(config), '另一所学校的课堂')
    assert.equal(config.brandName, '  另一所学校的课堂  ')
})

test('页面标题避免 undefined 或无效路由名，保留有效标题和自定义品牌', () => {
    for (const title of invalid) assert.equal(platformPageTitle({}, title), platform)
    assert.equal(platformPageTitle({}, '  我的课程  '), '我的课程 · ' + platform)
    assert.equal(platformPageTitle({ brandName: '  课程站  ' }, '作业反馈'), '作业反馈 · 课程站')
    assert.equal(platformPageTitle(null, '课表'), '课表 · ' + platform)
})

test('真实 GlobalHeader 默认模板显示学校平台名，缺配置不会抛错', () => {
    for (const config of [undefined, null, {}, { brandName: ' \n ' }, { brandName: 123 }]) {
        const h = harness('components/page/GlobalHeader.vue', config, { menus: [] })
        assert.equal(h.instance.brandName, platform)
        assert.ok(text(h.instance._render()).includes(platform))
        h.instance.$destroy()
    }
})

test('真实 GlobalHeader 对品牌修改和整份配置替换立即响应', async () => {
    const h = harness('components/page/GlobalHeader.vue', { brandName: '旧名称' }, { menus: [] })
    assert.match(text(h.instance._render()), /旧名称/)
    h.store.state.user.sysConfig.brandName = '  新名称  '
    await Vue.nextTick()
    assert.equal(h.instance.brandName, '新名称')
    assert.match(text(h.instance._render()), /新名称/)
    h.replaceConfig({})
    await Vue.nextTick()
    assert.equal(h.instance.brandName, platform)
    assert.ok(!text(h.instance._render()).includes('旧名称'))
    h.instance.$destroy()
})

test('真实 Logo 无有效图片时显示天工文字 mark，展开和收起均不请求旧 logo', () => {
    for (const config of [undefined, null, {}, { logo: ' \n ' }, { logo: {} }]) {
        for (const showTitle of [true, false]) {
            const h = harness('components/tools/Logo.vue', config, { showTitle })
            const tree = h.instance._render()
            assert.equal(image(tree), undefined)
            assert.match(text(tree), /天工/)
            if (showTitle) assert.ok(text(tree).includes(platform))
            h.instance.$destroy()
        }
    }
})

test('真实 Logo 继续使用既有媒体解析器处理相对自定义图片', () => {
    const h = harness('components/tools/Logo.vue', { brandName: '自定义平台', logo: '  logos/custom.png  ', uploadType: 'local', staticDomain: '/files' })
    const tree = h.instance._render()
    assert.equal(image(tree).data.attrs.src, '/files/logos/custom.png')
    assert.ok(text(tree).includes('自定义平台'))
    h.instance.$destroy()
})

test('真实 Logo 保留完整自定义 HTTP 地址及七牛文件路径', () => {
    for (const [config, expected] of [
        [{ logo: 'https://assets.example.invalid/logo.svg', uploadType: 'local', staticDomain: '/files' }, 'https://assets.example.invalid/logo.svg'],
        [{ logo: 'logo.svg', uploadType: 'qiniu', qiniuDomain: 'https://cdn.example.invalid' }, 'https://cdn.example.invalid/logo.svg']
    ]) {
        const h = harness('components/tools/Logo.vue', config)
        assert.equal(image(h.instance._render()).data.attrs.src, expected)
        h.instance.$destroy()
    }
})

test('真实 Logo 图片失败后回退文字，新配置恢复图片而旧失败状态不残留', async () => {
    const h = harness('components/tools/Logo.vue', { logo: 'bad.png', uploadType: 'local', staticDomain: '/files' })
    const first = image(h.instance._render())
    assert.equal(first.data.attrs.src, '/files/bad.png')
    assert.equal(typeof first.data.on.error, 'function')
    first.data.on.error()
    await Vue.nextTick()
    assert.equal(image(h.instance._render()), undefined)
    assert.match(text(h.instance._render()), /天工/)
    h.replaceConfig({ brandName: '恢复平台', logo: 'good.png', uploadType: 'local', staticDomain: '/files' })
    await Vue.nextTick()
    assert.equal(image(h.instance._render()).data.attrs.src, '/files/good.png')
    assert.ok(text(h.instance._render()).includes('恢复平台'))
    h.store.state.user.sysConfig.logo = ''
    await Vue.nextTick()
    assert.equal(image(h.instance._render()), undefined)
    h.instance.$destroy()
})

test('真实 Logo 的品牌不是创建时快照，配置变更更新可见文字', async () => {
    const h = harness('components/tools/Logo.vue', { brandName: '旧平台' })
    h.store.state.user.sysConfig.brandName = '新平台'
    await Vue.nextTick()
    assert.equal(h.instance.brandName, '新平台')
    assert.ok(text(h.instance._render()).includes('新平台'))
    h.replaceConfig(null)
    await Vue.nextTick()
    assert.equal(h.instance.brandName, platform)
    h.instance.$destroy()
})

test('真实 UserMenu 个人头像优先于平台配置，并通过实际文件解析器', () => {
    const h = harness('components/tools/UserMenu.vue', { avatar: 'platform.png', uploadType: 'local', staticDomain: '/files' }, {}, ' personal.png ')
    assert.equal(h.instance.getAvatar(), '/files/personal.png')
    const avatar = renderedAvatar(h.instance._render())
    assert.ok(avatar)
    assert.equal(avatar.componentOptions.propsData.src, '/files/personal.png')
    assert.equal(avatar.componentOptions.propsData.icon, 'user')
    h.instance.$destroy()
})

test('真实 UserMenu 无个人头像时沿用有效平台头像和既有七牛域名', () => {
    for (const [config, expected] of [
        [{ avatar: 'default.png', uploadType: 'local', staticDomain: '/files' }, '/files/default.png'],
        [{ avatar: 'default.png', uploadType: 'local', staticDomain: '/files', qiniuDomain: 'https://cdn.example.invalid' }, 'https://cdn.example.invalid/default.png'],
        [{ avatar: 'https://assets.example.invalid/default.png', uploadType: 'local', staticDomain: '/files' }, 'https://assets.example.invalid/default.png']
    ]) {
        const h = harness('components/tools/UserMenu.vue', config)
        assert.equal(h.instance.getAvatar(), expected)
        h.instance.$destroy()
    }
})

test('个人头像被既有解析器拒绝时仍采用有效配置头像，不返回空图片', () => {
    const h = harness('components/tools/UserMenu.vue', { avatar: 'default.png', uploadType: 'local', staticDomain: '/files' }, {}, '[invalid]')
    assert.equal(resolver(h.store)('[invalid]'), undefined, '实际 resolver 拒绝历史数组字符串')
    assert.equal(h.instance.getAvatar(), '/files/default.png')
    assert.equal(renderedAvatar(h.instance._render()).componentOptions.propsData.src, '/files/default.png')
    h.instance.$destroy()
})

test('真实 UserMenu 缺失或非法头像使用中性 user 图标，不把学校 logo 作为个人头像', () => {
    for (const value of invalid) {
        const h = harness('components/tools/UserMenu.vue', { avatar: value }, {}, value)
        assert.equal(h.instance.getAvatar(), '')
        const vnode = renderedAvatar(h.instance._render())
        assert.equal(vnode.componentOptions.propsData.src, '')
        assert.equal(vnode.componentOptions.propsData.icon, 'user')
        const actualAvatar = new Vue({ ...Avatar, propsData: vnode.componentOptions.propsData })
        const tree = actualAvatar._render()
        assert.equal(image(tree), undefined)
        assert.ok(nodes(tree).some(node => node.componentOptions && node.componentOptions.propsData.type === 'user'))
        actualAvatar.$destroy()
        h.instance.$destroy()
    }
})

test('实际 AntD Avatar 图片加载失败时仍回退 user 图标', () => {
    const h = harness('components/tools/UserMenu.vue', { uploadType: 'local', staticDomain: '/files' }, {}, 'personal.png')
    const vnode = renderedAvatar(h.instance._render())
    const actualAvatar = new Vue({ ...Avatar, propsData: vnode.componentOptions.propsData })
    const first = image(actualAvatar._render())
    assert.ok(first)
    first.data.on.error()
    const tree = actualAvatar._render()
    assert.equal(image(tree), undefined)
    assert.ok(nodes(tree).some(node => node.componentOptions && node.componentOptions.propsData.type === 'user'))
    actualAvatar.$destroy()
    h.instance.$destroy()
})

test('真实 UserMenu 头像随用户和配置切换更新，缺配置也可安全渲染', async () => {
    const h = harness('components/tools/UserMenu.vue', null)
    assert.equal(h.instance.getAvatar(), '')
    assert.ok(renderedAvatar(h.instance._render()))
    h.replaceConfig({ avatar: 'default.png', uploadType: 'local', staticDomain: '/files' })
    await Vue.nextTick()
    assert.equal(h.instance.getAvatar(), '/files/default.png')
    h.store.state.personalAvatar = 'mine.png'
    await Vue.nextTick()
    assert.equal(renderedAvatar(h.instance._render()).componentOptions.propsData.src, '/files/mine.png')
    h.store.state.personalAvatar = ''
    await Vue.nextTick()
    assert.equal(h.instance.getAvatar(), '/files/default.png')
    h.instance.$destroy()
})

test('真实 TabLayout 标题处理首页、有效路由名和缺失标题', async () => {
    const h = harness('components/layouts/TabLayout.vue', {})
    await Vue.nextTick()
    h.instance.changeTitle(undefined)
    assert.equal(h.document.title, platform)
    h.instance.changeTitle('  班级管理  ')
    assert.equal(h.document.title, '班级管理 · ' + platform)
    h.route.path = '/dashboard/index'
    h.instance.changeTitle('首页')
    assert.equal(h.document.title, platform)
    h.instance.$destroy()
})

test('真实 TabLayout 品牌配置变更刷新当前路由标题，不保留旧学校名称', async () => {
    const h = harness('components/layouts/TabLayout.vue', { brandName: '旧平台' })
    await Vue.nextTick()
    h.instance.changeTitle(h.route.meta.title)
    assert.equal(h.document.title, '学生作业批改 · 旧平台')
    h.store.state.user.sysConfig.brandName = '  新平台  '
    await Vue.nextTick()
    assert.equal(h.document.title, '学生作业批改 · 新平台')
    h.replaceConfig(null)
    await Vue.nextTick()
    assert.equal(h.document.title, '学生作业批改 · ' + platform)
    h.instance.$destroy()
})

test('真实 TabLayout 首页在配置刷新后仍只显示平台名称', async () => {
    const h = harness('components/layouts/TabLayout.vue', { brandName: '原平台' })
    await Vue.nextTick()
    h.route.path = '/dashboard/index'
    h.route.fullPath = '/dashboard/index'
    h.route.meta.title = '首页'
    h.instance.changeTitle('首页')
    assert.equal(h.document.title, '原平台')
    h.replaceConfig({ brandName: '更新平台' })
    await Vue.nextTick()
    assert.equal(h.document.title, '更新平台')
    h.instance.$destroy()
})
