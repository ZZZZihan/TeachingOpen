<template>
  <footer class="public-footer">
    <div class="campus-footer">
      <div><p class="campus-footer-name">TeachingOpen <span>人工智能与编程</span></p><p class="campus-footer-motto">学习 · 实践 · 创造 · 分享</p></div>
      <nav aria-label="学习入口"><router-link to="/courseList">探索课程 ↗</router-link><router-link to="/home">创作社区 ↗</router-link></nav>
    </div>
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
        brandName () { return (this.sysConfig.brandName || '').trim() || '人工智能教学平台' }
    }
}
</script>
<style scoped lang="less">
.campus-footer { max-width: 1200px; margin: auto; padding: 34px 0; display: flex; justify-content: space-between; align-items: center; gap: 24px; border-bottom: 1px solid #dce7f2; }
.campus-footer-name { color: #146fc2; font-family: 'Songti SC', SimSun, serif; font-size: 22px; margin: 0 0 10px; }
.campus-footer-name span { display: block; font-family: Georgia, serif; font-size: 10px; letter-spacing: 1.5px; margin-top: 4px; }
.campus-footer-motto { color: #5e6f82; letter-spacing: 3px; font-size: 12px; margin: 0; }
.campus-footer nav { display: flex; gap: 28px; }
.campus-footer a { color: #146fc2; }
.campus-footer a:focus-visible { outline: 2px solid #146fc2; outline-offset: 4px; }
.public-footer { background: #eef4ee; padding: 0 40px; border-top: 1px solid #d4e3d9; color: #5d6d7f; font-size: 12px; line-height: 1.7; }
.footer-inner { max-width: 1200px; margin: auto; padding: 22px 0; display: flex; align-items: center; justify-content: space-between; gap: 20px; }
.footer-inner strong { color: #454f5b; font-weight: 500; margin-right: 26px; }
.footer-inner nav { display: flex; gap: 28px; white-space: nowrap; }
.footer-inner a { color: #616d7a; }
.footer-inner a:hover { color: #146fc2; }
.footer-inner a:focus-visible { outline: 2px solid #146fc2; outline-offset: 4px; }
.configured-footer { padding: 24px; text-align: center; overflow-wrap: anywhere; }
.configured-footer /deep/ img { max-width: 100%; }
@media (max-width: 900px) { .footer-inner { padding: 22px 0; } }
@media (max-width: 600px) { .footer-inner { padding: 22px 0; flex-direction: column; align-items: flex-start; gap: 18px; } .footer-description { display: block; margin-top: 6px; } }
@media (max-width: 900px) { .public-footer { padding: 0 28px; } }
@media (max-width: 600px) { .public-footer { padding: 0 20px; } .campus-footer { align-items: flex-start; flex-direction: column; padding: 28px 0; } }
</style>
