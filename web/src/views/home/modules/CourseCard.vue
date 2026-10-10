<template>
  <button class="course-card-button" type="button" :aria-label="'查看课程：' + course.courseName" @click="$emit('open', course)">
    <span v-if="course.courseCover_url && !coverFailed" class="course-cover">
      <img :src="course.courseCover_url" alt="" loading="lazy" @error="coverFailed = true" />
    </span>
    <span class="course-info">
      <span class="course-category">{{ course.courseCategory_dictText || '公开课程' }}</span>
      <span class="course-title">{{ course.courseName }}</span>
      <span class="course-summary">{{ summary || '打开课程介绍，查看学习内容。' }}</span>
      <span class="course-meta">
        <span>{{ course.courseType_dictText || '课程学习' }}</span>
        <span class="course-action">了解课程 <a-icon type="arrow-right" /></span>
      </span>
    </span>
  </button>
</template>
<script>
import { courseSummaryText } from './courseSummaryText'

export default {
    name: 'CourseCard',
    props: { course: { type: Object, required: true } },
    data () { return { coverFailed: false } },
    computed: {
        summary () {
            // This remains interpolated text; course HTML is never executed in cards.
            return courseSummaryText(this.course.courseDesc)
        }
    },
    watch: { 'course.courseCover_url' () { this.coverFailed = false } }
}
</script>
<style scoped lang="less">
.course-card-button { display: flex; flex-direction: column; width: 100%; height: 100%; min-height: 250px; padding: 0; border: 1px solid #dce1e6; border-radius: 5px; text-align: left; background: #fff; color: #26313b; cursor: pointer; font: inherit; overflow: hidden; transition: border-color .15s ease, box-shadow .15s ease; }
.course-card-button:hover { border-color: #9caab5; box-shadow: 0 3px 10px rgba(30, 45, 58, .06); }
.course-card-button:focus-visible { outline: 2px solid #74256a; outline-offset: 4px; }
.course-cover { display: block; position: relative; width: 100%; padding-top: 48%; background: #f0f2f4; }
.course-cover img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; }
.course-info { display: flex; flex-direction: column; width: 100%; padding: 26px; flex: 1; }
.course-category { color: #7b5362; font-size: 11px; letter-spacing: .5px; margin-bottom: 16px; }
.course-title { display: block; font-size: 21px; font-weight: 600; color: #202c37; line-height: 1.5; overflow-wrap: anywhere; }
.course-summary {
  /* Autoprefixer 6 removes box-orient without this rule-local switch. */
  /* autoprefixer: off */
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
  max-height: 5.7em;
  flex-shrink: 0;
  overflow-wrap: anywhere;
  color: #687684;
  font-size: 13px;
  line-height: 1.9;
  margin: 14px 0 26px;
}
.course-meta { display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-top: auto; padding-top: 18px; border-top: 1px solid #edf0f2; color: #687684; font-size: 11px; }
.course-action { display: inline-flex; align-items: center; gap: 16px; color: #74256a; font-size: 12px; }
@media (max-width: 600px) { .course-card-button { min-height: 236px; } .course-info { padding: 24px; } .course-title { font-size: 20px; } }
@media (prefers-reduced-motion: reduce) { .course-card-button { transition: none; } }
</style>
