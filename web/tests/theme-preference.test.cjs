const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { resolve } = require('node:path')
const vm = require('node:vm')
const { test } = require('node:test')
const compiler = require('vue-template-compiler')

const source = file => readFileSync(resolve(__dirname, '../src', file), 'utf8')
const stripImports = text => text.replace(/^\s*import\s+(?:[^;'"\n]+?\s+from\s+)?['"][^'"\n]+['"];?[^\n]*$/gm, '')
    .replace(/^\s*import\s*\{[\s\S]*?\}\s*from\s*['"][^'"]+['"];?/gm, '')
const keys = {}
vm.runInNewContext(source('store/mutation-types.js').replace(/export const (\w+)\s*=/g, 'this.$1 ='), keys)
const helpers = { ...keys }
vm.runInNewContext(stripImports(source('utils/themePreference.js')).replace(/export function /g, 'function ') +
    '\nthis.helpers = { restoreThemeColor, sameThemeColor, themeColorOptions, themeColorLabel }', helpers)
const { restoreThemeColor, sameThemeColor, themeColorOptions, themeColorLabel } = helpers.helpers
const config = {}
vm.runInNewContext(source('defaultSettings.js').replace('export default', 'this.config ='), config)
const defaultColor = config.config.primaryColor
const palette = {}
vm.runInNewContext(stripImports(source('components/tools/setting.js')).replace(/export \{[^}]+\}/, '') + '\nthis.colors = colorList', palette)

function harness (cached, extra = {}) {
    const data = new Map(Object.entries({ ...extra }))
    if (cached !== undefined) data.set(keys.DEFAULT_COLOR, cached)
    const writes = []
    const storage = {
        get: (key, fallback = null) => data.has(key) ? data.get(key) : fallback,
        set (key, value) { writes.push([key, value]); data.set(key, value) }
    }
    const properties = new Map()
    const context = { ...keys, Vue: { ls: storage }, document: { documentElement: { style: {
        setProperty: (key, value) => properties.set(key, value)
    } } } }
    vm.runInNewContext(stripImports(source('store/modules/app.js')).replace('export default app', 'this.app = app'), context)
    const app = context.app
    const commit = (name, value) => app.mutations[name](app.state, value)
    const restore = () => commit('TOGGLE_COLOR', restoreThemeColor(storage, defaultColor))
    return { data, storage, writes, properties, app, commit, restore,
        choose: color => app.actions.ToggleColor({ commit }, color) }
}

test('自动保存的旧默认色大小写均迁移，保留原值用于回退且刷新幂等', () => {
    for (const legacy of ['#1890FF', '#1890ff', '#1890Ff']) {
        const h = harness(legacy, { DEFAULT_THEME: 'dark', USER_INFO: { id: 'synthetic' }, SYS_CONFIG: { brandName: '定制课堂' } })
        const other = [...h.data].filter(([key]) => key !== keys.DEFAULT_COLOR)
        h.restore()
        assert.equal(h.app.state.color, defaultColor)
        assert.equal(h.storage.get(keys.DEFAULT_COLOR), defaultColor)
        assert.equal(h.properties.get('--app-primary-color'), defaultColor)
        assert.equal(h.storage.get(keys.DEFAULT_COLOR_LEGACY), legacy)
        assert.equal(h.storage.get(keys.DEFAULT_COLOR_USER_CHOICE), null)
        assert.deepEqual([...h.data].filter(([key]) => ![keys.DEFAULT_COLOR, keys.DEFAULT_COLOR_LEGACY].includes(key)), other)
        h.restore()
        assert.equal(h.storage.get(keys.DEFAULT_COLOR_LEGACY), legacy)
        assert.equal(h.app.state.color, defaultColor)
    }
})

test('首次访问或无效空缓存使用新默认，不误备份或标记用户主动选择', () => {
    for (const value of [undefined, null, '', ' ', {}, false]) {
        const h = harness(value)
        h.restore()
        assert.equal(h.app.state.color, defaultColor)
        assert.equal(h.storage.get(keys.DEFAULT_COLOR_LEGACY), null)
        assert.equal(h.storage.get(keys.DEFAULT_COLOR_USER_CHOICE), null)
    }
})

test('所有既有非默认色与任意自定义色保持原值，重复启动不覆盖', () => {
    for (const color of [...palette.colors.map(item => item.color), '#123abc', '#722ed1']) {
        const h = harness(color)
        h.restore(); h.restore()
        assert.equal(h.app.state.color, color)
        assert.equal(h.storage.get(keys.DEFAULT_COLOR), color)
        assert.equal(h.storage.get(keys.DEFAULT_COLOR_LEGACY), null)
        assert.equal(h.properties.get('--app-primary-color'), color)
    }
})

test('显式设置选择在刷新后保留，包括用户重新选用旧蓝色', () => {
    const h = harness('#1890FF')
    h.restore()
    for (const color of ['#722ED1', '#1890FF', '#1890ff', defaultColor]) {
        h.choose(color)
        assert.equal(h.storage.get(keys.DEFAULT_COLOR_USER_CHOICE), color)
        h.restore()
        assert.equal(h.app.state.color, color)
        assert.equal(h.properties.get('--app-primary-color'), color)
    }
    assert.equal(h.storage.get(keys.DEFAULT_COLOR_LEGACY), '#1890FF')
})

test('过时的主动选择记录不保护另一个旧默认值，也不覆盖已有回退记录', () => {
    const h = harness('#1890ff', { DEFAULT_COLOR_USER_CHOICE: '#722ED1', DEFAULT_COLOR_LEGACY: '#1890FF' })
    h.restore()
    assert.equal(h.app.state.color, defaultColor)
    assert.equal(h.storage.get(keys.DEFAULT_COLOR_LEGACY), '#1890FF')
})

test('设置抽屉和账户标签对新默认、大小写不同的原主题及任意自定义色有唯一选中项', () => {
    const drawer = compiler.parseComponent(source('components/setting/SettingDrawer.vue'))
    const context = { DetailList: {}, SettingItem: {}, config: config.config, colorList: palette.colors,
        mixin: {}, mixinDevice: {}, sameThemeColor, themeColorOptions, updateTheme () {}, updateColorWeak () {}, triggerWindowResizeEvent () {} }
    vm.runInNewContext(stripImports(drawer.script.content).replace('export default', 'this.drawer ='), context)
    assert.match(drawer.template.content, /v-for="\(item, index\) in themeColors"/)
    assert.match(drawer.template.content, /sameThemeColor\(item.color, primaryColor\)/)
    for (const color of [defaultColor, '#722ED1', '#722ed1', '#123abc', '#1890FF']) {
        const colors = context.drawer.computed.themeColors.call({ colorList: palette.colors, primaryColor: color })
        assert.equal(colors.filter(item => context.drawer.methods.sameThemeColor(item.color, color)).length, 1)
        assert.ok(themeColorLabel(palette.colors, color))
    }
    assert.equal(themeColorLabel(palette.colors, defaultColor), '科技蓝（默认）')
    assert.equal(themeColorLabel(palette.colors, '#123abc'), '自定义色')
})

test('实际启动流程在根实例构造及抽屉挂载前恢复颜色，冷启动也恢复自定义主题', async () => {
    for (const [cached, expected] of [['#1890FF', defaultColor], ['#722ED1', '#722ED1'], [undefined, defaultColor]]) {
        const h = harness(cached)
        let constructed = false
        const compiledColors = []
        const drawer = compiler.parseComponent(source('components/setting/SettingDrawer.vue'))
        const drawerContext = { DetailList: {}, SettingItem: {}, config: config.config, colorList: palette.colors,
            mixin: {}, mixinDevice: {}, sameThemeColor, themeColorOptions, updateTheme: color => compiledColors.push(color),
            updateColorWeak () {}, triggerWindowResizeEvent () {}, setTimeout () {} }
        vm.runInNewContext(stripImports(drawer.script.content).replace('export default', 'this.drawer ='), drawerContext)
        function FakeVue (options) {
            assert.equal(h.app.state.color, expected, 'child components must observe restored color')
            drawerContext.drawer.mounted.call({ primaryColor: h.app.state.color, colorWeak: config.config.colorWeak,
                multipage: config.config.multipage })
            constructed = true
            this.$mount = () => this
        }
        FakeVue.use = () => {}
        FakeVue.config = {}
        FakeVue.ls = h.storage
        const context = { ...keys, Vue: FakeVue, App: {}, Storage: {}, router: {}, config: config.config,
            store: { getters: {}, commit: (name, value) => { if (name === 'TOGGLE_COLOR') h.commit(name, value) } },
            restoreThemeColor, window: { document: { getElementById: () => null } },
            loadStartupData: async () => ({ sysConfig: {}, isCurrent: () => true }), showStartupError () {},
            getSysConfig () {}, getMenu () {}, platformBrandName () {} }
        for (const key of ['Antd', 'VueAxios', 'hasPermission', 'JDictSelectTag', 'Print', 'preview', 'vueBus', 'JeecgComponents', 'VueAreaLinkage', 'VueAwesomeSwiper', 'vcolorpicker']) context[key] = {}
        vm.runInNewContext(stripImports(source('main.js')).replace(/start\(\)\s*$/, 'this.ready = start()'), context)
        await context.ready
        assert.equal(constructed, true)
        assert.deepEqual(compiledColors, expected === defaultColor ? [] : [expected])
    }
})


test('主动重选同一颜色仍记录来源并重新编译，失败后可通过原色重试', () => {
    const drawer = compiler.parseComponent(source('components/setting/SettingDrawer.vue'))
    const h = harness('#722ED1')
    h.restore()
    const compiled = []
    const context = { DetailList: {}, SettingItem: {}, config: config.config, colorList: palette.colors,
        mixin: {}, mixinDevice: {}, sameThemeColor, themeColorOptions, updateTheme: color => compiled.push(color),
        updateColorWeak () {}, triggerWindowResizeEvent () {} }
    vm.runInNewContext(stripImports(drawer.script.content).replace('export default', 'this.drawer ='), context)
    const component = { primaryColor: h.app.state.color, $store: {
        dispatch (action, color) { assert.equal(action, 'ToggleColor'); h.choose(color) }
    } }
    context.drawer.methods.changeColor.call(component, component.primaryColor)
    context.drawer.methods.changeColor.call(component, component.primaryColor)
    assert.deepEqual(compiled, ['#722ED1', '#722ED1'])
    assert.equal(h.storage.get(keys.DEFAULT_COLOR_USER_CHOICE), '#722ED1')
    h.restore()
    assert.equal(h.app.state.color, '#722ED1')
})
