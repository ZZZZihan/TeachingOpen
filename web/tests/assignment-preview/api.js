import Axios from 'axios'
export const axios = config => Axios(config).then(response => response.data)
export const getAction = (url, params) => axios({ url, params, method: 'get' })
export const postAction = (url, data) => axios({ url, data, method: 'post' })
export const deleteAction = (url, params) => axios({ url, params, method: 'delete' })
