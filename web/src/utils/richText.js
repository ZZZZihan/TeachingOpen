import createDOMPurify from 'dompurify'

// This policy mirrors the news backend. No event, arbitrary data, SVG or iframe attributes.
const purifier = createDOMPurify(window)
const tags = 'p div span br strong b em i u s strike sub sup h1 h2 h3 h4 h5 h6 blockquote pre code ul ol li hr a img table thead tbody tfoot tr th td caption colgroup col video source'.split(' ')
const attributes = 'style title href target rel src alt width height poster controls preload type colspan rowspan colwidth scope span start class'.split(' ')

function safeStyle (style) {
    return String(style).split(';').map(declaration => {
        const split = declaration.indexOf(':')
        if (split < 0) return ''
        const name = declaration.slice(0, split).trim().toLowerCase()
        const value = declaration.slice(split + 1).trim().toLowerCase()
        const rules = {
            color: /^(#[0-9a-f]{3,8}|black|white|red|green|blue|yellow|gray|grey|orange|purple|pink|transparent|rgba?\([0-9.,% ]+\))$/,
            'text-align': /^(left|center|right|justify)$/,
            'font-weight': /^(normal|bold|[1-9]00)$/,
            'font-style': /^(normal|italic)$/,
            'text-decoration': /^(none|underline|line-through)$/,
            'vertical-align': /^(top|middle|bottom|baseline|sub|super)$/,
            'list-style-type': /^(disc|circle|square|decimal|lower-alpha|upper-alpha|lower-roman|upper-roman)$/
        }
        rules['background-color'] = rules.color
        for (const dimension of ['width', 'height', 'max-width', 'font-size', 'margin-left', 'padding-left']) {
            rules[dimension] = /^([0-9]+(?:\.[0-9]+)?(?:px|em|rem|%)|auto)$/
        }
        return rules[name] && rules[name].test(value) ? name + ':' + value + ';' : ''
    }).join('')
}

export function safeMediaUrl (value, image = false) {
    const url = String(value || '').trim()
    if (image && /^data:image\/(png|jpeg|gif|webp);base64,[a-z0-9+/=\r\n]+$/i.test(url)) return url
    if (!url || Array.from(url).some(character => character.charCodeAt(0) < 32 || character.charCodeAt(0) === 127)) return ''
    try {
        const parsed = new URL(url, window.location.href)
        return ['http:', 'https:'].includes(parsed.protocol) ? url : ''
    } catch (error) {
        return ''
    }
}

purifier.addHook('uponSanitizeAttribute', (node, data) => {
    if (data.attrName === 'style') {
        data.attrValue = safeStyle(data.attrValue)
        data.keepAttr = Boolean(data.attrValue)
    }
    if (data.attrName === 'class') data.keepAttr = node.nodeName === 'CODE' && /^language-[a-zA-Z0-9+#-]+$/.test(data.attrValue)
    if (['src', 'poster'].includes(data.attrName)) data.keepAttr = Boolean(safeMediaUrl(data.attrValue, node.nodeName === 'IMG' && data.attrName === 'src'))
    if (data.attrName === 'href') data.keepAttr = Boolean(safeMediaUrl(data.attrValue) || /^mailto:[^\s]+$/i.test(data.attrValue) || /^#[^\s]*$/.test(data.attrValue))
    if (data.attrName === 'target') data.keepAttr = data.attrValue === '_blank'
})
purifier.addHook('afterSanitizeAttributes', node => {
    if (node.nodeName === 'A' && node.getAttribute('target') === '_blank') node.setAttribute('rel', 'noopener noreferrer')
    if (node.nodeName === 'VIDEO') {
        node.setAttribute('controls', '')
        node.setAttribute('preload', 'metadata')
    }
})

export function sanitizeRichText (html) {
    return purifier.sanitize(String(html || ''), {
        ALLOWED_TAGS: tags,
        ALLOWED_ATTR: attributes,
        ALLOW_DATA_ATTR: false,
        ALLOW_ARIA_ATTR: false,
        SANITIZE_NAMED_PROPS: true
    })
}
