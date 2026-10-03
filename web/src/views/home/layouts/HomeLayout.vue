<template>
  <div class="public-layout" :style="backgroundStyle">
    <a class="skip-link" href="#public-content">跳到主要内容</a>
    <Header />
    <main id="public-content" class="public-content" tabindex="-1">
      <section v-if="showIntro" class="welcome-panel" :class="{ 'has-banner': hasBanner }" aria-labelledby="welcome-title">
        <div class="welcome-copy">
          <p class="eyebrow">TIANGONG UNIVERSITY · 人工智能与编程</p>
          <h1 id="welcome-title">从课堂出发，<br /><span>让想法成为作品。</span></h1>
          <p class="welcome-description">选择课程，理解知识，完成自己的编程作品。<br />在这里，把学习落实到每一次实践。</p>
          <div class="welcome-actions">
            <router-link class="primary-action" to="/courseList">浏览课程 <a-icon type="arrow-right" /></router-link>
            <router-link class="secondary-action" :to="isLoggedIn ? '/teaching/mineCourse/cardList' : '/user/login'">{{ isLoggedIn ? '我的课程' : '登录，继续学习' }}</router-link>
          </div>
        </div>
        <Banner v-if="hasBanner" class="welcome-banner" />
        <figure v-else class="campus-view">
          <img
            v-if="!campusImageFailed"
            src="@/assets/tiangong/campus.jpg"
            width="499"
            height="333"
            alt="天津工业大学校园建筑与长廊"
            @error="campusImageFailed = true">
          <div v-else class="campus-image-fallback"><span>TIANGONG UNIVERSITY</span><p>教研相长<br>学能并进</p></div>
          <figcaption><span>天工 · 校园一隅</span><a href="https://news.tiangong.edu.cn/2022/0617/c7646a77757/page.htm" target="_blank" rel="noopener noreferrer">校园影像 ↗</a></figcaption>
        </figure>
      </section>
      <div v-if="showIntro" class="teaching-principle"><p>教研相长 <span>学能并进</span></p><span>在天工，把知识变成解决问题的能力。</span></div>
      <CoursePreview v-if="showIntro && $route.path === '/index'" />
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
import CoursePreview from '../modules/CoursePreview'
export default {
    name: 'HomeLayout',
    components: { Header, Banner, Footer, CoursePreview },
    data () { return { campusImageFailed: false } },
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
.public-layout { min-height: 100vh; display: flex; flex-direction: column; background: #fcfbfa; background-size: 100% auto; color: #252129; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif; }
.public-content { width: 100%; max-width: 1280px; margin: 0 auto; padding: 44px 40px 64px; flex: 1; }
.skip-link { position: absolute; top: -100px; left: 20px; padding: 12px 20px; background: #fff; border: 2px solid #74256a; z-index: 1000; }
.skip-link:focus { top: 8px; }
.welcome-panel { display: grid; grid-template-columns: 1.08fr 1fr; gap: 64px; align-items: center; padding: 12px 0 38px; }
.eyebrow { color: #74256a; font-size: 10px; letter-spacing: 1.8px; margin: 0 0 26px; }
.welcome-copy h1 { font-size: clamp(34px, 3.2vw, 46px); font-weight: 500; line-height: 1.45; letter-spacing: -1px; color: #29222b; margin: 0 0 22px; }
.welcome-copy h1 span { color: #74256a; }
.welcome-description { font-size: 14px; line-height: 1.9; color: #6e6570; margin: 0 0 30px; }
.welcome-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 26px; }
.primary-action { display: inline-flex; align-items: center; gap: 28px; padding: 13px 22px; border: 1px solid #74256a; border-radius: 2px; background: #74256a; color: #fff; font-weight: 500; }
.primary-action:hover { background: #592052; border-color: #592052; color: #fff; }
.secondary-action { color: #534757; padding: 8px 0; border-bottom: 1px solid #baaeb9; font-size: 13px; }
.secondary-action:hover { color: #74256a; border-color: #74256a; }
a:focus-visible { outline: 2px solid #74256a; outline-offset: 5px; }
.campus-view { min-width: 0; margin: 0; }
.campus-view img { display: block; width: 100%; height: auto; aspect-ratio: 499 / 333; object-fit: cover; }
.campus-view figcaption { display: flex; justify-content: space-between; gap: 15px; color: #746d75; font-size: 11px; margin-top: 14px; }
.campus-view figcaption a { color: #746d75; }
.campus-image-fallback { aspect-ratio: 499 / 333; background: #f1e8ef; color: #74256a; display: flex; flex-direction: column; justify-content: center; padding: 36px; }
.campus-image-fallback span { font-size: 11px; letter-spacing: 2px; }
.campus-image-fallback p { color: #74256a; font-family: 'Songti SC', SimSun, serif; font-size: 32px; line-height: 1.7; margin: 20px 0 0; }
.teaching-principle { padding: 22px 0; margin-bottom: 42px; border-top: 1px solid #e4dce3; border-bottom: 1px solid #e4dce3; display: flex; align-items: center; justify-content: space-between; gap: 20px; }
.teaching-principle p { margin: 0; font-family: 'Songti SC', SimSun, serif; color: #74256a; letter-spacing: 4px; font-size: 18px; }
.teaching-principle p span { margin-left: 24px; }
.teaching-principle > span { color: #79717a; font-size: 12px; }
.welcome-banner { min-width: 0; }
@media (max-width: 1000px) { .welcome-panel { gap: 32px; grid-template-columns: 1fr 1fr; } .welcome-copy h1 { font-size: 34px; } .eyebrow { letter-spacing: 1px; } }
@media (max-width: 900px) { .public-content { padding: 32px 28px 48px; } .welcome-panel.has-banner { grid-template-columns: 1fr; } .teaching-principle > span { max-width: 190px; line-height: 1.8; } }
@media (max-width: 600px) { .public-content { padding: 28px 20px 40px; } .welcome-panel { grid-template-columns: 1fr; padding: 0 0 28px; gap: 32px; } .welcome-copy h1 { font-size: 34px; margin-bottom: 18px; } .eyebrow { font-size: 9px; margin-bottom: 18px; } .welcome-description { font-size: 13px; margin-bottom: 24px; } .welcome-actions { gap: 20px; } .primary-action { padding: 11px 16px; gap: 16px; } .secondary-action { font-size: 12px; } .teaching-principle { align-items: flex-start; flex-direction: column; gap: 12px; margin-bottom: 32px; } .teaching-principle > span { max-width: none; } .teaching-principle p { font-size: 17px; letter-spacing: 3px; } .teaching-principle p span { margin-left: 16px; } }
</style>
