import Vue from 'vue'
import axios from 'axios'
import store from '@/store'
import router from '@/router'
import { VueAxios } from './axios'
import { Modal, notification } from 'ant-design-vue'
import { ACCESS_TOKEN } from '@/store/mutation-types'
import { safeRedirect } from './session'

const service = axios.create({ baseURL: window._CONFIG['domianURL'] || '/api', timeout: 60000 })
let expirationNotice = null

const err = error => {
    const config = error.config || {}
    const response = error.response || {}
    const data = response.data || {}
    const expired = response.status === 401 || (response.status === 500 && data.message === 'Token失效，请重新登录')
    const token = Vue.ls.get(ACCESS_TOKEN)
    const sentToken = (config.headers || {})['X-Access-Token']
    if (!config.skipSession && expired) {
    // A late response from a previous account must not log out the current one.
        if (token && sentToken === token) {
            store.dispatch('ClearSession')
            if (!config.skipSessionNotice && !expirationNotice) {
                const redirect = safeRedirect(router.currentRoute.fullPath)
                expirationNotice = Modal.confirm({
                    title: '登录已过期',
                    content: '请先复制尚未保存的内容，再重新登录。当前页面会保留，未保存的修改不会自动恢复。',
                    okText: '重新登录',
                    cancelText: '留在本页',
                    maskClosable: false,
                    onOk: () => {
                        expirationNotice = null
                        return router.push({ path: '/user/login', query: { redirect, reason: 'expired' } })
                    },
                    onCancel: () => { expirationNotice = null }
                })
            }
        }
        return Promise.reject(error)
    }
    if (!config.localError && !config.skipSession) {
        const messages = { 403: '没有访问此内容的权限。', 404: '资源未找到。', 500: '服务暂时不可用，请稍后重试。', 502: '服务暂时不可用，请稍后重试。', 504: '连接超时，请稍后重试。' }
        notification.error({ message: '请求未完成', description: messages[response.status] || '无法完成请求，请检查网络后重试。', duration: 4 })
    }
    return Promise.reject(error)
}

service.interceptors.request.use(config => {
    const token = Vue.ls.get(ACCESS_TOKEN)
    config.headers = config.headers || {}
    if (token && !config.skipSession) config.headers['X-Access-Token'] = token
    if (token && expirationNotice) { expirationNotice.destroy(); expirationNotice = null }
    if (config.method === 'get' && config.url.indexOf('sys/dict/getDictItems') < 0) {
        config.params = { _t: Math.floor(Date.now() / 1000), ...config.params }
    }
    return config
}, error => Promise.reject(error))
service.interceptors.response.use(response => response.data, err)
const installer = { vm: {}, install (Vue, router = {}) { Vue.use(VueAxios, router, service) } }
export { installer as VueAxios, service as axios }
