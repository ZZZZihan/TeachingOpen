<template>
  <main class="learning-entry">
    <header class="learning-heading">
      <div><p class="learning-eyebrow">MY LEARNING</p><h1>我的课程</h1><p class="learning-lead">从课堂到实践，按自己的节奏探索与学习。</p></div>
      <router-link class="learning-text-link" to="/courseList">探索更多课程 <span aria-hidden="true">↗</span></router-link>
    </header>
    <section aria-labelledby="my-courses-title" :aria-busy="String(loading)">
      <div class="learning-section-heading"><h2 id="my-courses-title">课程与课堂</h2><span v-if="loaded" class="learning-count">{{ dataSource.length }} 门课程</span></div>
      <div v-if="loading" class="learning-state" role="status"><a-spin /><h3>正在加载你的课程</h3><p>课程内容即将呈现。</p></div>
      <div v-else-if="loadError" class="learning-state" role="alert"><p class="learning-eyebrow">暂时无法加载</p><h3>课程没有加载成功</h3><p>{{ loadError }}</p><button class="learning-button" type="button" @click="getCourseList">重新加载</button></div>
      <div v-else-if="loaded && !dataSource.length" class="learning-state"><p class="learning-eyebrow">开始学习</p><h3>还没有可学习的课程</h3><p>班级分配课程后会出现在这里，也可以先浏览公开课程。</p><router-link class="learning-button" to="/courseList">探索课程</router-link></div>
      <div v-else class="my-course-grid">
        <article v-for="course in dataSource" :key="course.id" class="my-course">
          <div v-if="course.courseCover && !failedCovers[course.id]" class="my-course-cover"><img :src="getFileAccessHttpUrl(course.courseCover)" alt="" loading="lazy" @error="$set(failedCovers, course.id, true)" /></div>
          <div class="my-course-content">
            <p class="learning-eyebrow">{{ course.courseCategory_dictText || '课程学习' }}</p>
            <h3><router-link :to="courseLocation(course)">{{ course.courseName }}</router-link></h3>
            <p class="my-course-summary">{{ learningSummary(course.courseDesc) || '进入课程，查看学习单元与课堂资料。' }}</p>
            <div class="my-course-footer"><button class="learning-text-link" type="button" :aria-label="'课程介绍：' + course.courseName" @click="toDetail(course)">课程介绍</button><router-link class="learning-course-action" :to="courseLocation(course)" :aria-label="'进入课程：' + course.courseName">进入课程 <span aria-hidden="true">→</span></router-link></div>
          </div>
        </article>
      </div>
    </section>
    <j-modal :visible="showCourseDetail" :title="currentCourse.courseName" :width="720" :footer="null" @cancel="showCourseDetail = false">
      <div v-if="currentCourse.courseDesc" class="learning-rich-description" v-html="currentCourse.courseDesc"></div>
      <p v-else>这门课程暂未提供简介。</p>
    </j-modal>
  </main>
</template>
<script>
import { getAction, getFileAccessHttpUrl } from '@/api/manage'
import { learningSummary, courseLocation } from './learningPresentation'
export default {
    name: 'MineCourseList',
    data () {
        return { dataSource: [], loading: false, loaded: false, loadError: '', requestId: 0, failedCovers: {}, showCourseDetail: false, currentCourse: {} }
    },
    created () { this.getCourseList() },
    beforeDestroy () { this.requestId += 1 },
    methods: {
        getFileAccessHttpUrl,
        learningSummary,
        courseLocation,
        async getCourseList () {
            if (this.loading) return
            const requestId = ++this.requestId
            this.loading = true
            this.loaded = false
            this.loadError = ''
            try {
                const res = await getAction('/teaching/teachingCourse/mineCourse', {})
                if (requestId !== this.requestId) return
                if (!res.success || !Array.isArray(res.result) || res.result.some(course => !course || !course.id)) throw new Error('Invalid course response')
                this.dataSource = res.result
                this.failedCovers = {}
                this.loaded = true
            } catch (error) {
                if (requestId !== this.requestId) return
                this.loadError = '请检查网络后重试。如果仍无法加载，请联系老师或管理员。'
            } finally {
                if (requestId === this.requestId) this.loading = false
            }
        },
        toDetail (course) { this.currentCourse = course; this.showCourseDetail = true }
    }
}
</script>
<style scoped lang="less">
@import './styles/learning-entry.less';
.my-course-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 24px; }
.my-course { min-width: 0; display: flex; flex-direction: column; border: 1px solid #dce2e5; background: #fff; border-radius: 4px; overflow: hidden; }
.my-course-cover { aspect-ratio: 2.6; background: #edf0f1; overflow: hidden; }
.my-course-cover img { width: 100%; height: 100%; object-fit: cover; }
.my-course-content { display: flex; flex-direction: column; padding: 28px; flex: 1; }
.my-course h3 { font-size: 23px; line-height: 1.5; margin: 4px 0 12px; overflow-wrap: anywhere; }
.my-course h3 a { color: #172d38; }
.my-course-summary { color: #5b6a73; line-height: 1.9; margin-bottom: 28px; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; overflow-wrap: anywhere; }
.my-course-footer { margin-top: auto; padding-top: 20px; border-top: 1px solid #e8ecee; display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.learning-course-action { color: #a73542; font-weight: 600; display: inline-flex; align-items: center; gap: 22px; }
.learning-rich-description { overflow-wrap: anywhere; }
.learning-rich-description /deep/ img { max-width: 100%; height: auto; }
@media (max-width: 640px) { .my-course-grid { grid-template-columns: minmax(0, 1fr); gap: 18px; } .my-course-content { padding: 22px; } .my-course h3 { font-size: 21px; } }
</style>
