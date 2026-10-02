import Vue from 'vue'
import Antd from 'ant-design-vue'
import 'ant-design-vue/dist/antd.css'
import JModal from '@/components/jeecg/JModal/index.vue'
import Reader from 'preview-reader'
import { unit } from './fixtures'
import './preview.css'
Vue.use(Antd); Vue.component('j-modal', JModal)
new Vue({
  components: { Reader },
  methods: { open () { this.$refs.reader.view({ ...unit }) }, empty () { this.$refs.reader.view({ id: 'empty', unitName: '尚未发布资料的单元' }) }, broken () { this.$refs.reader.view({ ...unit, id: 'recover', courseVideo: '/fixtures/recover.mp4', courseVideo_url: '/fixtures/recover.mp4' }) } },
  template: '<main class="reader-preview"><p>本机组件与媒体预览 · 使用实际学习弹窗、合成 API 与自制媒体，未登录教学平台</p><h1>学习阅读器</h1><button @click="open">打开视频单元</button><button @click="empty">打开无资源单元</button><button @click="broken">打开失效视频</button><Reader ref="reader" /></main>'
}).$mount('#app')
