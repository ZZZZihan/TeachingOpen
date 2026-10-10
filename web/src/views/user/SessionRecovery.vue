<template>
  <section class="session-recovery" aria-labelledby="session-heading" :aria-busy="busy">
    <span class="eyebrow">连接未完成</span>
    <h1 id="session-heading">暂时无法打开你的空间</h1>
    <p role="status">登录信息已保留，但页面权限未能加载。请检查网络后重试；如果持续出现，请联系平台管理员。</p>
    <button type="button" :disabled="busy" @click="retry">{{ busy ? '正在重试…' : '重新加载' }}</button>
    <router-link to="/index">先浏览首页</router-link>
    <button class="switch-account" type="button" :disabled="busy" @click="switchAccount">退出并切换账号</button>
  </section>
</template>
<script>
import { safeRedirect } from '@/utils/session'
export default {
    name: 'SessionRecovery',
    data () { return { busy: false } },
    methods: {
        async retry () {
            if (this.busy) return
            this.busy = true
            try { await this.$router.replace(safeRedirect(this.$route.query.redirect)) } catch (_) { /* The guard keeps this retry view. */ } finally { this.busy = false }
        },
        async switchAccount () {
            if (this.busy) return
            this.busy = true
            const redirect = safeRedirect(this.$route.query.redirect)
            await this.$store.dispatch('Logout')
            await this.$router.replace({ path: '/user/login', query: { redirect } })
        }
    }
}
</script>
<style scoped>
.eyebrow { color: #a53d47; font-size: 12px; letter-spacing: .08em; }
h1 { font-size: 25px; color: #20252b; line-height: 1.5; margin: 16px 0; }
p { color: #626b73; line-height: 1.9; margin-bottom: 28px; }
button { width: 100%; min-height: 44px; color: #fff; background: #b23e4c; border: 1px solid #b23e4c; border-radius: 3px; cursor: pointer; margin-bottom: 20px; }
button:disabled { opacity: .65; cursor: wait; }
a { display: block; text-align: center; color: #59646e; }
.switch-account { background: transparent; color: #59646e; border: 0; margin: 16px 0 0; font-size: 12px; }
button:focus-visible, a:focus-visible { outline: 2px solid #9b3844; outline-offset: 3px; }
</style>
