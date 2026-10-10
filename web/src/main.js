import Vue from 'vue'
import App from './App.vue'
import Storage from 'vue-ls'
import router from './router'
import store from './store/'

import { VueAxios } from '@/utils/request'

import Antd from 'ant-design-vue'
import 'ant-design-vue/dist/antd.less' // or 'ant-design-vue/dist/antd.less'

import '@/permission' // permission control
import '@/utils/filter' // base filter
import Print from 'vue-print-nb-jeecg'
/* import '@babel/polyfill' */
import preview from 'vue-photo-preview'
import 'vue-photo-preview/dist/skin.css'

// swiper
import VueAwesomeSwiper from 'vue-awesome-swiper'
// import "swiper/css/swiper.css";
import 'swiper/dist/css/swiper.css'

import {
    ACCESS_TOKEN,
    DEFAULT_COLOR,
    DEFAULT_THEME,
    DEFAULT_LAYOUT_MODE,
    DEFAULT_COLOR_WEAK,
    SIDEBAR_TYPE,
    DEFAULT_FIXED_HEADER,
    DEFAULT_FIXED_HEADER_HIDDEN,
    DEFAULT_FIXED_SIDEMENU,
    DEFAULT_CONTENT_WIDTH_TYPE,
    DEFAULT_MULTI_PAGE,
    SYS_CONFIG,
    MENU
} from '@/store/mutation-types'
import config from '@/defaultSettings'

import JDictSelectTag from './components/dict/index.js'
import hasPermission from '@/utils/hasPermission'
import vueBus from '@/utils/vueBus'
import JeecgComponents from '@/components/jeecg/index'
import '@/assets/less/JAreaLinkage.less'
import VueAreaLinkage from 'vue-area-linkage'
import { getSysConfig, getMenu } from '@/api/manage'
import { loadStartupData, showStartupError } from '@/utils/startup'
import { platformBrandName } from '@/utils/platformBranding'
// 颜色选择器
import vcolorpicker from 'vcolorpicker'

Vue.config.productionTip = false
Vue.use(Storage, config.storageOptions)
Vue.use(Antd)
Vue.use(VueAxios, router)
Vue.use(hasPermission)
Vue.use(JDictSelectTag)
Vue.use(Print)
Vue.use(preview)
Vue.use(vueBus)
Vue.use(JeecgComponents)
Vue.use(VueAreaLinkage)
Vue.use(VueAwesomeSwiper /* { default options with global component } */)
Vue.use(vcolorpicker)

let cacheTime = 1800000 // 缓存时间

let starting = false
let started = false

const start = async () => {
    if (starting || started) return
    starting = true
    const retryButton = window.document.getElementById('startup-retry')
    if (retryButton) {
        retryButton.disabled = true
        retryButton.textContent = '正在加载……'
    }
    let sysConfig
    try {
        const data = await loadStartupData({
            cachedConfig: store.getters.sysConfig,
            cachedMenu: store.getters.menuList,
            getConfig: getSysConfig,
            getMenu,
            saveConfig: value => {
                Vue.ls.set(SYS_CONFIG, value, cacheTime)
                store.commit('SET_SYS_CONFIG', value)
            },
            saveMenu: value => {
                Vue.ls.set(MENU, value, cacheTime)
                store.commit('SET_MENU', value)
            },
            clearMenu: () => {
                Vue.ls.remove(MENU)
                store.commit('SET_MENU', [])
            }
        })
        if (!data.isCurrent()) throw new Error('Startup access revoked')
        sysConfig = data.sysConfig
    } catch (error) {
        starting = false
        showStartupError(start, window.document)
        return
    }
    started = true
    starting = false
    new Vue({
        router,
        store,
        created () {
            window.document.title = platformBrandName(sysConfig)
            if (sysConfig.customJS) {
                let script = document.createElement('script')
                script.type = 'text/javascript'
                script.textContent = sysConfig.customJS
                document.head.appendChild(script)
            }
            if (sysConfig.customCss) {
                let style = document.createElement('style')
                style.type = 'text/css'
                style.textContent = sysConfig.customCss
                document.head.appendChild(style)
            }
        },
        mounted () {
            store.commit('SET_SIDEBAR_TYPE', Vue.ls.get(SIDEBAR_TYPE, true))
            store.commit('TOGGLE_THEME', Vue.ls.get(DEFAULT_THEME, config.navTheme))
            store.commit('TOGGLE_LAYOUT_MODE', Vue.ls.get(DEFAULT_LAYOUT_MODE, config.layout))
            store.commit('TOGGLE_FIXED_HEADER', Vue.ls.get(DEFAULT_FIXED_HEADER, config.fixedHeader))
            store.commit('TOGGLE_FIXED_SIDERBAR', Vue.ls.get(DEFAULT_FIXED_SIDEMENU, config.fixSiderbar))
            store.commit('TOGGLE_CONTENT_WIDTH', Vue.ls.get(DEFAULT_CONTENT_WIDTH_TYPE, config.contentWidth))
            store.commit('TOGGLE_FIXED_HEADER_HIDDEN', Vue.ls.get(DEFAULT_FIXED_HEADER_HIDDEN, config.autoHideHeader))
            store.commit('TOGGLE_WEAK', Vue.ls.get(DEFAULT_COLOR_WEAK, config.colorWeak))
            store.commit('TOGGLE_COLOR', Vue.ls.get(DEFAULT_COLOR, config.primaryColor))
            store.commit('SET_TOKEN', Vue.ls.get(ACCESS_TOKEN))
            store.commit('SET_MULTI_PAGE', Vue.ls.get(DEFAULT_MULTI_PAGE, config.multipage))
        },
        render: h => h(App)
    }).$mount('#app')
}

start()
