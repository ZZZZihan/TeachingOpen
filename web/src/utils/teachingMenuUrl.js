// Navigation has a narrower policy than images or rich text. Recheck persisted menus at the sink.
// Empty URLs are non-link grouping labels; null means an unsupported or malformed destination.
export function safeTeachingMenuUrl (input) {
  if (input == null) return ''
  if (typeof input !== 'string' || input.length > 255 || /[\u0000-\u001f\u007f\\]/.test(input)) return null
  const value = input.trim()
  if (!value) return ''
  if (/\s|%(?:0[0-9a-f]|1[0-9a-f]|7f|5c)/i.test(value) || /%(?![0-9a-f]{2})/i.test(value)) return null
  if (value.startsWith('/') && !value.startsWith('//')) {
    // A decoded slash or backslash must not turn a site path into an authority.
    const path = value.split(/[?#]/)[0].replace(/%2f/ig, '/').replace(/%5c/ig, '\\')
    return path.startsWith('//') || path.includes('\\') ? null : value
  }
  if (!/^https:\/\//i.test(value)) return null
  try {
    const parsed = new URL(value)
    return parsed.protocol === 'https:' && parsed.hostname && !parsed.username && !parsed.password ? value : null
  } catch (_) {
    return null
  }
}

export function teachingMenuLink (menu) {
  const url = safeTeachingMenuUrl(menu.url)
  if (!url) return { tag: 'span', props: {}, attrs: {} }
  if (url.startsWith('/') && menu.route && !menu.internalOrExternal) {
    return { tag: 'router-link', props: { to: { path: url } }, attrs: {} }
  }
  return { tag: 'a', props: {}, attrs: { href: url, target: menu.internalOrExternal ? '_blank' : '_self', rel: 'noopener noreferrer' } }
}
