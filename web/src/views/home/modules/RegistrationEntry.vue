<template>
  <section class="registration-entry" aria-labelledby="registration-entry-title">
    <div class="registration-copy">
      <h3 id="registration-entry-title">加入学习，一起成长</h3>
      <p>创建账号，开启课程学习与作品创作。</p>
    </div>
    <router-link class="registration-button" :to="{ name: 'register' }">立即注册</router-link>
  </section>
</template>

<script>
export default {
    name: 'RegistrationEntry'
}
</script>

<style scoped lang="less">
.registration-entry { display: flex; align-items: center; flex-wrap: wrap; gap: 16px 20px; }
.registration-copy { flex: 1 1 230px; min-width: 0; }
h3 { margin: 0 0 6px; font-size: 18px; color: #20252b; }
p { margin: 0; font-size: 13px; color: #59646e; line-height: 1.6; }
.registration-button { display: inline-flex; align-items: center; justify-content: center; flex: 0 0 auto; min-height: 44px; padding: 10px 22px; white-space: nowrap; background: #146fc2; border-radius: 6px; color: #fff; font-weight: 600; }
.registration-button:hover { background: #095b9e; }
a:focus-visible { outline: 2px solid #146fc2; outline-offset: 4px; }
@media (max-width: 600px) { .registration-entry { gap: 14px; } }
</style>
