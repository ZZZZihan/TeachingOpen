import Vue from 'vue'
import VueRouter from 'vue-router'
import Antd from 'ant-design-vue'
import 'ant-design-vue/dist/antd.less'
import UserLayout from '@/components/layouts/UserLayout'
import Alteration from '@/views/user/Alteration'
Vue.use(VueRouter)
Vue.use(Antd)
Vue.prototype.$store = { state: { user: { sysConfig: { brandName: '人工智能教学平台' } } } }
const router = new VueRouter({ mode: 'history', routes: [{ path: '/user', component: UserLayout, children: [{ path: 'alteration', name: 'alteration', component: Alteration, meta: { keepAlive: false } }, { path: 'login', name: 'login', component: { template: '<section><h1>合成登录落点</h1><p>本预览不连接登录接口。</p><router-link to="/user/alteration">返回找回密码预览</router-link></section>' }, meta: { keepAlive: false } }] }, { path: '*', redirect: '/user/alteration' }] })
const fixture = () => ({ username: 'demo-student', maskedPhone: '138****0000', enteredPhone: '', phone: '13800000000', smscode: '123456', resendAt: 0 })
function recovery (component) { if (component.$options.name === 'Alteration') return component; for (const child of component.$children) { const found = recovery(child); if (found) return found } }
new Vue({ router, data: () => ({ mode: 'success', status: '' }), methods: {
  async show (step) { await this.$router.push('/user/alteration').catch(() => {}); await this.$nextTick(); const view = recovery(this); if (!view) return; view.userList = step === 0 ? {} : step === 3 ? { username: 'demo-student' } : fixture(); view.initialAccount = ''; view.currentTab = step },
  async configure () { const res = await fetch('/__mode', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ mode: this.mode }) }); this.status = res.ok ? '合成响应已切换' : '切换失败' }
}, template: `<div><aside class="probe-controls"><strong>本机合成 HTTP 组件验证</strong><p>实际找回密码组件与天津工业大学顶栏；不连接真实账号、短信或密码修改。各步骤按钮仅切换此合成页面。</p><nav><button @click="show(0)">展示确认账号</button><button @click="show(1)">展示手机验证</button><button @click="show(2)">展示设置密码</button><button @click="show(3)">展示完成</button></nav><label>合成响应 <select v-model="mode" @change="configure"><option value="success">成功</option><option value="sms-once-fail">短信首次失败</option><option value="sms-active">验证码仍有效</option><option value="verify-fail">验证码校验失败</option><option value="reset-unknown">重置结果不确定</option><option value="reset-committed">已改密但清理失败</option><option value="http-fail">HTTP 服务失败</option><option value="slow">慢响应 5 秒</option><option value="captcha-fail">验证码图片失败</option><option value="captcha-reject">图形验证码不通过</option></select></label><span role="status">{{ status }}</span></aside><router-view /></div>` }).$mount('#app')
const style = document.createElement('style'); style.textContent = 'html,body{margin:0}.probe-controls{padding:14px 24px;background:#eef1f4;border-bottom:1px solid #cbd1d6;font:12px/1.7 sans-serif}.probe-controls p{margin:4px 0}.probe-controls nav{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:8px}.probe-controls button,.probe-controls select{min-height:32px;background:white;border:1px solid #aeb7be;border-radius:3px;padding:4px 8px}.probe-controls span{margin-left:12px}'; document.head.appendChild(style)
