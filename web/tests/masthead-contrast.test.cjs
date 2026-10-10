const assert = require('node:assert/strict')
const { readFileSync } = require('node:fs')
const { resolve } = require('node:path')
const { test } = require('node:test')
const compiler = require('vue-template-compiler')

const source = readFileSync(resolve(__dirname, '../src/components/brand/CampusMasthead.vue'), 'utf8')
const styles = compiler.parseComponent(source).styles.map(style => style.content).join('\n')

function declaration (selector, property) {
    // Read the component's real CSS, so changing either color exercises this check.
    const rules = [...styles.matchAll(/([^{}]+)\{([^{}]*)\}/g)]
    const rule = rules.find(match => match[1].trim() === selector &&
        new RegExp('(?:^|;)\\s*' + property + '\\s*:').test(match[2]))
    assert.ok(rule, `${selector} must declare ${property}`)
    const value = rule[2].match(new RegExp('(?:^|;)\\s*' + property + '\\s*:\\s*([^;]+)'))
    return value[1].trim()
}

function luminance (color) {
    assert.match(color, /^#(?:[\da-f]{3}|[\da-f]{6})$/i, 'Expected an opaque sRGB CSS color')
    const hex = color.length === 4 ? color.slice(1).split('').map(value => value + value).join('') : color.slice(1)
    const channels = hex.match(/../g).map(value => parseInt(value, 16) / 255)
        .map(value => value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4)
    return channels.reduce((result, value, index) => result + value * [0.2126, 0.7152, 0.0722][index], 0)
}

test('顶部标语小字与真实蓝色背景达到 WCAG AA 普通文字对比度', t => {
    const foreground = declaration('.university-motto span', 'color')
    const background = declaration('.campus-masthead', 'background')
    const light = Math.max(luminance(foreground), luminance(background))
    const dark = Math.min(luminance(foreground), luminance(background))
    const ratio = (light + 0.05) / (dark + 0.05)
    t.diagnostic(`${foreground} on ${background}: ${ratio.toFixed(6)}:1`)
    // The current 10px subtitle uses the normal-text threshold, without rounding up.
    assert.ok(ratio >= 4.5, `${foreground} on ${background}: ${ratio.toFixed(6)}:1 is below 4.5:1`)
})
