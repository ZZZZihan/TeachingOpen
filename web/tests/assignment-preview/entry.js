import Vue from 'vue'
import Antd from 'ant-design-vue'
import 'ant-design-vue/dist/antd.css'
import Dialog from 'preview-dialog'
import { axios } from './api'
import './preview.css'
Vue.use(Antd)
new Vue({
  components: { Dialog },
  data: () => ({ mode: 'normal', refreshes: 0, records: '', latest: '' }),
  methods: {
    open (id) { this.$refs.dialog.open({ additionalId: id, departId: 'class-fixture', workName: id === 'task-a' ? '观察报告：身边的人工智能' : '第二份作业：设计一个智能助手', workType: 0 }) },
    async changeMode () { await axios({ url: '/__mode', method: 'post', data: { mode: this.mode } }) },
    async refresh () { this.records = JSON.stringify(await axios({ url: '/__state', method: 'get' }), null, 2) },
    submitted (record) { this.refreshes++; this.latest = record ? record.id : '旧版无返回对象'; this.refresh() }
  },
  template: '<main class="assignment-preview"><p>本机组件预览 · 实际提交弹窗与 HTTP 上传，使用隔离合成服务，无教学平台账号</p><h1>文件作业提交</h1><p>测试取消、移除、上传和提交失败恢复。</p><div class="preview-actions"><button @click="open(\'task-a\')">打开第一份作业</button><button @click="open(\'task-b\')">打开第二份作业</button><label>预览服务状态 <select v-model="mode" @change="changeMode"><option value="normal">正常</option><option value="upload-error">上传失败</option><option value="registration-error">文件登记失败</option><option value="submit-error">提交失败</option><option value="slow-upload">慢速上传</option><option value="slow-submit">慢速提交</option></select></label><button @click="refresh">刷新预览记录</button></div><p role="status">收到成功提交事件：{{ refreshes }} 次 {{ latest }}</p><details><summary>合成 HTTP 记录</summary><pre>{{ records }}</pre></details><Dialog ref="dialog" @ok="submitted" /></main>'
}).$mount('#app')
