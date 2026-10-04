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
window.loadingScenario = new URLSearchParams(window.location.search).get('scenario') || 'success'
Vue.prototype.$route = { name: 'synthetic-preview', params: {}, meta: { pageHeader: true } }
Vue.prototype.$store = { getters: { nickname: '合成学生', avatar: '' } }
new Vue({
    components: { List, Center, CampusMasthead },
    data: () => ({ mode: new URLSearchParams(window.location.search).get('view') === 'center' ? 'center' : 'list', scenario: window.loadingScenario, nested: false }),
    watch: { scenario (value) { window.loadingScenario = value } },
    methods: {
        requestAgain () {
            const find = node => node && (['MineWorkList', 'MineWorksCard'].includes(node.$options.name) ? node : node.$children.map(find).find(Boolean))
            const target = find(this.$refs.list || this.$refs.center)
            if (target) target.$options.name === 'MineWorkList' ? target.loadData() : target.getWorkList()
        }
    },
    template: `<main><aside class="probe-controls"><strong>本机合成加载故障验证 · 实际 Vue / Ant Design 组件</strong><p>受控只读 HTTP，无平台会话；实际个人中心 Index → MineWorksPage 映射。外壳为普通组件容器。超时场景仅预览传输层改为 1.2 秒，产品 60 秒不改；全局认证/通知拦截器不在此预览内。</p><button @click="mode='list'">我的作品表格</button><button @click="mode='center'">实际个人中心卡片</button><label>下次请求场景 <select v-model="scenario"><option value="success">成功</option><option value="empty">成功空列表</option><option value="success-empty-page">当前页空 / 总数 25</option><option value="http500">HTTP 500</option><option value="business">业务失败 code 510</option><option value="malformed">非法 records</option><option value="network">网络断开</option><option value="delayed">延迟成功 4.5 秒</option><option value="timeout">请求超时 1.2 秒</option></select></label><button @click="requestAgain">重新请求（保留实例）</button><label><input type="checkbox" v-model="nested"> 容器留白模拟</label></aside><CampusMasthead /><header class="preview-brand">人工智能教学平台 <span>学生作品</span></header><div :class="['preview-container', { nested }]" :key="mode"><List v-if="mode==='list'" ref="list" /><Center v-else ref="center" /></div></main>`
}).$mount('#app')
const style = document.createElement('style'); style.textContent = 'html,body{margin:0;background:#f5f6f7;color:#20252b}.probe-controls{padding:12px 24px;background:#eef1f4;font:12px/1.7 sans-serif}.probe-controls p{margin:3px 0 8px}.probe-controls button{margin-right:8px;min-height:32px;background:#fff;border:1px solid #aeb7be;border-radius:3px;padding:4px 8px}.probe-controls label{display:inline-block;margin-top:6px}.preview-brand{padding:18px 32px;background:#fff;border-bottom:1px solid #e1e4e8;font-size:18px}.preview-brand span{font-size:13px;margin-left:16px;color:#737b82}.preview-container{width:100%;padding:24px;box-sizing:border-box;min-width:0;max-width:1440px;margin:auto}.preview-container.nested{padding:48px}@media(max-width:600px){.preview-container{padding:12px}.preview-container.nested{padding:24px}.preview-brand{padding:15px 20px}}'; document.head.appendChild(style)
