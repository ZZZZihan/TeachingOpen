const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { resolve } = require('node:path')
const { test } = require('node:test')
const vm = require('node:vm')
const { createHash } = require('node:crypto')
const Vue = require('vue')
const compiler = require('vue-template-compiler')
const catalogue = require('../../examples/showcase/catalog.json')
const source = file => readFileSync(resolve(__dirname, '../src', file), 'utf8')

test('公开清单的五个版本与实际程序和封面一致', () => {
  assert.equal(catalogue.length, 5)
  assert.equal(new Set(catalogue.map(item => item.id)).size, 5)
  for (const item of catalogue) {
    for (const kind of ['program', 'cover']) {
      const bytes = readFileSync(resolve(__dirname, '../..', item[kind + 'Path']))
      assert.equal(createHash('sha256').update(bytes).digest('hex'), item[kind + 'Sha256'])
    }
    assert.ok(item.filePrefix.endsWith('/' + item.programSha256 + '/'))
  }
})

test('所有作品卡片仅显示一张真实封面，缺失封面时才使用代码图', () => {
  for (const file of ['Home.vue', 'WorkList.vue', 'FriendDetail.vue']) {
    const text = compiler.parseComponent(source('views/home/' + file)).template.content
    const pairs = text.match(/<img[^>]*v-if="item\.coverFileKey_url"[^>]*\/>\s*<img[^>]*src="@\/assets\/code.png"[^>]*\/>/g)
    assert.equal(pairs.length, file === 'Home.vue' ? 2 : 1)
    for (const pair of pairs) {
      const render = compiler.compileToFunctions('<div>' + pair + '</div>')
      for (const type of ['2', '4', '10']) {
        for (const cover of ['', '/actual-cover.png']) {
          const component = new Vue({ ...render, data: () => ({ item: { workName: '示例', workType: type, coverFileKey_url: cover } }) })
          const images = component._render().children.filter(v => v.tag === 'img')
          assert.equal(images.length, cover || type !== '2' ? 1 : 0)
          if (images.length) assert.equal(images[0].data.attrs.src, cover || '@/assets/code.png')
        }
      }
    }
  }
})

test('来源只属于已登记版本，重存、其他作品或异常路径不继承原作者', () => {
  const context = { catalogue }
  vm.runInNewContext(source('utils/showcaseAttribution.js').replace(/^import .*$/m, '').replace('export function', 'function') + '\nthis.get = getShowcaseAttribution', context)
  for (const item of catalogue) {
    const basename = 'a'.repeat(32) + (item.workType === '2' ? '.sb3' : '.py')
    const work = { id: item.id, workType: item.workType, workFileKey: item.filePrefix + basename }
    assert.equal(context.get(work).author, item.author)
    assert.equal(context.get({ ...work, workType: Number(item.workType) }).sourceUrl, item.sourceUrl)
    for (const override of [
      { id: 'other-work', workName: item.title }, { workType: '10' }, { workFileKey: '' },
      { workFileKey: 'upload/' + basename }, { workFileKey: item.filePrefix + '../' + basename },
      { workFileKey: item.filePrefix + 'extra/' + basename }, { workFileKey: item.filePrefix.slice(0, -1) + '-other/' + basename }
    ]) assert.equal(context.get({ ...work, ...override }), null)
  }
  assert.equal(context.get(null), null)
  assert.equal(context.get({}), null)
})
