export const registrationMessages = {
    closed: '平台暂未开放注册，请联系教师或管理员。',
    duplicate: '账号已注册，请直接登录，或更换账号。',
    invalid_username: '账号需为 4–32 位英文字母、数字或下划线。',
    invalid_realname: '请输入 100 字以内的姓名。',
    invalid_password: '密码需为 8–64 位，包含英文字母、数字和特殊符号。',
    registration_failed: '注册未完成，请稍后重试，或尝试登录确认账号状态。',
    invalid_defaults: '平台注册配置不可用，请联系管理员。',
    service_unavailable: '注册服务暂时不可用，请稍后重试。'
}

export function registrationError (response, fallback) {
    const state = response && response.result && response.result.registrationState
    return registrationMessages[state] || fallback
}

export function registrationProblems (values) {
    const errors = {}
    if (!/^[a-zA-Z0-9_]{4,32}$/.test(values.username)) errors.username = registrationMessages.invalid_username
    if (!values.realname.trim() || values.realname.length > 100 || values.realname.split('').some(c => c.charCodeAt(0) < 32 || (c.charCodeAt(0) >= 0xd800 && c.charCodeAt(0) <= 0xdfff))) errors.realname = registrationMessages.invalid_realname
    return errors
}
