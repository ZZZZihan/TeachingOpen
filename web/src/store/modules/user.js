import Vue from 'vue'
import { login, logout, phoneLogin, thirdLogin } from '@/api/login'
import { ACCESS_TOKEN, USER_NAME, USER_INFO, USER_ROLE, USER_AUTH, SYS_BUTTON_AUTH, UI_CACHE_DB_DICT_DATA, MENU } from '@/store/mutation-types'
import { welcome } from '@/utils/util'
import { axios } from '@/utils/request'
import { resetRouter } from '@/router'
import { getAction } from '@/api/manage'

const user = {
    state: {
        token: '',
        username: '',
        realname: '',
        welcome: '',
        avatar: '',
        permissionList: [],
        permissionsLoaded: false,
        sessionVersion: 0,
        menuList: [],
        info: {},
        userRole: [],
        sysConfig: {}
    },

    mutations: {
        CLEAR_SESSION: state => {
            state.token = ''
            state.username = ''
            state.realname = ''
            state.welcome = ''
            state.avatar = ''
            state.permissionList = []
            state.permissionsLoaded = false
            state.menuList = []
            state.info = {}
            state.userRole = []
            state.sessionVersion++
        },
        SET_PERMISSIONS_LOADED: (state, value) => { state.permissionsLoaded = value },
        SET_TOKEN: (state, token) => {
            state.token = token
        },
        SET_NAME: (state, { username, realname, welcome }) => {
            state.username = username
            state.realname = realname
            state.welcome = welcome
        },
        SET_AVATAR: (state, avatar) => {
            state.avatar = avatar
        },
        SET_PERMISSIONLIST: (state, permissionList) => {
            state.permissionList = permissionList
        },
        SET_MENU: (state, menuList) => {
            state.menuList = menuList
        },
        SET_INFO: (state, info) => {
            state.info = info
        },
        SET_USER_ROLE: (state, info) => {
            state.userRole = info
        },
        SET_SYS_CONFIG (state, configInfo) {
            state.sysConfig = configInfo
        }
    },

    actions: {
    // CAS验证登录
        ValidateLogin ({ commit }, userInfo) {
            return new Promise((resolve, reject) => {
                getAction('/cas/client/validateLogin', userInfo).then(response => {
                    if (response.success) {
                        const result = response.result
                        const userInfo = result.userInfo
                        Vue.ls.set(ACCESS_TOKEN, result.token, 7 * 24 * 60 * 60 * 1000)
                        Vue.ls.set(USER_NAME, userInfo.username, 7 * 24 * 60 * 60 * 1000)
                        Vue.ls.set(USER_INFO, userInfo, 7 * 24 * 60 * 60 * 1000)
                        commit('SET_TOKEN', result.token)
                        commit('SET_INFO', userInfo)
                        commit('SET_NAME', { username: userInfo.username, realname: userInfo.realname, welcome: welcome() })
                        commit('SET_AVATAR', userInfo.avatar)
                        resolve(response)
                    } else {
                        resolve(response)
                    }
                }).catch(error => {
                    reject(error)
                })
            })
        },
        // 登录
        Login ({ commit, dispatch, state }, userInfo) {
            dispatch('ClearSession')
            const version = state.sessionVersion
            return new Promise((resolve, reject) => {
                login(userInfo).then(response => {
                    if (version !== state.sessionVersion) throw new Error('登录已取消，请重试。')
                    if (String(response.code) === '200' && response.result && response.result.token && response.result.userInfo) {
                        const result = response.result
                        const userInfo = result.userInfo
                        const userRole = result.role
                        const expire = 7 * 24 * 60 * 60 * 1000
                        Vue.ls.set(ACCESS_TOKEN, result.token, expire)
                        Vue.ls.set(USER_NAME, userInfo.username, expire)
                        Vue.ls.set(USER_INFO, userInfo, expire)
                        Vue.ls.set(USER_ROLE, userRole, expire)
                        Vue.ls.set(UI_CACHE_DB_DICT_DATA, result.sysAllDictItems, expire)
                        commit('SET_TOKEN', result.token)
                        commit('SET_INFO', userInfo)
                        commit('SET_USER_ROLE', userRole)
                        commit('SET_NAME', { username: userInfo.username, realname: userInfo.realname, welcome: welcome() })
                        commit('SET_AVATAR', userInfo.avatar)
                        resolve(response)
                    } else {
                        reject(response)
                    }
                }).catch(error => {
                    reject(error)
                })
            })
        },
        // 手机号登录
        PhoneLogin ({ commit }, userInfo) {
            return new Promise((resolve, reject) => {
                phoneLogin(userInfo).then(response => {
                    if (String(response.code) === '200') {
                        const result = response.result
                        const userInfo = result.userInfo
                        Vue.ls.set(ACCESS_TOKEN, result.token, 7 * 24 * 60 * 60 * 1000)
                        Vue.ls.set(USER_NAME, userInfo.username, 7 * 24 * 60 * 60 * 1000)
                        Vue.ls.set(USER_INFO, userInfo, 7 * 24 * 60 * 60 * 1000)
                        Vue.ls.set(UI_CACHE_DB_DICT_DATA, result.sysAllDictItems, 7 * 24 * 60 * 60 * 1000)
                        commit('SET_TOKEN', result.token)
                        commit('SET_INFO', userInfo)
                        commit('SET_NAME', { username: userInfo.username, realname: userInfo.realname, welcome: welcome() })
                        commit('SET_AVATAR', userInfo.avatar)
                        resolve(response)
                    } else {
                        reject(response)
                    }
                }).catch(error => {
                    reject(error)
                })
            })
        },
        // Empty menus are valid; malformed responses and connection failures remain retryable.
        async GetPermissionList ({ commit, state }) {
            const token = Vue.ls.get(ACCESS_TOKEN)
            const version = state.sessionVersion
            const response = await axios({ url: '/sys/permission/getUserPermissionByToken',
                method: 'get',
                localError: true,
                skipSessionNotice: true,
                timeout: 15000 })
            if (version !== state.sessionVersion || token !== Vue.ls.get(ACCESS_TOKEN)) throw new Error('Session changed')
            const result = response && response.result
            if (!response.success || !result || !Array.isArray(result.menu) || !Array.isArray(result.auth) || !Array.isArray(result.allAuth)) {
                throw new Error('权限信息暂时不可用')
            }
            const menuData = result.menu
            menuData.forEach(item => {
                if (Array.isArray(item.children) && !item.children.some(child => !child.hidden)) item.hidden = true
            })
            sessionStorage.setItem(USER_AUTH, JSON.stringify(result.auth))
            sessionStorage.setItem(SYS_BUTTON_AUTH, JSON.stringify(result.allAuth))
            commit('SET_PERMISSIONLIST', menuData)
            return response
        },

        ClearSession ({ commit }) {
            commit('CLEAR_SESSION')
            for (const key of [ACCESS_TOKEN, UI_CACHE_DB_DICT_DATA, USER_NAME, USER_INFO, USER_ROLE, USER_AUTH, SYS_BUTTON_AUTH, MENU]) {
                Vue.ls.remove(key)
                sessionStorage.removeItem(key)
            }
            commit('SET_ROUTERS', [])
            resetRouter()
        },
        async Logout ({ dispatch, state }) {
            const token = state.token || Vue.ls.get(ACCESS_TOKEN)
            dispatch('ClearSession')
            if (token) {
                try { await logout(token) } catch (_) { /* Local sign-out must also work offline. */ }
            }
        },
        // 第三方登录
        ThirdLogin ({ commit }, token) {
            return new Promise((resolve, reject) => {
                thirdLogin(token).then(response => {
                    if (String(response.code) === '200') {
                        const result = response.result
                        const userInfo = result.userInfo
                        Vue.ls.set(ACCESS_TOKEN, result.token, 7 * 24 * 60 * 60 * 1000)
                        Vue.ls.set(USER_NAME, userInfo.username, 7 * 24 * 60 * 60 * 1000)
                        Vue.ls.set(USER_INFO, userInfo, 7 * 24 * 60 * 60 * 1000)
                        commit('SET_TOKEN', result.token)
                        commit('SET_INFO', userInfo)
                        commit('SET_NAME', { username: userInfo.username, realname: userInfo.realname, welcome: welcome() })
                        commit('SET_AVATAR', userInfo.avatar)
                        resolve(response)
                    } else {
                        reject(response)
                    }
                }).catch(error => {
                    reject(error)
                })
            })
        }
    }
}

export default user
