import Vue from 'vue'
import Antd from 'ant-design-vue'
import 'ant-design-vue/dist/antd.less'
import '@/assets/less/common.less'
import '@/utils/filter'
import List from 'preview-list'
import Center from 'preview-center'
import CampusMasthead from '@/components/brand/CampusMasthead'
Vue.use(Antd)
Vue.ls = { get: () => undefined }
window._CONFIG = { webURL: window.location.origin }
Vue.prototype.$route = { name: 'synthetic-preview', params: {}, meta: { pageHeader: true } }
Vue.prototype.$store = { getters: { nickname: '合成学生', avatar: '' } }
new Vue({ components: { List, Center, CampusMasthead }, data: () => ({ mode: new URLSearchParams(window.location.search).get('view') === 'center' ? 'center' : 'list', nested: false }), template: `<main><aside class="probe-controls"><strong>本机合成反馈验证 · 实际 Vue / Ant Design 组件</strong><p>受控只读 API，10 种反馈样例；无平台会话。个人中心模式保留实际 Index → MineWorksPage 映射。布局外壳为普通组件容器，不是认证 BasicLayout。</p><button @click="mode='list'">我的作品表格</button><button @click="mode='center'">实际个人中心卡片</button><label><input type="checkbox" v-model="nested"> 容器留白模拟</label></aside><CampusMasthead /><header class="preview-brand">人工智能教学平台 <span>学生作品</span></header><div :class="['preview-container', { nested }]" :key="mode"><List v-if="mode==='list'" /><Center v-else /></div></main>` }).$mount('#app')
const style = document.createElement('style'); style.textContent = 'html,body{margin:0;background:#f5f6f7;color:#20252b}.probe-controls{padding:12px 24px;background:#eef1f4;font:12px/1.7 sans-serif}.probe-controls p{margin:3px 0 8px}.probe-controls button{margin-right:8px;min-height:32px;background:#fff;border:1px solid #aeb7be;border-radius:3px;padding:4px 8px}.probe-controls label{display:inline-block;margin-top:6px}.preview-brand{padding:18px 32px;background:#fff;border-bottom:1px solid #e1e4e8;font-size:18px}.preview-brand span{font-size:13px;margin-left:16px;color:#737b82}.preview-container{width:100%;padding:24px;box-sizing:border-box;min-width:0;max-width:1440px;margin:auto}.preview-container.nested{padding:48px}@media(max-width:600px){.preview-container{padding:12px}.preview-container.nested{padding:24px}.preview-brand{padding:15px 20px}}'; document.head.appendChild(style)
