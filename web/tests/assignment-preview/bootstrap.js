import Vue from 'vue'
window._CONFIG = { domianURL: '' }
Vue.ls = { get: name => /token/i.test(name) ? undefined : { uploadType: 'local' } }
Vue.prototype.$store = { getters: { sysConfig: { uploadType: 'local', staticDomain: window.location.origin, qiniuDomain: '', qiniuArea: 'z0' } } }
