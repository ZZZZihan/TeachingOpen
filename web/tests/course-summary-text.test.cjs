const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { resolve } = require('node:path')
const { test } = require('node:test')
const vm = require('node:vm')
const Vue = require('vue')
const compiler = require('vue-template-compiler')
const less = require('less')
const postcss = require('postcss')
const autoprefixer = require('autoprefixer')

const cardSource = readFileSync(resolve(__dirname, '../src/views/home/modules/CourseCard.vue'), 'utf8')
const helperSource = readFileSync(resolve(__dirname, '../src/views/home/modules/courseSummaryText.js'), 'utf8')
const context = {}
vm.runInNewContext(helperSource.replace(/^export /gm, ''), context)
const summary = context.courseSummaryText

test('摘要解码常用命名实体及十进制、十六进制 Unicode 实体', () => {
  assert.equal(summary('<p>&ldquo;课程&rdquo;&nbsp;&mdash; 示例&hellip;</p><p>&copy; &#34;引号&#x22; &#x1F680;</p>'), '“课程” — 示例… © "引号" 🚀')
  assert.equal(summary('&lsquo;文字&rsquo; &lt; 3 &gt; 1 &amp; &apos; &yen; &times; &#20013;&#25991;'), '‘文字’ < 3 > 1 & \' ¥ × 中文')
})

test('实体只解码一次，保留双重转义的文本语义', () => {
  assert.equal(summary('&amp;lt; &amp;gt; &#38;lt; &amp;#x1F680;'), '&lt; &gt; &lt; &#x1F680;')
})

test('未知或非法实体不丢失文本，也不会因非法码点报错', () => {
  const literal = '&unknown; &constructor; &#0; &#xD800; &#1114112; &#x110000; &#xZZ; &amp'
  assert.equal(summary(literal), literal)
  assert.equal(summary(null), '')
  assert.equal(summary(undefined), '')
  assert.equal(summary('   <p>&nbsp;</p>  '), '')
})

test('原始 HTML、注释及脚本样式仅转为摘要文本，不使用 DOM 解析', () => {
  assert.equal(summary('<style>body{display:none}</style><p>第一段<img src="/never-request" onerror="alert(1)"></p><!-- hidden --><script>alert(1)</script><div>第二段<br>末句</div>'), '第一段 第二段 末句')
})

test('实际 CourseCard 模板把解码后的标签作为文本，并保留原课程介绍事件和对象', () => {
  const componentContext = { courseSummaryText: summary }
  const script = cardSource.match(/<script>([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm, '').replace('export default', 'this.component =')
  vm.runInNewContext(script, componentContext)
  const compiled = compiler.compile(cardSource.match(/<template>([\s\S]*?)<\/template>/)[1])
  assert.deepEqual(compiled.errors, [])
  const course = { id: 'synthetic-course', courseName: '自造课程', courseDesc: '&lt;img src="/never-request" onerror="alert(1)"&gt;&lt;script&gt;alert(1)&lt;/script&gt;' }
  const instance = new Vue({ ...componentContext.component, propsData: { course }, render: new Function(compiled.render), staticRenderFns: compiled.staticRenderFns.map(code => new Function(code)) })
  const tree = instance._render()
  const descendants = []
  const walk = node => { descendants.push(node); (node.children || []).forEach(walk) }
  walk(tree)
  const summaryNode = descendants.find(node => node.data && node.data.staticClass === 'course-summary')
  assert.equal(summaryNode.children[0].text, '<img src="/never-request" onerror="alert(1)"><script>alert(1)</script>')
  assert.equal(descendants.some(node => ['img', 'script', 'style'].includes(node.tag)), false)
  assert.equal(descendants.some(node => node.data && node.data.domProps && node.data.domProps.innerHTML), false)
  let opened
  instance.$on('open', value => { opened = value })
  tree.data.on.click()
  assert.equal(opened, course)
  assert.equal(opened.courseDesc, course.courseDesc)
  instance.$destroy()
})

test('实际 Less 与项目 Autoprefixer 处理后仍保留三行截断所需的方向声明', async () => {
  const source = cardSource.match(/<style[^>]*>([\s\S]*?)<\/style>/)[1]
  const css = (await less.render(source)).css
  const output = await postcss([autoprefixer()]).process(css, { from: undefined })
  const declarations = {}
  output.root.walkRules('.course-summary', rule => rule.walkDecls(decl => { declarations[decl.prop] = decl.value }))
  assert.equal(declarations.display, '-webkit-box')
  assert.equal(declarations['-webkit-line-clamp'], '3')
  assert.equal(declarations['-webkit-box-orient'], 'vertical')
  assert.equal(declarations.overflow, 'hidden')
  assert.equal(declarations['max-height'], '5.7em')
})
