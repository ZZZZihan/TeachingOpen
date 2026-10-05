const DEFAULT_BRAND_NAME = '天津工业大学 · 人工智能教学平台'

export function brandingValue (value) {
    return typeof value === 'string' ? value.trim() : ''
}

export function platformBrandName (config) {
    return brandingValue(config && config.brandName) || DEFAULT_BRAND_NAME
}

export function platformPageTitle (config, title) {
    const page = brandingValue(title)
    const brand = platformBrandName(config)
    return page ? `${page} · ${brand}` : brand
}
