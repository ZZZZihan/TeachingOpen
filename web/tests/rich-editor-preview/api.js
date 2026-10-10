import axios from 'axios'
window.newsAxiosVersion = axios.VERSION
function request(method, url, data) {
    return axios({ method, url: url.startsWith('/api') || /^https?:/.test(url) ? url : '/api' + url, data }).then(response => response.data)
}
export function getAction(url, parameters) { return request('GET', url + (parameters && Object.keys(parameters).length ? '?' + new URLSearchParams(parameters) : '')) }
export function postAction(url, data) { return request('POST', url, data) }
export function httpAction(url, data, method) { return request(method.toUpperCase(), url, data) }
export function uploadAction(url, data) { if (window.newsQiniuResponse && /^https:\/\/upload-/.test(url)) { window.newsQiniuRequest = { url, key: data.get('key'), token: data.get('token') }; return Promise.resolve(window.newsQiniuResponse) }; if (window.newsUploadFailure) return Promise.reject(Error('合成网络故障')); return request('POST', url, data) }
export function getFileAccessHttpUrl(key) { return key.startsWith('http') || key.startsWith('/') ? key : '/api/sys/common/static/' + key }
