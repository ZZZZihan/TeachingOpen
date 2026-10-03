const assert = require('node:assert/strict')
const { test } = require('node:test')
const { caller, origin, player, readSource } = require('./python-preview-url/harness.cjs')
const flush = () => new Promise(resolve => setImmediate(resolve))

const files = [
  ['nested query and literal plus', 'https://files.test/seed.py?revision=1&label=a+b&next=/child?x=1&y=2'],
  ['space and Chinese', 'https://files.test/课程 示例.py?label=中文 空格'],
  ['percent escapes belong to the file', 'https://files.test/a%2Fb%26c%25.py?token=x%2Fy%26z%2526&literal=100%25'],
  ['hash belongs to the file', 'https://files.test/seed.py?revision=1#中文+ 空格%26'],
  ['relative file with query and percent escape', '/fixtures/a%2Fb.py?revision=1&label=a+b'],
  ['relative file without initial slash', 'fixtures/seed.py?revision=1&label=a+b']
]

test('both HTML entry points load the real query helper before both prebuilt Python bundles', () => {
  for (const page of ['index', 'player']) {
    const html = readSource('web/public/python/' + page + '.html')
    const scripts = [...html.matchAll(/<script\b[^>]*\bsrc=(?:"([^"]+)"|'([^']+)'|([^\s>]+))/g)].map(match => match[1] || match[2] || match[3])
    assert.equal(scripts.filter(value => value === './persistence.js').length, 1, page + ' includes one shared query helper')
    for (const bundle of ['appPlayer', 'app']) {
      assert.ok(scripts.indexOf('./persistence.js') < scripts.indexOf('./static/js/' + bundle + '.js'), page + ' loads the helper before ' + bundle)
    }
  }
})

test('all three actual callers mark modern Python links for one standard outer decode', () => {
  for (const name of ['teacher', 'course', 'community']) {
    const href = caller(name).link('/fixtures/seed.py?label=a+b&revision=1')
    assert.equal(new URL(href, origin).searchParams.get('queryEncoding'), 'uri', name + ' opts into the standard outer query encoding')
  }
})

for (const name of ['teacher', 'course', 'community']) {
  for (const [label, file] of files) {
    test(name + ' actual caller reaches both actual Python component downloads: ' + label, async () => {
      const href = caller(name).link(file)
      const expected = name === 'community' ? file : new URL(file, origin).href
      assert.ok(href.startsWith('/python/player.html?'), 'actual caller produces a Python player link')
      for (const bundle of ['appPlayer', 'app']) {
        const h = player(bundle, href)
        assert.equal(h.instance.urlParam('url'), expected, bundle + ' decodes the entire outer query value once')
        h.start(); await flush()
        assert.deepEqual(h.requested, [expected], bundle + ' requests precisely the caller file')
        assert.equal(h.instance.code, 'print("URL fixture loaded")\n')
        assert.deepEqual(h.applied, ['print("URL fixture loaded")\n'], bundle + ' applies the downloaded bytes to Ace')
      }
    })
  }
}

for (const bundle of ['appPlayer', 'app']) {
  test(bundle + ' encoded url retains nested delimiters, percent escapes, literal plus and Unicode in one decode', () => {
    const file = '/fixtures/空 格%2F%26%25.py?a=x+y&b=中文 空格&c=100%&d=#片段+ %26'
    const href = '/python/player.html?' + new URLSearchParams({ queryEncoding: 'uri', lang: 'turtle', url: file })
    const h = player(bundle, href)
    assert.equal(h.instance.urlParam('url'), file)
  })

  test(bundle + ' first duplicate URL wins without reparsing embedded URL parameters', async () => {
    const first = '/fixtures/first.py?url=/nested.py&lang=inner', second = '/fixtures/second.py'
    const params = new URLSearchParams({ queryEncoding: 'uri', lang: 'turtle', url: first }); params.append('url', second)
    const h = player(bundle, '/python/player.html?' + params)
    assert.equal(h.instance.urlParam('url'), first)
    h.start(); await flush(); assert.deepEqual(h.requested, [first])
  })

  test(bundle + ' missing and empty URL keep the original lifecycle fallback and do not use fragment-only parameters', async () => {
    for (const href of ['/python/player.html', '/python/player.html?lang=turtle', '/python/player.html?url=', '/python/player.html?url=&url=/ignored.py', '/python/player.html#?url=/fragment.py']) {
      const h = player(bundle, href)
      assert.equal(h.instance.urlParam('url'), 0, 'missing or empty first value has the established sentinel')
      h.start(); await flush()
      assert.deepEqual(h.requested, bundle === 'appPlayer' ? [] : ['./static/defaultPython.py'])
    }
  })

  test(bundle + ' ordinary raw relative links remain usable and malformed percent encoding does not throw', async () => {
    for (const [href, expected] of [
      ['/python/player.html?url=/fixtures/seed.py', '/fixtures/seed.py'],
      ['/python/player.html?url=fixtures/seed.py', 'fixtures/seed.py'],
      ['/python/player.html?url=%', '%'],
      ['/python/player.html?url=%2', '%2'],
      ['/python/player.html?url=/fixtures/100%.py', '/fixtures/100%.py']
    ]) {
      const h = player(bundle, href)
      assert.doesNotThrow(() => h.instance.urlParam('url'))
      assert.equal(h.instance.urlParam('url'), expected)
      h.start(); await flush(); assert.deepEqual(h.requested, [expected])
    }
  })

  test(bundle + ' legacy raw addresses preserve their own percent escapes and literal plus', async () => {
    for (const file of [
      'https://files.test/a%2Fb%26c+100%25.py?label=a+b',
      'http://files.test/a%2Fb%26c+100%25.py?label=a+b',
      '/fixtures/a%2Fb%26c+100%25.py?label=a+b',
      './fixtures/a%2Fb%26c+100%25.py?label=a+b',
      '../fixtures/a%2Fb%26c+100%25.py?label=a+b',
      'fixtures/a%2Fb%26c+100%25.py?label=a+b'
    ]) {
      const h = player(bundle, '/python/player.html?lang=turtle&url=' + file)
      assert.equal(h.instance.urlParam('url'), file)
      h.start(); await flush(); assert.deepEqual(h.requested, [file])
    }
  })

  test(bundle + ' legacy whole-value encoded recognized addresses decode once', async () => {
    for (const file of [
      'https://files.test/a%2Fb%26c+100%25.py?label=a+b&revision=1',
      '/fixtures/a%2Fb%26c+100%25.py?label=a+b&revision=1',
      './fixtures/a%2Fb%26c+100%25.py?label=a+b&revision=1',
      '../fixtures/a%2Fb%26c+100%25.py?label=a+b&revision=1'
    ]) {
      const h = player(bundle, '/python/player.html?url=' + encodeURIComponent(file))
      assert.equal(h.instance.urlParam('url'), file)
      h.start(); await flush(); assert.deepEqual(h.requested, [file])
    }
  })
}

test('the shared parser keeps editor workFile escapes while preserving the existing name and ID query behavior', () => {
  const file = '../fixtures/a%2Fb%26c+100%25.py?label=a+b'
  const legacy = player('app', '/python/index.html?workFile=' + file + '&workId=work%26one&workName=100%25+中文')
  assert.equal(legacy.instance.urlParam('workFile'), file)
  assert.equal(legacy.instance.urlParam('workId'), 'work&one')
  assert.equal(legacy.instance.urlParam('workName'), '100%+中文')
  const standard = player('app', '/python/index.html?' + new URLSearchParams({ queryEncoding: 'uri', workFile: file, workId: 'work&one', workName: '100% + 中文' }))
  assert.equal(standard.instance.urlParam('workFile'), file)
  assert.equal(standard.instance.urlParam('workId'), 'work&one')
  assert.equal(standard.instance.urlParam('workName'), '100% + 中文')
})
