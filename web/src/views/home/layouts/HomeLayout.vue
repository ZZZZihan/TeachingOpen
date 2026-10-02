<template>
  <div class="public-layout" :style="backgroundStyle">
    <a class="skip-link" href="#public-content">跳到主要内容</a>
    <Header />
    <main id="public-content" class="public-content" tabindex="-1">
      <section v-if="showIntro" class="welcome-panel" :class="{ 'has-banner': hasBanner }" aria-labelledby="welcome-title">
        <div class="welcome-copy">
          <p class="eyebrow">探索 · 学习 · 创作</p>
          <h1 id="welcome-title">从好奇开始，<br />让想法成为作品。</h1>
          <p class="welcome-description">在课程中学习人工智能与编程，在动手实践中发现更多可能。</p>
          <div class="welcome-actions">
            <router-link class="primary-action" to="/courseList">探索课程 <a-icon type="arrow-right" /></router-link>
            <router-link class="secondary-action" :to="isLoggedIn ? '/teaching/mineCourse/cardList' : '/user/login'">{{ isLoggedIn ? '我的课程' : '登录，继续学习' }}</router-link>
          </div>
        </div>
        <Banner v-if="hasBanner" class="welcome-banner" />
        <div v-else class="learning-path" aria-label="学习路径">
          <div class="path-step"><span class="step-icon"><a-icon type="compass" /></span><div><strong>发现兴趣</strong><p>选择想要探索的课程</p></div><span class="step-number">01</span></div>
          <div class="path-step"><span class="step-icon"><a-icon type="experiment" /></span><div><strong>动手实践</strong><p>跟随单元学习与练习</p></div><span class="step-number">02</span></div>
          <div class="path-step"><span class="step-icon"><a-icon type="bulb" /></span><div><strong>表达创意</strong><p>用编程完成自己的作品</p></div><span class="step-number">03</span></div>
        </div>
      </section>
      <router-view />
    </main>
    <Footer />
  </div>
</template>
<script>
import Vue from 'vue'
import { getFileAccessHttpUrl } from '@/api/manage'
import { ACCESS_TOKEN } from '@/store/mutation-types'
import Header from '../modules/Header'
import Banner from '../modules/Banner'
import Footer from '../modules/Footer'
export default {
    name: 'HomeLayout',
    components: { Header, Banner, Footer },
    computed: {
        sysConfig () { return this.$store.getters.sysConfig || {} },
        isLoggedIn () { return Boolean(this.$store.state.user.token || Vue.ls.get(ACCESS_TOKEN)) },
        showIntro () {
            return this.$route.path === '/home' || (this.$route.path === '/index' && !this.sysConfig._homeHtml)
        },
        hasBanner () { return Boolean((this.sysConfig.banner || '').trim()) },
        backgroundStyle () {
            return {
                backgroundColor: this.sysConfig.homeBgColor || '',
                backgroundImage: this.sysConfig.file_homeBg ? 'url(' + getFileAccessHttpUrl(this.sysConfig.file_homeBg) + ')' : '',
                backgroundRepeat: this.sysConfig.homeBgRepeat || 'no-repeat'
            }
        }
    }
}
</script>
<style scoped lang="less">
.public-layout { min-height: 100vh; display: flex; flex-direction: column; background: #f5f7fb; background-size: 100% auto; color: #24334a; }
.public-content { width: 100%; max-width: 1260px; margin: 0 auto; padding: 32px 24px 48px; flex: 1; }
.skip-link { position: absolute; top: -100px; left: 20px; padding: 12px 20px; background: #fff; border: 2px solid #245bd6; border-radius: 8px; z-index: 1000; }
.skip-link:focus { top: 8px; }
.welcome-panel { display: grid; grid-template-columns: 1.25fr 1fr; gap: 48px; align-items: center; padding: 48px; margin-bottom: 32px; background: #eaf1ff; border: 1px solid #dce6fa; border-radius: 20px; }
.eyebrow { color: #245bd6; font-size: 13px; font-weight: 700; letter-spacing: 3px; margin-bottom: 20px; }
.welcome-copy h1 { font-size: clamp(30px, 3.2vw, 44px); font-weight: 700; line-height: 1.35; letter-spacing: -1px; color: #162d53; margin: 0 0 18px; }
.welcome-description { max-width: 360px; font-size: 16px; line-height: 1.8; color: #536581; margin-bottom: 28px; }
.welcome-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 20px; }
.primary-action { display: inline-flex; align-items: center; gap: 20px; padding: 13px 20px; border-radius: 9px; background: #245bd6; color: #fff; font-weight: 600; }
.primary-action:hover { background: #1749b8; }
.secondary-action { color: #344e79; font-weight: 500; }
a:focus-visible { outline: 3px solid #7194e4; outline-offset: 4px; }
.learning-path { display: flex; flex-direction: column; gap: 12px; }
.path-step { display: flex; align-items: center; gap: 16px; padding: 20px; background: #fff; border: 1px solid #e2e9f5; border-radius: 12px; }
.step-icon { display: grid; place-items: center; width: 44px; height: 44px; background: #f0f5ff; color: #245bd6; border-radius: 12px; font-size: 22px; flex-shrink: 0; }
.path-step strong { color: #213c65; font-size: 16px; font-weight: 600; }
.path-step p { color: #65738a; margin: 4px 0 0; font-size: 13px; }
.step-number { margin-left: auto; color: #95a6be; font-size: 14px; letter-spacing: 1px; }
.welcome-banner { min-width: 0; }
@media (max-width: 900px) {
  .welcome-panel { padding: 32px; gap: 24px; }
  .welcome-panel.has-banner { grid-template-columns: 1fr; }
  .path-step { padding: 16px; gap: 12px; }
  .step-number { display: none; }
}
@media (max-width: 600px) {
  .public-content { padding: 24px 16px 32px; }
  .welcome-panel { grid-template-columns: 1fr; padding: 28px 24px; border-radius: 16px; }
  .welcome-description { font-size: 15px; }
  .welcome-actions { gap: 16px; }
  .learning-path { gap: 10px; }
  .path-step { padding: 14px; }
}
</style>
