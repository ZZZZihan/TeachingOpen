// Memory only: no backend proxy, credentials or persistent identities.
import Vue from 'vue'
export const state = Vue.observable({ calls: [], slow: false, fail: false })
const users = ['a', 'b', 'new'].map(letter => ({ id: 'user-' + letter, username: 'sample_' + letter, realname: '合成学生 ' + letter.toUpperCase(), sex: 1, sex_dictText: '男', userIdentity: '1', orgCode: '合成班级', phone: '', roleNames: ['学生'], departNames: [] }))
let members = { 'class-a': ['user-a'], 'class-b': ['user-b'] }
const roles = [{ id: 'role-student', roleName: '学生', roleCode: 'student' }]
const clone = value => JSON.parse(JSON.stringify(value))
function call (method, url, data = {}) {
  state.calls.push({ method, url, data: clone(data) })
  let result, failure = state.fail
  if (!failure) {
    if (url.includes('departUserList')) { const rows = users.filter(row => (members[data.depId] || []).includes(row.id)); result = { records: clone(rows), total: rows.length } }
    else if (url === '/sys/user/list') { const rows = users.filter(row => !data.username || row.username.includes(data.username)); result = { records: clone(rows), total: rows.length } }
    else if (url.endsWith('/editSysDepartWithUser')) members[data.depId] = [...new Set([...(members[data.depId] || []), ...data.userIdList])]
    else if (url.includes('deleteUserInDepart')) members[data.depId] = (members[data.depId] || []).filter(id => !(data.userIds || data.userId || '').split(',').includes(id))
    else if (url.endsWith('/removeAll')) members[data.id] = []
    else if (url.includes('getDeptRoleByUserId')) result = []
    else if (url.includes('getDeptRoleList')) result = [{ id: 'dept-student', roleName: '合成班级学生' }]
    else if (url.includes('userDepart')) result = Object.keys(members).filter(id => members[id].includes(data.userId)).map(id => ({ key: id, title: id }))
    else if (url === 'queryMySubRole') result = clone(roles)
    else if (url === 'queryUserRole') result = ['role-student']
  }
  return new Promise(resolve => setTimeout(() => resolve({ success: !failure, message: failure ? '合成请求失败，请重试' : '合成操作完成', result }), state.slow ? 1800 : 50))
}
export const getAction = (url, data) => call('get', url, data)
export const postAction = (url, data) => call('post', url, data)
export const deleteAction = (url, data) => call('delete', url, data)
export const httpAction = (url, data, method) => call(method, url, data)
export const queryMySubRole = () => call('get', 'queryMySubRole')
export const queryUserRole = data => call('get', 'queryUserRole', data)
export const duplicateCheck = data => call('get', 'duplicateCheck', data)
export const addUser = data => call('post', 'addUser', data)
export const editUser = data => call('put', 'editUser', data)
export const disabledAuthFilter = () => false
export const initDictOptions = () => Promise.resolve({ success: true, result: [] })
export const downFile = () => Promise.reject(Error('Outside preview scope'))
export const getFileAccessHttpUrl = value => value
