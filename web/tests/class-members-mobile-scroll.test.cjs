const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const cp = require('node:child_process')
const vm = require('node:vm')
const babel = require('@babel/core')
const less = require('less')
const compiler = require('vue-template-compiler')
const { compileStyle } = require('@vue/component-compiler-utils')
const Vue = require('vue')
const postcss = require('postcss')
const selectorParser = require('postcss-selector-parser')
const cssSelect = require('css-select')
const { parseDOM } = require('htmlparser2')

const root = path.resolve(__dirname, '..')
const read = file => process.env.SOURCE_REF
  ? cp.execFileSync('git', ['show', `${process.env.SOURCE_REF}:web/${file}`], { cwd: root, encoding: 'utf8' })
  : fs.readFileSync(path.join(root, file), 'utf8')
const memberFile = 'src/views/system/modules/DeptUserInfo.vue'
const member = compiler.parseComponent(read(memberFile))
const shell = compiler.parseComponent(read('src/components/page/GlobalLayout.vue'))
const scoped = compileStyle({ source: member.styles[0].content, filename: memberFile, id: 'data-v-member-scroll-test', scoped: true })
assert.deepEqual(scoped.errors, [])
const styles = less.render(shell.styles[0].content, require('../vue.config').css.loaderOptions.less).then(result => ({ shell: result.css, member: scoped.code }))

// These are real compiled selectors, matched against Antd's nested table structure.
// The width calculation below is a bounded model using the observed 310/921px
// geometry, not a browser layout engine or authenticated UI acceptance.
function table({ mobile = true, owned = true } = {}) {
  const dom = parseDOM(`<div class="layout${mobile ? ' mobile' : ''}">
    <div class="${owned ? 'member-table-region' : 'unrelated-table-region'}" data-v-member-scroll-test>
      <div class="ant-table-wrapper"><div class="ant-spin-nested-loading"><div class="ant-spin-container">
        <div class="ant-table"><div class="ant-table-content"><div class="ant-table-scroll">
          <div class="ant-table-body"><table></table></div>
        </div></div></div>
      </div></div></div>
    </div>
  </div>`)
  return cssSelect.selectOne('.ant-table-body', dom)
}
function specificity(selector) {
  const score = [0, 0, 0]
  selectorParser(nodes => nodes.walk(node => {
    if (node.type === 'id') score[0]++
    if (['class', 'attribute', 'pseudo'].includes(node.type)) score[1]++
    if (node.type === 'tag') score[2]++
  })).process(selector)
  return score
}
function compare(a, b) {
  for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) return a[i] - b[i]
  return 0
}
function declaration(css, element, property) {
  let winner = null, order = 0
  postcss.parse(css).walkRules(rule => {
    const declarations = rule.nodes.filter(node => node.type === 'decl' && node.prop === property)
    if (!declarations.length) return
    for (const selector of rule.selectors) {
      if (!cssSelect.is(element, selector)) continue
      // Neither source currently conditions these width rules on media queries.
      assert.equal(rule.parent.type, 'root', 'width rule needs an explicit conditional cascade model')
      for (const node of declarations) {
        const priority = [Number(Boolean(node.important)), ...specificity(selector), order++]
        if (!winner || compare(priority, winner.priority) >= 0) winner = { value: node.value, selector, priority }
      }
    }
  })
  return winner
}
function bodyWidth(css, element, available) {
  const minimum = Number.parseFloat(declaration(css, element, 'min-width')?.value || '0')
  const maximum = declaration(css, element, 'max-width')?.value
  const limit = maximum === '100%' ? available : Infinity
  return Math.max(minimum, Math.min(available, limit))
}

