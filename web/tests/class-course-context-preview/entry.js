import Vue from 'vue'
import Antd from 'ant-design-vue'
import 'ant-design-vue/dist/antd.css'
import DeptCourseInfo from '@/views/system/modules/DeptCourseInfo'
import { state } from './api'
Vue.use(Antd)
new Vue({ components: { DeptCourseInfo }, data: () => ({ label: '', state }), mounted () { this.open('a') }, methods: {
  open (letter) { this.label = '合成班级 ' + letter.toUpperCase(); this.$refs.courses.open({ id: 'class-' + letter, orgCategory: '3', departName: this.label }) },
  clear () { this.label = '未选择班级'; this.$refs.courses.clearList() },
  schedule () { this.label += ' · 5 秒后切换 B'; setTimeout(() => this.open('b'), 5000) }
}, template: `<main style="max-width:1100px;margin:32px auto;padding:0 32px;font-family:Arial,sans-serif">
  <p>本机合成组件检查 · 实际 Vue / Ant Design 三个组件 · API 为内存替代 · 未登录平台</p>
  <h1>班级课程管理</h1><nav style="display:flex;gap:12px;margin:24px 0"><a-button @click="open('a')">班级 A</a-button><a-button @click="open('b')">班级 B</a-button><a-button @click="clear">清空班级</a-button><a-button @click="schedule">5 秒后切换 B</a-button><label><input type="checkbox" v-model="state.slow"> 慢响应</label></nav>
  <h2>{{label}}</h2><DeptCourseInfo ref="courses" />
  <details open style="margin-top:24px"><summary>合成 API 请求记录</summary><pre style="white-space:pre-wrap">{{JSON.stringify(state.calls, null, 2)}}</pre></details>
</main>` }).$mount('#app')
