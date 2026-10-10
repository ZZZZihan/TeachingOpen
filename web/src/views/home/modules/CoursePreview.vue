<template>
  <section class="course-preview" aria-labelledby="preview-title" :aria-busy="String(loading)">
    <div class="preview-heading"><div><h2 id="preview-title">公开课程</h2><p>查看课程内容，找到适合自己的学习起点。</p></div><router-link to="/courseList">全部课程 <a-icon type="arrow-right" /></router-link></div>
    <div v-if="loading" class="preview-state" role="status"><a-spin /> 正在加载课程…</div>
    <div v-else-if="error" class="preview-state" role="alert"><p>课程暂时无法加载。</p><button type="button" @click="loadCourses">重新加载课程</button></div>
    <p v-else-if="!courses.length" class="preview-state">公开课程正在准备中，欢迎稍后查看。</p>
    <div v-else class="preview-grid"><article v-for="course in courses" :key="course.id"><CourseCard :course="course" @open="currentCourse = $event; detailVisible = true" /></article></div>
    <j-modal
      :visible="detailVisible"
      :title="currentCourse.courseName"
      :width="560"
      @cancel="detailVisible = false"
      @ok="enterCourse"
      okText="去上课"
      cancelText="关闭">
      <div v-if="currentCourse.courseDesc" class="course-description" v-html="currentCourse.courseDesc"></div><p v-else>这门课程暂未提供简介。</p>
    </j-modal>
  </section>
</template>
<script>
import { getAction } from '@/api/manage'
import CourseCard from './CourseCard'
export default {
    components: { CourseCard },
    data () { return { courses: [], loading: false, error: false, requestId: 0, currentCourse: {}, detailVisible: false } },
    created () { this.loadCourses() },
    beforeDestroy () { this.requestId += 1 },
    methods: {
        loadCourses () {
            if (this.loading) return
            const requestId = ++this.requestId
            this.loading = true
            this.error = false
            return getAction('/teaching/teachingCourse/getHomeCourse', { pageNo: 1, pageSize: 3, orderBy: 'time' })
                .then(result => {
                    if (requestId !== this.requestId) return
                    if (!result || !result.success || !result.result || !Array.isArray(result.result.records) ||
                        result.result.records.some(course => !course || typeof course.id !== 'string' || !course.id || typeof course.courseName !== 'string')) {
                        throw new Error('Invalid course preview')
                    }
                    this.courses = result.result.records
                }).catch(() => { if (requestId === this.requestId) this.error = true })
                .finally(() => { if (requestId === this.requestId) this.loading = false })
        },
        enterCourse () { this.$router.push('/teaching/mineCourse/courseUnitCard?id=' + encodeURIComponent(this.currentCourse.id)) }
    }
}
</script>
<style scoped lang="less">
.preview-heading { display: flex; align-items: center; justify-content: space-between; gap: 24px; margin-bottom: 24px; }
.preview-heading h2 { font-size: 25px; font-weight: 600; color: #202c37; margin: 0 0 10px; }
.preview-heading p { color: #687684; font-size: 13px; margin: 0; line-height: 1.8; }
.preview-heading > a { display: inline-flex; align-items: center; gap: 16px; color: #146fc2; font-size: 13px; white-space: nowrap; }
.preview-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 24px; }
.preview-grid article { min-width: 0; }
.preview-state { padding: 36px 24px; background: #fff; border: 1px solid #e1e5e9; color: #687684; text-align: center; line-height: 1.8; }
.preview-state button { border: 1px solid #146fc2; background: #fff; border-radius: 4px; padding: 8px 16px; color: #146fc2; cursor: pointer; }
a:focus-visible, button:focus-visible { outline: 2px solid #146fc2; outline-offset: 4px; }
.course-description { overflow-wrap: anywhere; line-height: 1.8; }
.course-description /deep/ img { max-width: 100%; height: auto; }
@media (max-width: 1000px) { .preview-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 20px; } }
@media (max-width: 600px) { .preview-heading { align-items: flex-start; gap: 14px; } .preview-heading h2 { font-size: 23px; } .preview-heading p { max-width: 200px; font-size: 12px; } .preview-heading > a { margin-top: 7px; gap: 10px; font-size: 12px; } .preview-grid { grid-template-columns: minmax(0, 1fr); gap: 18px; } }
</style>
