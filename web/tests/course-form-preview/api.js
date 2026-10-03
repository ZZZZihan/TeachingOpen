import Axios from 'axios'
export const getAction = (url, params) => Axios.get(url,{params}).then(r=>r.data)
export const httpAction = (url, data, method) => Axios({url,data,method}).then(r=>r.data)
