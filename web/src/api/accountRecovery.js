import { axios } from '@/utils/request'

// Recovery is public: keep errors on its form and do not attach a stale session.
function request (url, method, values) {
    return axios({ url,
        method,
        ...(method === 'get' ? { params: values } : { data: values }),
        localError: true,
        skipSession: true,
        timeout: 15000 })
}

export const getRecoveryCaptcha = key => request(`/sys/randomImage/${key}`, 'get')
export const checkRecoveryCaptcha = values => request('/sys/checkCaptcha', 'post', values)
export const queryRecoveryAccount = values => request('/sys/user/querySysUser', 'get', values)
export const sendRecoverySms = values => request('/sys/sms', 'post', values)
export const verifyRecoveryPhone = values => request('/sys/user/phoneVerification', 'post', values)
export const changeRecoveryPassword = values => request('/sys/user/passwordChange', 'post', values)
