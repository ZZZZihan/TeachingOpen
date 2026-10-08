<template>
  <section class="registration-result" aria-labelledby="result-title">
    <span class="eyebrow">天工 · 你的学习空间</span>
    <template v-if="username">
      <h1 id="result-title">注册成功</h1>
      <p>你的登录账号：<strong>{{ username }}</strong></p>
      <p>请使用刚刚设置的密码登录，继续学习与创作。</p>
      <router-link class="login-button" :to="{ name: 'login', params: { username } }">前往登录 →</router-link>
    </template>
    <template v-else>
      <h1 id="result-title">账号服务</h1>
      <p>如已完成注册，请前往登录。</p>
      <router-link class="login-button" to="/user/login">前往登录 →</router-link>
    </template>
    <router-link class="home-link" to="/index">← 返回首页</router-link>
  </section>
</template>

<script>
export default {
    name: 'RegisterResult',
    computed: {
        username () {
            const value = this.$route.params.username
            return typeof value === 'string' && /^[a-zA-Z0-9_]{4,32}$/.test(value) ? value : ''
        }
    }
}
</script>

<style scoped>
.eyebrow { color: #74256a; font-size: 11px; letter-spacing: .12em; font-weight: 600; }
h1 { color: #20252b; font-size: 28px; margin: 12px 0 22px; }
p { color: #626b73; line-height: 1.8; overflow-wrap: anywhere; }
strong { color: #20252b; }
.login-button { display: block; background: #74256a; color: #fff; padding: 13px; text-align: center; border-radius: 3px; margin: 28px 0 20px; }
.home-link { color: #59646e; font-size: 13px; }
a:focus-visible { outline: 2px solid #74256a; outline-offset: 3px; }
</style>
