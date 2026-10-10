<template>
  <div class="campus-masthead">
    <div class="campus-masthead-inner">
      <router-link class="university-link" to="/index" aria-label="TeachingOpen 首页">
        <img
          v-if="!imageFailed"
          src="@/assets/brand/wordmark.svg"
          width="265"
          height="66"
          alt="TeachingOpen 人工智能与编程"
          @error="imageFailed = true">
        <span v-else class="university-name">TeachingOpen<small>人工智能与编程</small></span>
      </router-link>
      <div class="university-motto"><p>学习 · 实践 · 创造 · 分享</p><span>让想法成为作品</span></div>
    </div>
  </div>
</template>
<script>
export default {
    name: 'CampusMasthead',
    data () { return { imageFailed: false } }
}
</script>
<style scoped>
.campus-masthead { background: #146fc2; color: #fff; }
.campus-masthead-inner { max-width: 1280px; margin: auto; padding: 16px 40px; display: flex; align-items: center; justify-content: space-between; gap: 24px; }
.university-link { display: inline-flex; color: #fff; flex-shrink: 0; }
.university-link img { width: 225px; height: auto; display: block; }
.university-link:focus-visible { outline: 2px solid #fff; outline-offset: 5px; }
.university-name { font-family: 'Songti SC', SimSun, serif; font-size: 28px; letter-spacing: 3px; }
.university-name small { display: block; font-family: Georgia, serif; font-size: 11px; letter-spacing: 1px; }
.university-motto { text-align: right; }
.university-motto p { color: #fff; font-family: 'Songti SC', SimSun, serif; font-size: 18px; letter-spacing: 5px; margin: 0 0 8px; }
.university-motto span { color: #e3f0ff; font-size: 10px; letter-spacing: 3px; }
@media (max-width: 900px) { .campus-masthead-inner { padding: 15px 28px; } }
@media (max-width: 600px) { .campus-masthead-inner { padding: 15px 20px; gap: 12px; } .university-link img { width: 178px; } .university-motto p { font-size: 12px; letter-spacing: 1px; max-width: 90px; line-height: 1.8; margin: 0; } .university-motto span { display: none; } .university-name { font-size: 22px; } }
</style>
