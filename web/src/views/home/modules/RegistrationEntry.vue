<template>
  <section class="registration-entry" aria-labelledby="registration-entry-title">
    <h3 id="registration-entry-title">加入学习，一起成长</h3>
    <p>创建账号，开启课程学习与作品创作。</p>
    <router-link class="registration-button" :to="{ name: 'register' }">立即注册</router-link>
  </section>
</template>

<script>
export default {
    name: 'RegistrationEntry'
}
</script>

<style scoped lang="less">
.registration-entry { padding: 24px; background: #f7f4f7; border: 1px solid #e9e1e8; border-radius: 12px; }
h3 { margin: 0 0 10px; font-size: 20px; color: #20252b; }
p { margin: 0 0 18px; color: #59646e; line-height: 1.6; }
.registration-button { display: inline-block; padding: 10px 24px; background: #74256a; border-radius: 6px; color: #fff; font-weight: 600; }
.registration-button:hover { background: #602058; }
a:focus-visible { outline: 2px solid #74256a; outline-offset: 4px; }
@media (max-width: 680px) { .registration-entry { padding: 20px; } }
</style>
