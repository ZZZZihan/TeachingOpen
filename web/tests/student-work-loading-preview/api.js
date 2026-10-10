import Axios from 'axios'
export const getAction = (url, params) => {
    const fixtureScenario = window.loadingScenario || 'success'
    return Axios({ url, params: { ...params, fixtureScenario }, method: 'get', timeout: fixtureScenario === 'timeout' ? 1200 : 15000 }).then(response => response.data)
}
export const postAction = () => Promise.resolve({ success: false, message: '合成只读预览不保存数据' })
export const deleteAction = () => Promise.resolve({ success: false, message: '合成只读预览不删除数据' })
export const downFile = () => Promise.resolve(null)
export const getFileAccessHttpUrl = value => value
