const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { resolve } = require('node:path')
const { test } = require('node:test')
const vm = require('node:vm')
const Vue = require('vue')
const compiler = require('vue-template-compiler')
const less = require('less')
const moment = require('moment')
const DateTBody = require('ant-design-vue/lib/vc-calendar/src/date/DateTBody').default
const { css: { loaderOptions: { less: buildTheme } } } = require('../vue.config')

const root = resolve(__dirname, '../src')
const defaults = {}
vm.runInNewContext(readFileSync(resolve(root, 'defaultSettings.js'), 'utf8')
    .replace('export default', 'this.config ='), defaults)
const config = defaults.config
const component = file => compiler.parseComponent(readFileSync(resolve(root, file), 'utf8'))
const primaryRules = [
    ['components/page/GlobalLayout.vue', '.layout .header .user-wrapper .action .avatar', 'color'],
    ['components/page/GlobalLayout.vue', '.layout .top-nav-header-index .user-wrapper .action .avatar', 'color'],
    ['views/account/center/Index.vue', '.page-header-wrapper-grid-content-main .account-center-team .members a:hover span', 'color'],
    ['views/home/FriendDetail.vue', '.work-card .work-op a:hover', 'color'],
    ['views/home/NewsList.vue', '/deep/ .title:hover', 'color'],
    ['views/list/CardList.vue', '.ant-card-actions li a:hover', 'color'],
    ['views/dashboard/Workplace.vue', '.project-list .card-title a:hover', 'color'],
    ['views/dashboard/Workplace.vue', '.project-list .project-item a:hover', 'color'],
    ['views/dashboard/Workplace.vue', '.members a:hover span', 'color'],
    ['views/jeecg/ImagPreview.vue', '.clName .ant-tree li .ant-tree-node-content-wrapper.ant-tree-node-selected', 'background-color']
]

async function cssFor (file, primaryColor) {
    const parsed = component(file)
    const result = await less.render(parsed.styles.map(style => style.content).join('\n'), {
        ...buildTheme,
        filename: resolve(root, file),
        modifyVars: { ...buildTheme.modifyVars, 'primary-color': primaryColor, 'link-color': primaryColor }
    })
    return result.css
}

// Check emitted declarations on the real selectors, so a variable elsewhere in
// the source cannot hide a remaining override on the affected element.
function declaration (css, selector, property) {
    for (const match of css.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
        const selectors = match[1].split(',').map(value => value.trim().replace(/\s+/g, ' '))
        if (!selectors.includes(selector)) continue
        const values = match[2].split(';').map(value => value.trim())
        const value = values.find(value => value.startsWith(property + ':'))
        if (value) return value.slice(property.length + 1).trim().replace(/\s*!important$/, '')
    }
    assert.fail('Missing emitted ' + property + ' for ' + selector)
}

for (const [name, primaryColor] of [
    ['默认主题', buildTheme.modifyVars['primary-color']],
    ['自定义紫色主题', '#722ed1']
]) {
    test(name + '编译真实页面 Less，头像和交互状态均接入运行时主题并保留编译回退值', async () => {
        const styles = new Map()
        for (const file of new Set(primaryRules.map(([file]) => file))) {
            styles.set(file, await cssFor(file, primaryColor))
        }
        for (const [file, selector, property] of primaryRules) {
            assert.equal(declaration(styles.get(file), selector, property),
                'var(--app-primary-color, ' + primaryColor + ')', file + ': ' + selector)
        }
    })
}

function load (file, globals = {}) {
    const parsed = component(file)
    const context = { ...globals }
    vm.runInNewContext(parsed.script.content.replace(/^\s*import [^\n]+$/gm, '')
        .replace('export default', 'this.component ='), context)
    const compiled = compiler.compileToFunctions(parsed.template.content)
    return { ...context.component, render: compiled.render, staticRenderFns: compiled.staticRenderFns }
}

function nodes (node) {
    if (!node) return []
    return [node, ...(node.children || []).flatMap(nodes)]
}

