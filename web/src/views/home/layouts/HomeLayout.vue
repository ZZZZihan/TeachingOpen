<template>
  <div class="public-layout" :style="backgroundStyle">
    <a class="skip-link" href="#public-content">跳到主要内容</a>
    <Header />
    <main id="public-content" class="public-content" tabindex="-1">
      <section v-if="showIntro" class="welcome-panel" :class="{ 'has-banner': hasBanner }" aria-labelledby="welcome-title">
        <div class="welcome-copy">
          <p class="eyebrow">TEACHINGOPEN · 人工智能与编程</p>
          <h1 id="welcome-title">学好人工智能，<br /><span>从动手开始。</span></h1>
          <p class="welcome-description">选择课程，理解知识，完成自己的编程作品。<br />在这里，把学习落实到每一次实践。</p>
          <div class="welcome-actions">
            <router-link class="primary-action" to="/courseList">浏览课程 <a-icon type="arrow-right" /></router-link>
            <router-link class="secondary-action" :to="isLoggedIn ? '/teaching/mineCourse/cardList' : '/user/login'">{{ isLoggedIn ? '我的课程' : '登录，继续学习' }}</router-link>
          </div>
        </div>
        <Banner v-if="hasBanner" class="welcome-banner" />
        <div v-else class="learning-path" aria-label="学习路径">
          <p class="path-caption">从课程，到自己的作品</p>
          <p class="path-line">理解一个概念。</p>
          <p class="path-line">写出一段代码。</p>
          <p class="path-line">完成一件作品。</p>
        </div>
      </section>
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
.public-layout { min-height: 100vh; display: flex; flex-direction: column; background: #f7f8fa; background-size: 100% auto; color: #20252b; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif; }
.public-content { width: 100%; max-width: 1280px; margin: 0 auto; padding: 36px 40px 64px; flex: 1; }
.skip-link { position: absolute; top: -100px; left: 20px; padding: 12px 20px; background: #fff; border: 2px solid #bd424d; z-index: 1000; }
.skip-link:focus { top: 8px; }
.welcome-panel { display: grid; grid-template-columns: 1.6fr 1fr; gap: 64px; align-items: center; padding: 40px 48px; margin-bottom: 48px; background: #172d38; border-radius: 5px; }
.eyebrow { color: #bfcbd0; font-size: 11px; letter-spacing: 2px; margin: 0 0 24px; }
.welcome-copy h1 { font-size: clamp(36px, 3.6vw, 50px); font-weight: 600; line-height: 1.4; letter-spacing: -1px; color: #fff; margin: 0 0 24px; }
.welcome-copy h1 span { color: #fff; }
.welcome-description { font-size: 14px; line-height: 1.9; color: #b8c6ce; margin: 0 0 30px; }
.welcome-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 26px; }
.primary-action { display: inline-flex; align-items: center; gap: 28px; padding: 13px 22px; border: 1px solid #c84a55; border-radius: 4px; background: #c84a55; color: #fff; font-weight: 500; }
.primary-action:hover { background: #b43b46; border-color: #b43b46; color: #fff; }
.secondary-action { color: #fff; padding: 8px 0; border-bottom: 1px solid #768b98; font-size: 13px; }
.secondary-action:hover { color: #fff; border-color: #fff; }
a:focus-visible { outline: 2px solid #e47883; outline-offset: 5px; }
.learning-path { padding-left: 34px; border-left: 1px solid #40535e; }
.path-caption { margin: 0 0 28px; color: #df8d95; font-size: 10px; letter-spacing: 2px; }
.path-line { color: #c3d0d6; font-size: 20px; line-height: 1.8; font-weight: 400; margin: 0 0 16px; }
.path-line:last-child { margin: 0; }
.welcome-banner { min-width: 0; }
@media (max-width: 1000px) { .welcome-panel { gap: 32px; padding: 40px 36px; grid-template-columns: 1.4fr 1fr; } .welcome-copy h1 { font-size: 38px; } .learning-path { padding-left: 24px; } .path-line { font-size: 16px; } }
@media (max-width: 900px) { .public-content { padding: 28px 28px 48px; } .welcome-panel.has-banner { grid-template-columns: 1fr; } }
@media (max-width: 600px) { .public-content { padding: 22px 20px 40px; } .welcome-panel { grid-template-columns: 1fr; padding: 32px 26px; gap: 0; margin-bottom: 36px; } .welcome-copy h1 { font-size: 33px; line-height: 1.45; margin-bottom: 20px; } .eyebrow { font-size: 9px; letter-spacing: 1px; margin-bottom: 22px; } .welcome-description { font-size: 13px; margin-bottom: 26px; } .welcome-actions { gap: 20px; } .primary-action { padding: 11px 16px; gap: 16px; } .secondary-action { font-size: 12px; } .learning-path { display: none; } }
</style>
