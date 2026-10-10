export function isMainlandPhone (value) {
    return /^1[3-9]\d{9}$/.test(value)
}

export function passwordProblem (value) {
    if (!value) return '请输入新密码。'
    if (!/^[!-~]{8,64}$/.test(value) || !/[a-zA-Z]/.test(value) || !/\d/.test(value) || !/[~!@#$%^&*()_+`\-={}:";'<>?,./]/.test(value)) {
        return '密码需为 8–64 位，包含英文字母、数字和特殊符号，不含空格或中文。'
    }
    return ''
}

// Do not surface arbitrary transport messages: they can contain request details.
export function recoveryError (error, fallback) {
    if (error && (error.code === 'ECONNABORTED' || error.code === 'ETIMEDOUT')) return '连接超时，请检查网络后重试。'
    if (error && (error.isAxiosError || error.request) && !error.response) return '无法连接服务，请检查网络后重试。'
    if (error && error.response && error.response.status >= 500) return '服务暂时不可用，请稍后重试。'
    return fallback
}
