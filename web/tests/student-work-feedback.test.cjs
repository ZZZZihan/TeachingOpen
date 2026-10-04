const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { resolve } = require('node:path')
const vm = require('node:vm')
const { test } = require('node:test')
const Vue = require('vue')
const compiler = require('vue-template-compiler')
const source = file => readFileSync(resolve(__dirname, '../src', file), 'utf8')
const helpers = {}
vm.runInNewContext(source('utils/studentWorkFeedback.js').replace('export function', 'function'), helpers)
const feedback = helpers.studentWorkFeedback
const stub = { render (h) { return h('div', this.$slots.default) } }

function component (file, imports = {}) {
    const parsed = compiler.parseComponent(source(file))
    const context = { ...helpers, ...imports, window: { _CONFIG: { webURL: 'http://synthetic.invalid' } } }
    vm.runInNewContext(parsed.script.content.replace(/^import .*$/gm, '').replace('export default', 'this.component ='), context)
    const compiled = compiler.compileToFunctions(parsed.template.content)
    return { ...context.component, render: compiled.render, staticRenderFns: compiled.staticRenderFns }
}
const Shared = component('components/teaching/StudentWorkFeedback.vue')
function harness (work) {
    let focusCount = 0
    const instance = new Vue({ ...Shared, components: { 'a-modal': stub }, propsData: { work: Vue.observable(work) } })
    instance.$refs.trigger = { isConnected: true, focus () { focusCount++ } }
    return { instance, get focusCount () { return focusCount } }
}
function nodes (vnode) {
    if (!vnode) return []
    const children = (vnode.children || []).concat(vnode.componentOptions ? vnode.componentOptions.children || [] : [])
    return [vnode, ...children.flatMap(nodes)]
}
const byClass = (tree, name) => nodes(tree).find(node => node.data && node.data.staticClass === name)
const text = vnode => nodes(vnode).map(node => node.text || '').join('')

