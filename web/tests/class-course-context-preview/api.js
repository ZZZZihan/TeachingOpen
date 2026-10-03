// In-memory transport fixture. Never proxies requests to a backend.
import Vue from 'vue'
export const state = Vue.observable({ calls: [], slow: false })
const courses = [{ id: 'course-a', courseName: '合成 A 课程' }, { id: 'course-b', courseName: '合成 B 课程' }, { id: 'course-new', courseName: '合成新增课程' }]
let rows = ['a', 'b'].map(letter => ({ id: 'relation-' + letter, deptId: 'class-' + letter, courseId: 'course-' + letter, courseName: '合成 ' + letter.toUpperCase() + ' 课程', openTime: '2026-10-03 09:00:00' }))
let serial = 0
const clone = value => JSON.parse(JSON.stringify(value))
function call(method, url, data = {}) {
  state.calls.push({ method, url, data: clone(data) })
  let result
  if (method === 'get') {
    let list = url.includes('teachingCourseDept') ? rows.filter(row => row.deptId === data.deptId) : courses
    if (data.courseName) list = list.filter(row => row.courseName.includes(data.courseName))
    result = { records: clone(list), total: list.length }
  } else if (method === 'delete') {
    const ids = (data.ids || data.id || '').split(',')
    rows = rows.filter(row => !ids.includes(row.id))
  } else if (url.endsWith('/addOrUpdate')) {
    for (const id of data.courseIdList) if (!rows.some(row => row.courseId === id && row.deptId === data.deptId)) rows.push({ ...courses.find(row => row.id === id), id: 'relation-new-' + (++serial), deptId: data.deptId, courseId: id, openTime: null })
  } else if (method === 'put') {
    rows = rows.map(row => row.id === data.id ? { ...row, ...data } : row)
  }
  return new Promise(resolve => setTimeout(() => resolve({ success: true, message: '合成操作完成', result }), state.slow ? 1800 : 50))
}
export const getAction = (url, params) => call('get', url, params)
export const postAction = (url, data) => call('post', url, data)
export const deleteAction = (url, params) => call('delete', url, params)
export const httpAction = (url, data, method) => call(method, url, data)
export const downFile = () => Promise.reject(Error('Not part of this controlled preview'))
export const getFileAccessHttpUrl = value => value
