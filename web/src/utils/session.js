/* eslint-disable no-control-regex */
// Control characters are rejected intentionally.
// Vue Router already decodes query values. Only accept a local absolute path.
export function safeRedirect (value, fallback = '/index') {
    if (typeof value !== 'string' || !/^\/(?!\/)/.test(value) || /[\\\u0000-\u0020]/.test(value)) return fallback
    let path
    try { path = decodeURIComponent(value.split(/[?#]/)[0]) } catch (_) { return fallback }
    if (/[\\\u0000-\u0020%]/.test(path) || path.startsWith('//') || path.split('/').some(part => part === '.' || part === '..') || /^\/user(?:\/|$)/i.test(path)) return fallback
    return value
}

export function loginErrorMessage (error) {
    const response = error && error.response
    if (response && response.status >= 500) return '服务暂时不可用，请稍后重试。'
    if (error && (error.code === 'ECONNABORTED' || error.code === 'ETIMEDOUT')) return '连接超时，请检查网络后重试。'
    if (error && (error.isAxiosError || error.request) && !response) return '无法连接服务，请检查网络后重试。'
    const message = (response && response.data && response.data.message) || (error && error.message)
    return typeof message === 'string' && message.length < 180 ? message : '登录未成功，请检查账号、密码和验证码后重试。'
}
