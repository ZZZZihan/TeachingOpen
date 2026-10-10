import Vue from 'vue'
import Antd from 'ant-design-vue'
import 'ant-design-vue/dist/antd.css'
import JEditor from '@/components/jeecg/JEditor.vue'
import JModal from '@/components/jeecg/JModal/index.vue'
import NewsModal from '@/views/teaching/modules/TeachingNewsModal.vue'
import NewsDetail from '@/views/home/NewsDetail.vue'
Vue.use(Antd)
Vue.component('JModal', JModal)
Vue.ls = { get: () => ({ uploadType: 'local' }) }
window._CONFIG = { domianURL: '/api' }
Vue.prototype.$store = { getters: { sysConfig: { uploadType: 'local', staticDomain: window.location.origin + '/api/sys/common/static', qiniuDomain: window.location.origin + '/fake-qiniu', qiniuArea: 'z0' } } }
Vue.prototype.$route = { query: { id: 'news_content_browser' } }
new Vue({
    components: { JEditor, NewsModal, NewsDetail },
    data: () => ({ value: '<p>原有正文</p>', disabled: false, target: 'local', form: null, changes: 0, inputs: 0, detail: false }),
    created() { this.form = this.$form.createForm(this) },
    mounted() { window.newsProbe = this },
    template: `<main style="padding:20px"><h1>真实编辑器组件与新闻表单</h1><button @click="$refs.news.add()">新增新闻</button><button @click="$refs.main.reload()">重载编辑器</button><button @click="disabled=!disabled">切换只读</button><button @click="detail=!detail">新闻阅读</button><label>存储方式<select v-model="target"><option value="local">local</option><option value="database">database</option><option value="qiniu">qiniu</option></select></label><a-tabs><a-tab-pane key="one" tab="正文"><j-editor data-probe="main" ref="main" v-model="value" :height="320" :disabled="disabled" :uploadTarget="target" @input="inputs++" /></a-tab-pane><a-tab-pane key="two" tab="其他"><p>其他页面</p></a-tab-pane></a-tabs><a-form :form="form"><a-form-item label="系统配置正文"><j-editor ref="change" v-decorator="['body']" triggerChange :height="120" @change="changes++" /></a-form-item></a-form><news-modal ref="news"/><news-detail v-if="detail" ref="reader"/></main>`
}).$mount('#app')
