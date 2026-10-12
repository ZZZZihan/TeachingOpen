import Vue from 'vue'
import Antd from 'ant-design-vue'
import 'ant-design-vue/dist/antd.css'
import AdditionalWork from 'preview-additional'
import JModal from '@/components/jeecg/JModal/index.vue'
import JDictSelectTag from '@/components/dict/JDictSelectTag.vue'

Vue.use(Antd)
Vue.component('j-modal', JModal)
Vue.component('j-dict-select-tag', JDictSelectTag)
window.fixtureApp = new Vue({
    components: { AdditionalWork },
    data: () => ({ saved: 0 }),
    methods: {
        open () {
            this.$refs.work.title = '新建附加作业 · 合成验证'
            this.$refs.work.edit({ status: '1', codeType: '0', workDept: 'class-a' })
        }
    },
    template: `<main style="padding:24px"><h1>附加作业表单验证</h1><p>真实表单、上传和班级组件 · 本机合成接口与附件</p><p>成功回调：<span id="saved">{{ saved }}</span></p><a-button id="open" @click="open">新建附加作业</a-button><AdditionalWork ref="work" @ok="saved++" /></main>`
}).$mount('#app')