// Compile the actual region opening tag, so Vue applies its real key aliases,
// .self and .prevent modifiers. No component lifecycle, service, or DOM is run.
const template = member.template.content.trim()
const parsed = compiler.compile(template, { outputSourceRange: true })
assert.deepEqual(parsed.errors, [])
function findRegion(node) {
  if (node.attrsMap?.role === 'region') return node
  return (node.children || []).map(findRegion).find(Boolean)
}
const region = findRegion(parsed.ast)
const openingTag = template.slice(region.start).match(/^<div[\s\S]*?>/)[0]
const render = compiler.compileToFunctions(`${openingTag}</div>`)
const renderVM = new Vue({ render: render.render, staticRenderFns: render.staticRenderFns })
const onKeydown = renderVM._render().data.on.keydown
function scrollingBody(width, content = 921) {
  let left = 0
  return { clientWidth: width, scrollWidth: content,
    get scrollLeft() { return left },
    set scrollLeft(value) { left = Math.max(0, Math.min(content - width, value)) }
  }
}
function key(body, code, fromChild = false) {
  let prevented = false
  const currentTarget = { querySelector(selector) { assert.equal(selector, '.ant-table-body'); return body } }
  const event = { type: 'keydown', keyCode: code, key: { 37: 'ArrowLeft', 39: 'ArrowRight', 40: 'ArrowDown' }[code],
    currentTarget, target: fromChild ? {} : currentTarget, preventDefault() { prevented = true } }
  for (const handler of [].concat(onKeydown)) handler(event)
  return prevented
}
const dataCode = babel.transformSync(member.script.content, { configFile: false, babelrc: false,
  plugins: [() => ({ visitor: { ImportDeclaration(p) { p.remove() }, ExportDefaultDeclaration(p) {
    p.replaceWith(babel.types.expressionStatement(babel.types.assignmentExpression('=', babel.types.identifier('component'), p.node.declaration)))
  } } })] }).code
const context = { component: null, JeecgListMixin: {}, SelectUserModal: {}, UserModal: {}, DeptRoleUserModal: {} }
vm.runInNewContext(dataCode, context)
const columns = context.component.data().columns
const selection = vm.runInNewContext(`(${region.children.find(node => node.tag === 'a-table').attrsMap[':rowSelection']})`,
  { selectedRowKeys: [], onSelectChange() {} })
const actionStart = selection.columnWidth + columns.filter(column => column.dataIndex !== 'action').reduce((sum, column) => sum + column.width, 0)
const actionEnd = actionStart + columns.find(column => column.dataIndex === 'action').width

test('real mobile shell retains its 800px minimum for unrelated tables', async () => {
  const css = await styles
  assert.equal(declaration(css.shell, table(), 'min-width').value, '800px')
  assert.equal(bodyWidth(css.shell + css.member, table({ owned: false }), 310), 800)
})
for (const order of ['shell-first', 'shell-last']) {
  test(`member scroll body overrides the real mobile shell in ${order} CSS order`, async () => {
    const css = await styles
    const combined = order === 'shell-first' ? css.shell + css.member : css.member + css.shell
    assert.equal(declaration(combined, table(), 'min-width').value, '0')
    assert.equal(bodyWidth(combined, table(), 310), 310)
  })
}
test('member body follows both narrow and wide desktop containers', async () => {
  const css = await styles
  for (const width of [310, 1000]) assert.equal(bodyWidth(css.shell + css.member, table({ mobile: false }), width), width)
  assert.equal(declaration(css.shell + css.member, table({ mobile: false, owned: false }), 'min-width'), null)
})
test('observed 310px region / 921px content reaches the entire action column with actual right-key handlers', async () => {
  const css = await styles
  const body = scrollingBody(bodyWidth(css.shell + css.member, table(), 310))
  for (let i = 0; i < 8; i++) assert.equal(key(body, 39), true)
  assert.equal(body.scrollLeft, 611)
  assert.ok(body.scrollLeft <= actionStart && body.scrollLeft + 310 >= actionEnd,
    `action ${actionStart}..${actionEnd} must fit the visible table interval`)
})
test('actual left-key handlers return from the action column to the first column', async () => {
  const css = await styles
  const body = scrollingBody(bodyWidth(css.shell + css.member, table(), 310))
  for (let i = 0; i < 8; i++) key(body, 39)
  for (let i = 0; i < 8; i++) assert.equal(key(body, 37), true)
  assert.equal(body.scrollLeft, 0)
})
test('region key modifiers leave focused children and other arrow keys alone', () => {
  const body = scrollingBody(310)
  assert.equal(key(body, 39, true), false)
  assert.equal(key(body, 40), false)
  assert.equal(body.scrollLeft, 0)
  assert.equal(key(body, 39), true)
  assert.equal(body.scrollLeft, 120)
})
