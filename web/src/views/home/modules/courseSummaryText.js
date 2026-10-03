const namedEntities = {
    amp: '&',
    lt: '<',
    gt: '>',
    quot: '"',
    apos: "'",
    nbsp: ' ',
    ensp: ' ',
    emsp: ' ',
    thinsp: ' ',
    lsquo: '\u2018',
    rsquo: '\u2019',
    ldquo: '\u201c',
    rdquo: '\u201d',
    laquo: '\u00ab',
    raquo: '\u00bb',
    ndash: '\u2013',
    mdash: '\u2014',
    hellip: '\u2026',
    middot: '\u00b7',
    bull: '\u2022',
    copy: '\u00a9',
    reg: '\u00ae',
    trade: '\u2122',
    cent: '\u00a2',
    pound: '\u00a3',
    yen: '\u00a5',
    euro: '\u20ac',
    deg: '\u00b0',
    plusmn: '\u00b1',
    times: '\u00d7',
    divide: '\u00f7',
    le: '\u2264',
    ge: '\u2265',
    ne: '\u2260'
}

export function courseSummaryText (html) {
    const text = String(html == null ? '' : html)
        .replace(/<!--[\s\S]*?(?:-->|$)/g, ' ')
        .replace(/<(script|style)\b[^>]*>[\s\S]*?<\/\1\s*>/gi, ' ')
        .replace(/<[^>]*>/g, ' ')

    // Decode once, after removing source markup. Encoded markup remains literal
    // text, and &amp;lt; stays &lt; rather than being decoded a second time.
    return text.replace(/&(#(?:x[0-9a-f]+|[0-9]+)|[a-z][a-z0-9]+);/gi, (match, entity) => {
        const name = entity.toLowerCase()
        if (name[0] !== '#') return Object.prototype.hasOwnProperty.call(namedEntities, name) ? namedEntities[name] : match
        const hex = name[1] === 'x'
        const code = parseInt(name.slice(hex ? 2 : 1), hex ? 16 : 10)
        if (code === 0 || code > 0x10ffff || (code >= 0xd800 && code <= 0xdfff)) return match
        return String.fromCodePoint(code)
    }).replace(/\s+/g, ' ').trim()
}
