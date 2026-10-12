import Axios from 'axios'

// The browser runner serves every endpoint on an ephemeral loopback listener.
export const getAction = (url, params) => Axios.get(url, { params }).then(response => response.data)
export const httpAction = (url, data, method) => Axios({ url, data, method }).then(response => response.data)
export const postAction = (url, data) => httpAction(url, data, 'post')
export const deleteAction = (url, params) => Axios.delete(url, { params }).then(response => response.data)

const dictionaries = {
    additional_work_status: [{ value: '0', text: '未发布' }, { value: '1', text: '进行中' }, { value: '2', text: '已结束' }],
    work_type: [{ value: '0', text: '文件作品' }, { value: '2', text: 'Scratch 作品' }]
}
export const getDictItemsFromCache = code => dictionaries[code]
export const ajaxGetDictItems = code => Promise.resolve({ success: true, result: dictionaries[code] || [] })
export const addDictItemsCache = () => { throw new Error('Dictionary mutation is outside this fixture') }
export const deleteDictItems = addDictItemsCache
export const deleteDictItemsCache = addDictItemsCache
export const queryMyDepartTreeList = () => getAction('/fixture/departments')
export const queryDepartTreeList = queryMyDepartTreeList
