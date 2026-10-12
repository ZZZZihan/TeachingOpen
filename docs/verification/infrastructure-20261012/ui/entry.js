import Vue from 'vue'
import Antd from 'ant-design-vue'
import 'ant-design-vue/dist/antd.css'
import DataSourceModal from 'preview-data-source'
import QuartzModal from 'preview-quartz'
import DictSelect from 'preview-dict'
Vue.use(Antd)
Vue.component('JDictSelectTag', DictSelect)
window._CONFIG = { domianURL: '' }
const source = {id:'synthetic-source-id',code:'synthetic_source',name:'合成数据源',dbType:'1',dbDriver:'com.mysql.jdbc.Driver',dbUrl:'jdbc:synthetic-no-driver',dbName:'synthetic_db',dbUsername:'synthetic_user',remark:'浏览器验证使用合成记录；没有存储密码返回'}
const job = {id:'synthetic-job-id',jobType:'sample',jobClassName:'org.jeecg.modules.quartz.job.SampleJob',cronExpression:'0 0 0 1 1 ? 2099',parameter:'synthetic parameter',description:'既有示例任务（合成）',status:0}
const app = new Vue({
  components: {DataSourceModal, QuartzModal},
  data: () => ({success:0}),
  methods: {
    sourceEdit() {this.$refs.source.title='编辑数据源';this.$refs.source.edit({...source})},
    sourceAdd() {this.$refs.source.title='新增数据源';this.$refs.source.edit({...source,id:undefined,code:'synthetic_new'})},
    quartzEdit() {this.$refs.quartz.title='编辑既有任务';this.$refs.quartz.edit({...job})},
    quartzAdd() {this.$refs.quartz.title='新增任务';this.$refs.quartz.add()},
  },
  template:`<main style="padding:24px;max-width:1100px;margin:auto"><h1>H01 运维弹窗 · 合成环境</h1><p>真实 Vue / Ant Design / Cron / 字典控件；接口仅发送到本地记录器。</p><div style="display:flex;flex-wrap:wrap;gap:8px"><a-button @click="sourceEdit">编辑数据源</a-button><a-button @click="sourceAdd">新增数据源</a-button><a-button @click="quartzEdit">编辑既有任务</a-button><a-button @click="quartzAdd">新增任务</a-button></div><p data-testid="success-count">成功保存：{{success}}</p><DataSourceModal ref="source" @ok="success++"/><QuartzModal ref="quartz" @ok="success++"/></main>`
}).$mount('#app')
window.h01 = {app}