test('zero is a score, missing and invalid values remain ungraded', () => {
    for (const score of [0, '0', ' 0 ', 5, '5']) assert.equal(feedback({ score }).score, Number(score))
    for (const score of [null, undefined, '', ' ', false, true, {}, [], '0x0', '0e0', '00', '0.0', '6', -1, 6, 2.5, NaN, Infinity]) {
        assert.equal(feedback({ score }).score, null, String(score))
        assert.equal(feedback({ score }).scoreLabel, '未评分')
    }
    assert.equal(feedback({ score: 0 }).scoreLabel, '0 / 5')
})
test('comment-only, scored-without-comment and no-feedback records remain distinct', () => {
    assert.equal(feedback({ teacherComment: '继续完善' }).scoreLabel, '未评分')
    assert.equal(feedback({ teacherComment: '继续完善' }).comment, '继续完善')
    assert.equal(feedback({ score: 4 }).scoreLabel, '4 / 5')
    for (const teacherComment of [null, undefined, '', ' \n\t ', {}, 0]) assert.equal(feedback({ teacherComment }).comment, '')
    assert.equal(feedback(null).workName, '未命名作品')
})
test('full comment keeps exact whitespace and literal HTML, summary truncates complete Unicode characters', () => {
    const comment = '  <script>fixture()</script>\n\n第二段\t '
    assert.equal(feedback({ teacherComment: comment }).comment, comment)
    const long = '🙂'.repeat(119) + '中尾'
    const result = feedback({ teacherComment: long })
    assert.equal(result.comment, long)
    assert.equal(result.summary, '🙂'.repeat(119) + '中…')
    assert.equal(Array.from(result.summary).length, 121)
})
test('feedback calculation and opening never mutate the API row', () => {
    const row = Object.freeze({ score: 0, teacherComment: '第一行\n第二行', workName: '作品 A' })
    const h = harness(row)
    h.instance.openFeedback()
    assert.equal(h.instance.visible, true)
    assert.equal(h.instance.detail.comment, row.teacherComment)
    assert.notEqual(h.instance.detail, row)
    assert.equal(h.instance.work.score, 0)
    h.instance.$destroy()
})
test('real template exposes visible score, native keyboard trigger and pure text detail', () => {
    const row = { score: 0, teacherComment: '<img src=x onerror=fixture()>\n下一行', workName: '作品 A' }
    const h = harness(row)
    let tree = h.instance._render()
    const trigger = nodes(tree).find(node => node.tag === 'button' && node.data.staticClass === 'feedback-open')
    assert.equal(trigger.data.attrs.type, 'button')
    assert.equal(trigger.data.attrs['aria-haspopup'], 'dialog')
    assert.match(trigger.data.attrs['aria-label'], /作品 A/)
    assert.match(text(tree), /0 \/ 5/)
    trigger.data.on.click()
    tree = h.instance._render()
    const full = byClass(tree, 'feedback-full-comment')
    assert.equal(text(full), row.teacherComment)
    assert.equal(full.data.domProps, undefined)
    assert.equal(nodes(full).filter(node => node.tag).length, 1)
    const region = byClass(tree, 'feedback-comment-region')
    assert.equal(region.data.attrs.tabindex, '0')
    assert.equal(region.data.attrs.role, 'region')
    h.instance.$destroy()
})
test('no-comment rows show empty text and do not create a misleading detail action', () => {
    const h = harness({ score: null, teacherComment: ' \n ' })
    const tree = h.instance._render()
    assert.match(text(tree), /未评分/)
    assert.equal(text(byClass(tree, 'feedback-empty')), '暂无评语')
    assert.equal(byClass(tree, 'feedback-open'), undefined)
    h.instance.openFeedback()
    assert.equal(h.instance.visible, false)
    h.instance.$destroy()
})
test('closing keeps detail until transition ends, then clears and returns focus once', () => {
    const h = harness({ teacherComment: '评语' })
    h.instance.openFeedback()
    h.instance.closeFeedback()
    assert.equal(h.instance.visible, false)
    assert.equal(h.instance.detail.comment, '评语')
    h.instance.afterFeedbackClose()
    assert.equal(h.instance.detail, null)
    assert.equal(h.focusCount, 1)
    h.instance.afterFeedbackClose()
    assert.equal(h.focusCount, 1)
    h.instance.$destroy()
})
test('late afterClose from an earlier close cannot erase a reopened detail or steal focus', () => {
    const h = harness({ teacherComment: '完整评语' })
    h.instance.openFeedback()
    h.instance.closeFeedback()
    h.instance.openFeedback()
    const reopened = h.instance.detail
    h.instance.afterFeedbackClose()
    assert.equal(h.instance.visible, true)
    assert.equal(h.instance.detail, reopened)
    assert.equal(h.focusCount, 0)
    h.instance.closeFeedback()
    h.instance.afterFeedbackClose()
    assert.equal(h.focusCount, 1)
    h.instance.$destroy()
})
test('changed row or refreshed feedback clears the old identity before reopening', async () => {
    const h = harness({ id: 'same', workName: '旧作品', teacherComment: '旧评语' })
    h.instance.openFeedback()
    h.instance.work = Vue.observable({ id: 'same', workName: '新作品', teacherComment: '新评语' })
    await Vue.nextTick()
    assert.equal(h.instance.visible, false)
    assert.equal(h.instance.detail, null)
    h.instance.afterFeedbackClose()
    assert.equal(h.focusCount, 0)
    h.instance.openFeedback()
    assert.equal(h.instance.detail.workName, '新作品')
    h.instance.work.teacherComment = '刷新后的评语'
    await Vue.nextTick()
    assert.equal(h.instance.visible, false)
    assert.equal(h.instance.detail, null)
    h.instance.$destroy()
})
test('destroyed component neither reopens nor restores focus to removed triggers', () => {
    const h = harness({ teacherComment: '评语' })
    h.instance.openFeedback()
    h.instance.$destroy()
    h.instance.afterFeedbackClose()
    h.instance.openFeedback()
    assert.equal(h.instance.visible, false)
    assert.equal(h.instance.detail, null)
    assert.equal(h.focusCount, 0)
    const removed = harness({ teacherComment: '评语' })
    removed.instance.openFeedback()
    removed.instance.$refs.trigger.isConnected = false
    removed.instance.closeFeedback()
    removed.instance.afterFeedbackClose()
    assert.equal(removed.focusCount, 0)
    removed.instance.$destroy()
})
test('separate rows keep independent detail and closing callbacks', () => {
    const first = harness({ teacherComment: '第一条' })
    const second = harness({ teacherComment: '第二条' })
    first.instance.openFeedback()
    first.instance.closeFeedback()
    second.instance.openFeedback()
    first.instance.afterFeedbackClose()
    assert.equal(second.instance.visible, true)
    assert.equal(second.instance.detail.comment, '第二条')
    assert.equal(second.focusCount, 0)
    first.instance.$destroy()
    second.instance.$destroy()
})
const listImports = { getAction: () => Promise.resolve({ success: true, result: [] }), deleteAction () {}, QrCode: stub, JeecgListMixin: { data () { return { queryParam: {}, selectedRowKeys: [], dataSource: [], ipagination: {}, loading: false, isorter: {}, filters: {} } }, methods: { onSelectChange () {}, handleTableChange () {}, searchQuery () {}, searchReset () {}, onClearSelected () {} } }, TeachingWorkPreviewModal: stub, JDictSelectTag: stub, StudentWorkFeedback: Shared }
const List = component('views/account/center/MineWorkList.vue', listImports)
const Cards = component('views/account/center/page/MineWorks.vue', { deleteAction () {}, getAction: listImports.getAction, getFileAccessHttpUrl: value => value, QrCode: stub, JEllipsis: stub, StudentWorkFeedback: Shared })

test('both actual parent templates pass their API row into the shared component', () => {
    const row = { id: 'fixture', score: 0, teacherComment: '评语', workType: '0' }
    const list = new Vue(List)
    const table = nodes(list._render()).find(node => node.tag === 'a-table')
    const slot = table.data.scopedSlots.scoreInfo(0, row)
    assert.equal(slot.componentOptions.Ctor.options.name, 'StudentWorkFeedback')
    assert.equal(slot.componentOptions.propsData.work, row)
    assert.equal(table.data.attrs.tabindex, '0')
    assert.equal(table.data.attrs.scroll.x, 1420)
    const cards = new Vue(Cards)
    cards.dataSource = [row]
    const cardFeedback = nodes(cards._render()).find(node => node.componentOptions && node.componentOptions.Ctor.options.name === 'StudentWorkFeedback')
    assert.equal(cardFeedback.componentOptions.propsData.work, row)
    list.$destroy()
    cards.$destroy()
})
test('keyboard table scrolling handles only its region, preserving child controls and other keys', () => {
    const list = new Vue(List)
    const body = { scrollLeft: 0 }
    list.$refs.table = { $el: { querySelector: () => body } }
    const region = {}; let prevented = 0
    const event = { target: region, currentTarget: region, key: 'ArrowRight', preventDefault () { prevented++ } }
    list.scrollTable(event)
    assert.equal(body.scrollLeft, 160)
    list.scrollTable({ ...event, key: 'ArrowLeft' })
    assert.equal(body.scrollLeft, 0)
    list.scrollTable({ ...event, target: {}, key: 'ArrowRight' })
    list.scrollTable({ ...event, key: 'Enter' })
    assert.equal(body.scrollLeft, 0)
    assert.equal(prevented, 2)
    list.$destroy()
})
