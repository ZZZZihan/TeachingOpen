import Vue from 'vue'
import Antd from 'ant-design-vue'
import 'ant-design-vue/dist/antd.css'
import DeptUserInfo from '@/views/system/modules/DeptUserInfo'
import SelectUserModal from '@/views/system/modules/SelectUserModal'
import { state } from './api'
Vue.use(Antd)
new Vue({ components: { DeptUserInfo, SelectUserModal }, data: () => ({ label: '', state, legacySelection: null }), mounted () { this.open('a') }, methods: {
  open (letter) { this.label = '合成班级 ' + letter.toUpperCase(); this.$refs.members.open({ id: 'class-' + letter, orgCategory: '3', departName: this.label }) },
  clear () { this.label = '未选择班级'; this.$refs.members.clearList() },
  schedule () { this.label += ' · 5 秒后切换 B'; setTimeout(() => this.open('b'), 5000) }
}, template: `<main style="max-width:1100px;margin:32px auto;padding:0 32px;font-family:Arial,sans-serif">
  <p>本机合成组件验证 · 实际 Vue / Ant Design 成员组件 · API 为内存替代 · 未登录平台</p>
  <h1>班级成员管理</h1><nav style="display:flex;flex-wrap:wrap;gap:12px;margin:24px 0"><a-button @click="open('a')">班级 A</a-button><a-button @click="open('b')">班级 B</a-button><a-button @click="clear">取消班级选择</a-button><a-button @click="schedule">5 秒后切换 B</a-button><label><input type="checkbox" v-model="state.slow"> 慢响应</label><label><input type="checkbox" v-model="state.fail"> 模拟失败</label></nav>
  <h2>{{label}}</h2><DeptUserInfo ref="members" />
  <section style="margin-top:24px"><a-button @click="$refs.legacy.visible = true">共享选择器（旧接口）</a-button><p>旧接口事件：{{JSON.stringify(legacySelection)}}</p><SelectUserModal ref="legacy" @selectFinished="legacySelection = $event" /></section>
  <details open style="margin-top:24px"><summary>合成 API 请求记录</summary><pre style="white-space:pre-wrap">{{JSON.stringify(state.calls, null, 2)}}</pre></details>
</main>` }).$mount('#app')
