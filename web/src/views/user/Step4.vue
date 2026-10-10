<template>
  <div class="recovery-success" role="status">
    <span class="success-mark" aria-hidden="true">✓</span><h2>密码已更新</h2><p>请使用新密码重新登录，继续你的学习与创作。</p>
    <router-link class="primary-button" :to="{ name: 'login', params: { username: userList.username } }">返回登录</router-link>
  </div>
</template>

<script>
export default { name: 'Step4', props: { userList: { type: Object, required: true } } }
</script>
