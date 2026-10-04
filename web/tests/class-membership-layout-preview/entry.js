import Vue from 'vue'
import Antd from 'ant-design-vue'
import 'ant-design-vue/dist/antd.less'
import '@/assets/less/common.less'
import DepartList from '@/views/system/DepartList'
import DeptUserInfo from '@/views/system/modules/DeptUserInfo'
import SelectUserModal from '@/views/system/modules/SelectUserModal'
import { state } from './api'
Vue.use(Antd)
Vue.prototype.$route = { params: {} }
Vue.prototype.$router = { back () {} }
new Vue({ components: { DeptUserInfo, SelectUserModal, DepartList }, data: () => ({ nested: false, label: '', state, legacySelection: null }), mounted () { this.open('a') }, methods: {
  open (letter) { this.label = '合成班级 ' + letter.toUpperCase(); this.$refs.members.open({ id: 'class-' + letter, orgCategory: '3', departName: this.label }) },
  clear () { this.label = '未选择班级'; this.$refs.members.clearList() },
  schedule () { this.label += ' · 5 秒后切换 B'; setTimeout(() => this.open('b'), 5000) }
}, template: `<main style="max-width:1100px;margin:32px auto;padding:0 32px;font-family:Arial,sans-serif">
  <p>本机合成组件验证 · 实际 Vue / Ant Design 成员组件 · API 为内存替代 · 未登录平台</p>
  <h1>班级成员布局验证</h1><label><input type="checkbox" v-model="nested"> 实际 DepartList 父页面</label><nav style="display:flex;flex-wrap:wrap;gap:12px;margin:24px 0"><a-button @click="open('a')">班级 A</a-button><a-button @click="open('b')">班级 B</a-button><a-button @click="clear">取消班级选择</a-button><a-button @click="schedule">5 秒后切换 B</a-button><label><input type="checkbox" v-model="state.stress"> 长文本与分页数据（重新查询生效）</label><label><input type="checkbox" v-model="state.slow"> 慢响应</label><label><input type="checkbox" v-model="state.fail"> 模拟失败</label></nav>
  <section v-show="!nested"><h2>{{label}}</h2><DeptUserInfo ref="members" /></section><section v-if="nested"><p>实际父页面：通过左侧树选择班级，再进入老师/学生页签。其他编辑面板未接入。</p><DepartList /></section>
  <section style="margin-top:24px"><a-button @click="$refs.legacy.visible = true">共享选择器（旧接口）</a-button><p>旧接口事件：{{JSON.stringify(legacySelection)}}</p><SelectUserModal ref="legacy" @selectFinished="legacySelection = $event" /></section>
  <details open style="margin-top:24px"><summary>合成 API 请求记录</summary><pre style="white-space:pre-wrap">{{JSON.stringify(state.calls, null, 2)}}</pre></details>
</main>` }).$mount('#app')
