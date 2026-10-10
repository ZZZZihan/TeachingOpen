import Vue from 'vue'
import router from './router'
import store from './store'
import NProgress from 'nprogress'
import 'nprogress/nprogress.css'
import { ACCESS_TOKEN } from '@/store/mutation-types'
import { generateIndexRouter } from '@/utils/util'
import { safeRedirect } from '@/utils/session'

NProgress.configure({ showSpinner: false })
const publicPaths = ['/', '/user/login', '/user/register', '/user/register-result', '/user/alteration', '/home', '/index', '/workList', '/courseList', '/friend-detail', '/work-detail', '/newsList', '/news-detail', '/404']
let permissionRequest = null
let permissionToken = null
function loadPermissions (token) {
    if (!permissionRequest || permissionToken !== token) {
        permissionToken = token
        const pending = store.dispatch('GetPermissionList').then(res => {
            if (Vue.ls.get(ACCESS_TOKEN) !== token) throw new Error('Session changed')
            const constRoutes = generateIndexRouter(res.result.menu)
            store.commit('SET_ROUTERS', constRoutes)
            router.addRoutes(constRoutes)
            store.commit('SET_PERMISSIONS_LOADED', true)
        }).finally(() => { if (permissionRequest === pending) permissionRequest = null })
        permissionRequest = pending
    }
    return permissionRequest
}

router.beforeEach(async (to, from, next) => {
    NProgress.start()
    const token = Vue.ls.get(ACCESS_TOKEN)
    if (to.path === '/user/login' && token) { next(safeRedirect(to.query.redirect)); return }
    if (publicPaths.includes(to.path)) { next(); return }
    if (!token) {
        next({ path: '/user/login', query: { redirect: safeRedirect(to.fullPath) }, replace: true })
        return
    }
    if (to.path === '/user/session') { next(); return }
    if (store.state.user.permissionsLoaded) { next(); return }
    try {
        await loadPermissions(token)
        if (Vue.ls.get(ACCESS_TOKEN) !== token) { next(false); NProgress.done(); return }
        next({ path: to.fullPath, replace: true })
    } catch (_) {
        if (!Vue.ls.get(ACCESS_TOKEN)) next({ path: '/user/login', query: { redirect: safeRedirect(to.fullPath), reason: 'expired' }, replace: true })
        else if (Vue.ls.get(ACCESS_TOKEN) !== token) { next(false); NProgress.done() } else next({ path: '/user/session', query: { redirect: safeRedirect(to.fullPath) }, replace: true })
    }
})
router.afterEach(() => NProgress.done())
router.onError(() => NProgress.done())
