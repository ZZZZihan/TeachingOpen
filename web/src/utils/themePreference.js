import { DEFAULT_COLOR, DEFAULT_COLOR_USER_CHOICE, DEFAULT_COLOR_LEGACY } from '@/store/mutation-types'

// Older releases saved their default during every startup, without recording
// whether it was selected by the user. Only that former default is migrated.
export function restoreThemeColor (storage, defaultColor) {
    const cached = storage.get(DEFAULT_COLOR)
    if (typeof cached !== 'string' || !cached.trim()) return defaultColor
    const explicitChoice = storage.get(DEFAULT_COLOR_USER_CHOICE)
    if (cached.trim().toLowerCase() === '#1890ff' && explicitChoice !== cached) {
        if (storage.get(DEFAULT_COLOR_LEGACY) == null) storage.set(DEFAULT_COLOR_LEGACY, cached)
        return defaultColor
    }
    return cached
}

export function sameThemeColor (left, right) {
    return typeof left === 'string' && typeof right === 'string' && left.toLowerCase() === right.toLowerCase()
}

export function themeColorOptions (colors, selected) {
    return selected && !colors.some(item => sameThemeColor(item.color, selected))
        ? colors.concat({ key: '自定义色', color: selected })
        : colors
}

export function themeColorLabel (colors, selected) {
    const item = colors.find(item => sameThemeColor(item.color, selected))
    return item ? item.key : '自定义色'
}
