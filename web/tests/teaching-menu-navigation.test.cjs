const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { resolve } = require('node:path')
const { test } = require('node:test')
const vm = require('node:vm')
const scope = { URL }
vm.runInNewContext(readFileSync(resolve(__dirname, '../src/utils/teachingMenuUrl.js'), 'utf8').replace(/export function/g, 'function') + '\nthis.policy = { safeTeachingMenuUrl, teachingMenuLink }', scope)
const { safeTeachingMenuUrl, teachingMenuLink } = scope.policy
const rejected = ['javascript:void(0)', 'JaVaScRiPt:void(0)', ' java\nscript:void(0)', 'data:text/html,synthetic', 'vbscript:synthetic', '//example.invalid/', '/\\example.invalid/', 'https:\\example.invalid/', 'https://name:secret@example.invalid', 'http://example.invalid', '/%2fexample.invalid', '/%5Cexample.invalid', '/%0aevil', '/%', 'relative', 'https://', 'https://example.invalid:65536/', 'https://exa mple.invalid', {}, { toString: () => '/index' }]
for (const url of rejected) test('reject unsupported navigation ' + String(url), () => {
  assert.equal(safeTeachingMenuUrl(url), null)
  for (const route of [false, true]) for (const internalOrExternal of [false, true]) {
    const link = teachingMenuLink({ url, route, internalOrExternal })
    assert.equal(link.tag, 'span')
    assert.equal(link.attrs.href, undefined)
    assert.equal(link.props.to, undefined)
  }
})
for (const url of ['', '/', '/courseList', '/scratch3/index.html?scene=create', '/blockly/index.html?lang=zh#synthetic', '/课程?q=%E5%AD%A6', 'https://example.invalid:443/a?q=x#fragment']) test('preserve supported navigation ' + url, () => assert.equal(safeTeachingMenuUrl(url), url))
test('flags never turn HTTPS or blank grouping labels into router links', () => {
  assert.equal(teachingMenuLink({ url: '', route: true }).tag, 'span')
  assert.equal(teachingMenuLink({ url: '/index', route: true }).tag, 'router-link')
  assert.equal(teachingMenuLink({ url: '/scratch3/index.html', route: false }).tag, 'a')
  const link = teachingMenuLink({ url: 'https://example.invalid', route: true, internalOrExternal: true })
  assert.equal(link.tag, 'a'); assert.equal(link.attrs.target, '_blank'); assert.equal(link.attrs.rel, 'noopener noreferrer')
})
