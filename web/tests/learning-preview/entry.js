import Vue from 'vue'
import VueRouter from 'vue-router'
import Antd from 'ant-design-vue'
import 'ant-design-vue/dist/antd.css'
import Courses from 'preview-courses'
import Units from 'preview-units'
import './preview.css'
Vue.use(VueRouter); Vue.use(Antd)
Vue.component('j-modal', { props: ['visible', 'title'], template: '<section v-if="visible" class="preview-reader" role="dialog"><h2>{{ title }}</h2><slot></slot><button @click="$emit(\'cancel\')">关闭介绍</button></section>' })
const router = new VueRouter({ routes: [{ path: '/teaching/mineCourse/cardList', component: Courses }, { path: '/teaching/mineCourse/courseUnitCard', component: Units }, { path: '*', component: { template: '<p class="preview-notice">这个入口不在组件预览范围内。</p>' } }] })
new Vue({ router, template: '<div><div class="preview-notice">合成组件预览 · 用于排版与入口检查，未连接后端或登录账号</div><header class="preview-nav"><strong>TeachingOpen</strong><nav><router-link to="/teaching/mineCourse/cardList">我的课程</router-link><router-link to="/teaching/mineCourse/courseUnitCard?id=preview-a">课程目录</router-link></nav></header><router-view /></div>' }).$mount('#app')
