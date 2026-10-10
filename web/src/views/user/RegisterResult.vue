<template>
  <section class="registration-result">
    <h1>注册成功</h1>
    <p>请使用手机号和密码登录，继续你的学习与创作。</p>
    <router-link :to="{ name: 'login', params: { username: phone } }">前往登录</router-link>
    <router-link class="home-link" to="/index">返回首页</router-link>
  </section>
</template>

<script>
export default {
    name: 'RegisterResult',
    computed: { phone () { return this.$route.params.phone || '' } }
}
</script>

<style scoped>
.registration-result { max-width: 480px; margin: 80px auto; padding: 24px; text-align: center; }
.registration-result p { margin: 24px 0; line-height: 1.8; color: #69747c; }
.registration-result a { color: #146fc2; }
.home-link { display: block; margin-top: 20px; }
</style>
