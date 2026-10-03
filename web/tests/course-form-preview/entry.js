import Vue from 'vue'
import Antd from 'ant-design-vue'
import 'ant-design-vue/dist/antd.css'
import Course from 'preview-course'
import Unit from 'preview-unit'
import JModal from '@/components/jeecg/JModal/index.vue'
import Field from './field'
import { httpAction } from './api'
Vue.use(Antd)
Vue.component('j-modal',JModal)
Vue.component('j-dict-select-tag',Field)
new Vue({components:{Course,Unit},data:()=>({mode:'normal',saved:0}),methods:{async changeMode(){await httpAction('/__mode',{mode:this.mode},'post')},open(kind,existing){this.$refs[kind].title=existing?'编辑'+(kind==='course'?'课程':'单元'):'新建'+(kind==='course'?'课程':'单元');this.$refs[kind].edit(existing?{id:kind+'-fixture',courseId:'course-fixture',courseName:'合成课程',unitName:'合成单元',unitIntro:'观察与实验',courseDesc:'保留这段课程介绍',isShared:false,showHome:false,showType:2,courseVideoSource:2,courseVideo:'https://example.invalid/lesson.mp4',showCourseVideo:false,showCourseCase:true,showCoursePpt:false,showCoursePlan:false}:{} )}},template:`<main style="padding:24px"><h1>课程与单元表单</h1><p>本机合成组件检查 · 未登录平台 · 上传 / 富文本 / 字典 / 部门 / 地图为替代控件</p><label>场景 <select v-model="mode" @change="changeMode"><option value="normal">正常</option><option value="business-error">业务拒绝</option><option value="network-error">网络失败</option><option value="slow">慢速保存</option></select></label><p>成功回调 {{saved}}</p><a-button @click="open('course',true)">编辑课程</a-button><a-button @click="open('unit',true)">编辑单元</a-button><a-button @click="open('course',false)">新建课程</a-button><a-button @click="open('unit',false)">新建单元</a-button><Course ref="course" @ok="saved++"/><Unit ref="unit" @ok="saved++"/></main>`}).$mount('#app')
