<template>
  <footer class="public-footer">
    <div v-if="sysConfig.footer" class="configured-footer" v-html="sysConfig.footer"></div>
    <div v-else class="footer-inner">
      <div><strong>{{ brandName }}</strong><span class="footer-description">让学习与创作，在这里发生。</span></div>
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
.public-footer { background: #fff; border-top: 1px solid #e6eaf0; color: #64748b; font-size: 13px; line-height: 1.7; }
.footer-inner { max-width: 1260px; margin: auto; padding: 28px 24px; display: flex; align-items: center; justify-content: space-between; gap: 20px; }
.footer-inner strong { color: #334764; font-weight: 600; margin-right: 20px; }
.footer-inner nav { display: flex; gap: 24px; white-space: nowrap; }
.footer-inner a { color: #536581; }
.footer-inner a:hover { color: #245bd6; }
.footer-inner a:focus-visible { outline: 3px solid #7194e4; outline-offset: 4px; }
.configured-footer { padding: 24px; text-align: center; overflow-wrap: anywhere; }
.configured-footer /deep/ img { max-width: 100%; }
@media (max-width: 600px) { .footer-inner { padding: 24px 16px; flex-direction: column; align-items: flex-start; gap: 12px; } .footer-description { display: block; margin-top: 4px; } }
</style>
