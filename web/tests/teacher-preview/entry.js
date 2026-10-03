import Vue from 'vue'
import Antd from 'ant-design-vue'
import 'ant-design-vue/dist/antd.css'
import List from 'preview-list'
import { axios } from './api'
import './preview.css'
Vue.use(Antd)
Vue.prototype.$route = { query: {} }
Vue.component('j-modal', { props: ['visible','title','width'], template: '<a-modal :visible="visible" :title="title" :width="width" @ok="$emit(\'ok\')" @cancel="$emit(\'cancel\')"><slot /></a-modal>' })
Vue.component('j-editable-table', { props: ['dataSource'], methods: { getValues (callback) { callback(null, this.dataSource || []) } }, template: '<div><a-table :columns="[{title:\'创建人\',dataIndex:\'createBy\'},{title:\'评论内容\',dataIndex:\'comment\'}]" :data-source="dataSource" :pagination="false" row-key="id" /></div>' })
new Vue({ components: { List }, data: () => ({ mode: 'normal' }), methods: { async changeMode () { await axios({ url: '/__mode', method: 'post', data: { mode: this.mode } }); this.$refs.list.loadData() } }, template: '<div><div class="preview-note">本机合成组件预览 · 教师页面 / 实际批改组件 · 未登录教学平台<label>场景 <select v-model="mode" @change="changeMode"><option value="normal">正常</option><option value="empty">空列表</option><option value="list-error">列表失败</option><option value="grade-error">评分读取失败</option><option value="comments-error">讨论读取失败</option><option value="save-error">保存失败</option><option value="slow-save">慢速保存</option><option value="many">多页作品</option></select></label></div><header class="preview-nav"><strong>TeachingOpen</strong><span>教学空间</span></header><List ref="list" /></div>' }).$mount('#app')
