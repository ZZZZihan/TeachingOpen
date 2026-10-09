const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { resolve } = require('node:path')
const vm = require('node:vm')
const { test } = require('node:test')
const Vue = require('vue')
const Router = require('vue-router')
const compiler = require('vue-template-compiler')
Vue.use(Router)
const context = { URL }
vm.runInNewContext(readFileSync(resolve(__dirname, '../src/utils/registrationEntry.js'), 'utf8').replace(/^export /gm, ''), context)

test('registration URL preserves origin and actual router base', () => {
    for (const base of ['/', '/teaching/']) {
        const router = new Router({ mode: 'history', base, routes: [{ name: 'register', path: '/user/register' }] })
        assert.equal(context.registrationUrl(router, 'https://learn.example.edu'), `https://learn.example.edu${base}user/register`)
    }
})

test('PNG includes a four-module white quiet zone and retains QR pixels', () => {
    for (const size of [160, 320]) {
        const calls = []
        const drawing = { fillRect: (...args) => calls.push(['white', ...args]), drawImage: (...args) => calls.push(['qr', ...args]) }
        const canvas = { getContext: () => drawing }
        const source = { width: size, height: size }
        assert.equal(context.qrPngCanvas(source, { createElement: () => canvas }), canvas)
        const border = Math.ceil(size * 4 / 21)
        assert.equal(canvas.width, size + 2 * border)
        assert.equal(canvas.height, size + 2 * border)
        assert.equal(drawing.fillStyle, '#fff')
        assert.deepEqual(calls, [['white', 0, 0, canvas.width, canvas.height], ['qr', source, border, border]])
    }
    assert.throws(() => context.qrPngCanvas(null, {}), /not ready/)
})

test('registration component compiles', () => {
    const component = compiler.parseComponent(readFileSync(resolve(__dirname, '../src/views/home/modules/RegistrationEntry.vue'), 'utf8'))
    assert.deepEqual(compiler.compile(component.template.content).errors, [])
})
