<template>
  <footer class="public-footer">
    <div class="campus-footer">
      <div><p class="campus-footer-name">天津工业大学 <span>TIANGONG UNIVERSITY</span></p><p class="campus-footer-motto">严谨 · 严格 · 求实 · 求是</p></div>
      <nav aria-label="学校资源"><a href="https://www.tiangong.edu.cn/" target="_blank" rel="noopener noreferrer">学校官网 ↗</a><a href="https://lib.tiangong.edu.cn/" target="_blank" rel="noopener noreferrer">图书馆 ↗</a></nav>
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
.campus-footer { max-width: 1200px; margin: auto; padding: 34px 0; display: flex; justify-content: space-between; align-items: center; gap: 24px; border-bottom: 1px solid #e6dfe5; }
.campus-footer-name { color: #74256a; font-family: 'Songti SC', SimSun, serif; font-size: 22px; margin: 0 0 10px; }
.campus-footer-name span { display: block; font-family: Georgia, serif; font-size: 10px; letter-spacing: 1.5px; margin-top: 4px; }
.campus-footer-motto { color: #6c616a; letter-spacing: 3px; font-size: 12px; margin: 0; }
.campus-footer nav { display: flex; gap: 28px; }
.campus-footer a { color: #74256a; }
.campus-footer a:focus-visible { outline: 2px solid #74256a; outline-offset: 4px; }
.public-footer { background: #f3eff2; padding: 0 40px; border-top: 1px solid #e1e4e8; color: #66717d; font-size: 12px; line-height: 1.7; }
.footer-inner { max-width: 1200px; margin: auto; padding: 22px 0; display: flex; align-items: center; justify-content: space-between; gap: 20px; }
.footer-inner strong { color: #454f5b; font-weight: 500; margin-right: 26px; }
.footer-inner nav { display: flex; gap: 28px; white-space: nowrap; }
.footer-inner a { color: #616d7a; }
.footer-inner a:hover { color: #74256a; }
.footer-inner a:focus-visible { outline: 2px solid #74256a; outline-offset: 4px; }
.configured-footer { padding: 24px; text-align: center; overflow-wrap: anywhere; }
.configured-footer /deep/ img { max-width: 100%; }
@media (max-width: 900px) { .footer-inner { padding: 22px 0; } }
@media (max-width: 600px) { .footer-inner { padding: 22px 0; flex-direction: column; align-items: flex-start; gap: 18px; } .footer-description { display: block; margin-top: 6px; } }
@media (max-width: 900px) { .public-footer { padding: 0 28px; } }
@media (max-width: 600px) { .public-footer { padding: 0 20px; } .campus-footer { align-items: flex-start; flex-direction: column; padding: 28px 0; } }
</style>
