<template>
  <footer class="public-footer">
    <div v-if="sysConfig.footer" class="configured-footer" v-html="sysConfig.footer"></div>
    <div v-else class="footer-inner">
      <div><strong>{{ brandName }}</strong><span class="footer-description">课程学习 · 编程实践 · 教学协作</span></div>
      <nav aria-label="页脚导航"><router-link to="/courseList">探索课程</router-link><router-link to="/home">创作社区</router-link></nav>
    </div>
  </footer>
</template>
<script>
export default {
    computed: {
        sysConfig () { return this.$store.getters.sysConfig || {} },
        brandName () { return (this.sysConfig.brandName || '').trim() || 'TeachingOpen' }
    }
}
</script>
<style scoped lang="less">
.public-footer { border-top: 1px solid #e1e4e8; color: #66717d; font-size: 12px; line-height: 1.7; }
.footer-inner { max-width: 1280px; margin: auto; padding: 30px 40px; display: flex; align-items: center; justify-content: space-between; gap: 20px; }
.footer-inner strong { color: #454f5b; font-weight: 500; margin-right: 26px; }
.footer-inner nav { display: flex; gap: 28px; white-space: nowrap; }
.footer-inner a { color: #616d7a; }
.footer-inner a:hover { color: #c84a55; }
.footer-inner a:focus-visible { outline: 2px solid #c84a55; outline-offset: 4px; }
.configured-footer { padding: 24px; text-align: center; overflow-wrap: anywhere; }
.configured-footer /deep/ img { max-width: 100%; }
@media (max-width: 900px) { .footer-inner { padding: 26px 28px; } }
@media (max-width: 600px) { .footer-inner { padding: 24px 22px; flex-direction: column; align-items: flex-start; gap: 18px; } .footer-description { display: block; margin-top: 6px; } }
</style>
