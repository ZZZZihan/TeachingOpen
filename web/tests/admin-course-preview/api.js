import Axios from 'axios'
export const axios = config => Axios(config).then(response => response.data)
export const getAction = (url, params) => axios({ url, params, method: 'get' })
export const deleteAction = (url, params) => axios({ url, params, method: 'delete' })
export const downFile = (url, params) => Axios({ url, params, responseType: 'blob' }).then(response => response.data)
export const getFileAccessHttpUrl = value => value
