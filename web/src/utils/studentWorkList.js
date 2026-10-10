export function copyStudentWorkParams (params) {
    return JSON.parse(JSON.stringify(params))
}

export function studentWorkPage (response) {
    if (!response || response.success !== true) {
        const error = new Error('Work list unavailable')
        error.listKind = response && response.code === 510 ? 'access' : 'business'
        throw error
    }
    const page = response.result
    const total = page && page.total
    const validId = row => row && typeof row === 'object' && !Array.isArray(row) && ((typeof row.id === 'string' && row.id.trim()) || (typeof row.id === 'number' && Number.isSafeInteger(row.id)))
    if (!page || !Array.isArray(page.records) || page.records.some(row => !validId(row)) || typeof total !== 'number' || !Number.isSafeInteger(total) || total < 0) {
        const error = new Error('Work list malformed')
        error.listKind = 'data'
        throw error
    }
    return { records: page.records, total }
}

export function studentWorkListError (error) {
    if (error && error.listKind === 'data') return '作品列表返回的数据不完整，请稍后重试。'
    if (error && error.listKind === 'access') return '暂时无法读取作品，请确认当前账号的访问权限后重试。'
    if (error && error.listKind === 'business') return '作品列表暂时无法读取，请稍后重试。'
    if (error && error.code === 'ECONNABORTED') return '读取作品超时，请检查网络后重试。'
    const status = error && error.response && error.response.status
    if (status === 401) return '暂时无法读取作品，请重新登录或稍后重试。'
    if (status === 403) return '暂时无法读取作品，请确认当前账号的访问权限后重试。'
    if (status >= 500) return '作品服务暂时不可用，请稍后重试。'
    return '读取作品失败，请检查网络后重试。'
}
