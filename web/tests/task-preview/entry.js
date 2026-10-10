import Vue from 'vue'
import Antd from 'ant-design-vue'
import 'ant-design-vue/dist/antd.css'
import List from 'preview-list'
import { axios } from './api'
import './preview.css'
Vue.use(Antd)
new Vue({
  components: { List }, data: () => ({ mode: 'normal' }),
  methods: { async changeMode () { await axios({ url: '/__mode', method: 'post', data: { mode: this.mode } }); this.$refs.list.getList() } },
  template: '<div><div class="preview-note">本机合成组件预览 · 实际页面与提交弹窗，未登录教学平台 <label>预览数据 <select v-model="mode" @change="changeMode"><option value="normal">正常</option><option value="empty">空列表</option><option value="list-error">列表失败</option><option value="slow-list">慢速读取</option><option value="many">多页作业</option></select></label></div><header class="preview-nav"><strong>TeachingOpen</strong><span>学习空间</span></header><List ref="list" /></div>'
}).$mount('#app')
