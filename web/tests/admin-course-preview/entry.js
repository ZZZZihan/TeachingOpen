import Vue from 'vue'
import VueRouter from 'vue-router'
import Antd from 'ant-design-vue'
import 'ant-design-vue/dist/antd.css'
import Course from 'preview-course'
import Unit from 'preview-unit'
import Dict from './dict'
import { axios } from './api'
import './preview.css'
Vue.use(VueRouter); Vue.use(Antd); Vue.component('j-dict-select-tag', Dict)
const router = new VueRouter({ routes: [{ path: '/', redirect: '/courses' }, { path: '/courses', component: Course }, { path: '/course/courseUnit', component: Unit }] })
new Vue({ router, data: () => ({ mode: 'normal' }), methods: { async changeMode () { await axios({ url: '/__mode', method: 'post', data: { mode: this.mode } }); this.$refs.route.loadData() } },
  template: '<div><div class="preview-note">本机合成组件检查 · 真实管理员列表 · 未登录教学平台 · 字典、部门、维护入口为替代控件<label>场景 <select v-model="mode" @change="changeMode"><option value="normal">正常</option><option value="empty">空列表</option><option value="list-error">业务失败</option><option value="network-error">网络失败</option><option value="malformed">畸形响应</option><option value="slow-list">慢速列表</option><option value="delete-error">删除失败</option><option value="slow-delete">慢速删除</option></select></label></div><nav class="preview-nav"><strong>TeachingOpen · 合成管理员空间</strong><router-link to="/courses">合成课程管理</router-link><router-link to="/course/courseUnit">合成单元管理</router-link></nav><router-view ref="route" /></div>'
}).$mount('#app')