function reportHarness (settings = config) {
    const stub = { render (h) { return h('div') } }
    const options = load('views/report/TeacherReport.vue', { moment, config: settings, Pie: stub, LineChartMultid: stub })
    const report = new Vue({ ...options, created: [] })
    const picker = nodes(report._render()).find(node => node.data && node.data.scopedSlots && node.data.scopedSlots.dateRender)
    assert.ok(picker, 'actual range picker retains its dateRender slot')
    return { report, dateRender: picker.data.scopedSlots.dateRender }
}

test('教师报表月初圆环读取默认配置回退值，同时保留运行时主题变量', () => {
    for (const settings of [config, { ...config, primaryColor: '#722ed1' }]) {
        const { report } = reportHarness(settings)
        const firstDay = report.getCurrentStyle({ date: () => 1 })
        assert.equal(firstDay.border, '1px solid var(--app-primary-color, ' + settings.primaryColor + ')')
        assert.equal(firstDay.borderRadius, '50%')
        assert.equal(Object.keys(report.getCurrentStyle({ date: () => 2 })).length, 0)
        report.$destroy()
    }
})

test('教师报表真实日期插槽只在每月第一天显示内联圆环，日期文本保持原值', () => {
    const { report, dateRender } = reportHarness()
    for (const day of [1, 2, 15, 31]) {
        const slot = dateRender({ date: () => day })
        const date = Array.isArray(slot) ? slot[0] : slot
        assert.equal(Boolean(date.data.style && date.data.style.border), day === 1)
        assert.equal(nodes(date).map(node => node.text || '').join('').trim(), String(day))
        if (day === 1) {
            assert.equal(date.data.style.border, '1px solid var(--app-primary-color, ' + config.primaryColor + ')')
            assert.equal(date.data.style.borderRadius, '50%')
        }
    }
    report.$destroy()
})

test('真实 AntD 日历将月初作为选中起止日期时，主题内联圆环仍保留且优先于透明边框', () => {
    const antdCss = readFileSync(require.resolve('ant-design-vue/lib/date-picker/style/index.css'), 'utf8')
    const { report, dateRender } = reportHarness()
    const firstDay = moment('2026-10-01')
    for (const [selectionClass, selectedValue] of [
        ['ant-calendar-selected-start-date', [firstDay, moment('2026-10-12')]],
        ['ant-calendar-selected-end-date', [moment('2026-09-12'), firstDay]]
    ]) {
        assert.equal(declaration(antdCss, '.ant-calendar-range .' + selectionClass + ' .ant-calendar-date', 'border'),
            '1px solid transparent', 'actual AntD selected-date rule would cover a less specific application class')
        const calendar = new Vue({ ...DateTBody, propsData: {
            prefixCls: 'ant-calendar', value: firstDay, selectedValue, dateRender
        } })
        const selected = nodes(calendar._render()).find(node => node.tag === 'td' && node.data.class.includes(selectionClass))
        assert.ok(selected, 'actual AntD calendar applies ' + selectionClass)
        const date = nodes(selected).find(node => node.data && node.data.staticClass === 'ant-calendar-date')
        assert.ok(date, 'actual report dateRender remains inside the selected AntD cell')
        assert.equal(date.data.style.border, '1px solid var(--app-primary-color, ' + config.primaryColor + ')')
        assert.equal(date.data.style.borderRadius, '50%')
        calendar.$destroy()
    }
    report.$destroy()
})

test('图表进度仍使用调用方传入的颜色，不把多色图表强行变成品牌色', () => {
    const chart = new Vue({ ...load('components/chart/MiniProgress.vue'), propsData: { color: '#a45125', percentage: 60 } })
    const progress = nodes(chart._render()).find(node => node.data && node.data.staticClass === 'progress')
    assert.equal(progress.data.style.backgroundColor, '#a45125')
    assert.equal(progress.data.style.width, '60%')
    chart.$destroy()
})
