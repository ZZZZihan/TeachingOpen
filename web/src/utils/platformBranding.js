const DEFAULT_BRAND_NAME = 'TeachingOpen · 人工智能教学平台'

export function brandingValue (value) {
    return typeof value === 'string' ? value.trim() : ''
}

export function brandingFileUrl (config, value, resolveFileUrl) {
    const path = brandingValue(value)
    if (!path) return ''
    if (/^https?:\/\//i.test(path)) return path
    if (path.includes('[')) return ''
    const settings = config || {}
    const domain = brandingValue(settings.uploadType === 'qiniu' ? settings.qiniuDomain : settings.staticDomain)
    if (!domain) return ''
    try {
        const url = brandingValue(resolveFileUrl(path))
        return /^(?:undefined|null)\//.test(url) ? '' : url
    } catch (error) {
        return ''
    }
}

export function platformBrandName (config) {
    return brandingValue(config && config.brandName) || DEFAULT_BRAND_NAME
}

export function platformPageTitle (config, title) {
    const page = brandingValue(title)
    const brand = platformBrandName(config)
    return page ? `${page} · ${brand}` : brand
}
