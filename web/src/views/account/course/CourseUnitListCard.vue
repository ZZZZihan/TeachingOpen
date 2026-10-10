<template>
  <main class="learning-entry">
    <router-link class="learning-text-link course-back" to="/teaching/mineCourse/cardList"><span aria-hidden="true">←</span> 我的课程</router-link>
    <header class="learning-heading course-heading">
      <div><p class="learning-eyebrow">COURSE OVERVIEW</p><h1>{{ courseInfo.courseName || '课程学习' }}</h1><p class="learning-lead">{{ learningSummary(courseInfo.courseDesc) || '从课程目录选择一个单元，查看学习内容、课堂资料与练习。' }}</p></div>
    </header>
    <section aria-labelledby="course-outline-title" :aria-busy="String(loading)">
      <div class="learning-section-heading"><h2 id="course-outline-title">课程目录</h2><span v-if="loaded" class="learning-count">{{ total }} 个单元</span></div>
      <div v-if="loading && !loaded" class="learning-state" role="status"><a-spin /><h3>正在加载课程目录</h3><p>为你准备学习内容。</p></div>
      <div v-else-if="!loaded && loadError" class="learning-state" role="alert"><p class="learning-eyebrow">暂时无法查看</p><h3>课程没有加载成功</h3><p>{{ loadError }}</p><button v-if="courseId" class="learning-button" type="button" @click="loadCourse">重新加载</button></div>
      <div v-else-if="loaded && !dataSource.length" class="learning-state"><p class="learning-eyebrow">课程准备中</p><h3>还没有学习单元</h3><p>老师发布内容后，会显示在这份课程目录中。</p></div>
      <ol v-else class="unit-outline">
        <li v-for="(unit, index) in dataSource" :key="unit.id" class="unit-row" :class="{ 'unit-selected': activeUnitId === unit.id }">
          <span class="unit-number" aria-hidden="true">{{ String(index + 1).padStart(2, '0') }}</span>
          <div class="unit-content">
            <h3><button type="button" @click="viewUnit(unit)">{{ unit.unitName }}</button></h3>
            <p class="unit-intro">{{ learningSummary(unit.unitIntro) || '打开本单元，查看老师准备的学习内容。' }}</p>
            <ul v-if="resourceLabels(unit).length" class="unit-resources" aria-label="本单元内容"><li v-for="label in resourceLabels(unit)" :key="label">{{ label }}</li></ul>
          </div>
          <img
            v-if="unit.unitCover && !failedCovers[unit.id]"
            class="unit-cover"
            :src="getFileAccessHttpUrl(unit.unitCover)"
            alt=""
            loading="lazy"
            @error="$set(failedCovers, unit.id, true)" />
          <button class="unit-open" type="button" :aria-label="'打开单元：' + unit.unitName" @click="viewUnit(unit)">开始学习 <span aria-hidden="true">→</span></button>
        </li>
      </ol>
      <div v-if="loaded && loadError" class="unit-page-error" role="alert"><p>{{ loadError }}</p><button class="learning-button" type="button" @click="loadMore">重试加载</button></div>
      <div v-if="loaded && dataSource.length < total && !loadError" class="unit-pagination"><p role="status">{{ loading ? '正在加载更多单元…' : '已显示 ' + dataSource.length + ' / ' + total + ' 个单元' }}</p><button class="learning-button" type="button" :disabled="loading" @click="loadMore">{{ loading ? '正在加载' : '加载更多单元' }}</button></div>
    </section>
    <UnitViewModal ref="unitViewModal" />
  </main>
</template>
<script>
import { getAction, getFileAccessHttpUrl } from '@/api/manage'
import UnitViewModal from './modules/UnitViewModal'
import { learningSummary } from './learningPresentation'
export default {
    name: 'CourseUnitListCard',
    components: { UnitViewModal },
    data () {
        return { courseInfo: {}, dataSource: [], total: 0, page: 0, loading: false, loaded: false, loadError: '', requestId: 0, failedCovers: {}, activeUnitId: '' }
    },
    computed: {
        courseId () { return typeof this.$route.query.id === 'string' ? this.$route.query.id.trim() : '' }
    },
    watch: { courseId: { immediate: true, handler () { this.loadCourse() } } },
    beforeDestroy () { this.requestId += 1 },
    methods: {
        getFileAccessHttpUrl,
        learningSummary,
        async loadCourse () {
            const requestId = ++this.requestId
            this.courseInfo = {}
            this.dataSource = []
            this.total = 0
            this.page = 0
            this.loaded = false
            this.loading = false
            this.loadError = ''
            this.failedCovers = {}
            this.activeUnitId = ''
            if (this.$refs.unitViewModal) this.$refs.unitViewModal.handleCancel()
            if (!this.courseId) {
                this.loadError = '课程地址不完整，请返回「我的课程」重新进入。'
                return
            }
            this.loading = true
            try {
                const [course, units] = await Promise.all([
                    getAction('/teaching/teachingCourse/queryById', { id: this.courseId }),
                    getAction('/teaching/teachingCourseUnit/mineUnit', { courseId: this.courseId, pageNo: 1, pageSize: 20 })
                ])
                if (requestId !== this.requestId) return
                if (!course.success || !course.result || !course.result.id) throw new Error('Invalid course response')
                this.validateUnits(units)
                this.courseInfo = course.result
                this.dataSource = units.result.records
                this.total = Number(units.result.total)
                this.page = 1
                this.loaded = true
            } catch (error) {
                if (requestId !== this.requestId) return
                this.loadError = '请检查网络后重试。如果课程已下架或尚未分配给你，请联系老师。'
            } finally {
                if (requestId === this.requestId) this.loading = false
            }
        },
        validateUnits (res) {
            const page = res && res.result
            if (!res || !res.success || !page || !Array.isArray(page.records) || page.records.some(unit => !unit || !unit.id) || page.total == null || !Number.isInteger(Number(page.total)) || Number(page.total) < 0) throw new Error('Invalid unit response')
        },
        async loadMore () {
            if (this.loading || !this.loaded || this.dataSource.length >= this.total) return
            const requestId = this.requestId
            this.loading = true
            this.loadError = ''
            try {
                const res = await getAction('/teaching/teachingCourseUnit/mineUnit', { courseId: this.courseId, pageNo: this.page + 1, pageSize: 20 })
                if (requestId !== this.requestId) return
                this.validateUnits(res)
                const ids = new Set(this.dataSource.map(unit => unit.id))
                const added = res.result.records.filter(unit => !ids.has(unit.id))
                if (!added.length && this.dataSource.length < Number(res.result.total)) throw new Error('No pagination progress')
                this.dataSource = this.dataSource.concat(added)
                this.total = Number(res.result.total)
                this.page += 1
            } catch (error) {
                if (requestId !== this.requestId) return
                this.loadError = '后续单元没有加载成功，已显示的内容仍可学习。请重试。'
            } finally {
                if (requestId === this.requestId) this.loading = false
            }
        },
        resourceLabels (unit) {
            return [[unit.courseVideo, '视频'], [unit.mediaContent, '课程内容'], [unit.courseCase, '案例'], [unit.coursePpt || unit.coursePlan, '学习资料'], [unit.courseWork_url, '课后练习']].filter(item => item[0]).map(item => item[1])
        },
        viewUnit (unit) {
            this.activeUnitId = unit.id
            this.$refs.unitViewModal.view(unit)
        }
    }
}
</script>
<style scoped lang="less">
@import './styles/learning-entry.less';
.course-back { display: inline-flex; gap: 12px; margin-bottom: 30px; }
.course-heading { border-bottom: 0; margin-bottom: 16px; padding: 0 0 24px; }
.course-heading .learning-lead { white-space: pre-line; display: -webkit-box; -webkit-line-clamp: 4; -webkit-box-orient: vertical; overflow: hidden; }
.unit-outline { list-style: none; padding: 0; margin: 0; border-top: 1px solid #cad3d8; }
.unit-row { display: flex; gap: 24px; align-items: center; border-bottom: 1px solid #dce2e5; padding: 28px 16px 28px 0; }
.unit-selected { background: #f5f7f7; }
.unit-number { font-size: 18px; color: #89979f; width: 36px; flex-shrink: 0; font-variant-numeric: tabular-nums; align-self: flex-start; padding-top: 4px; }
.unit-content { min-width: 0; flex: 1; }
.unit-content h3 { margin: 0 0 9px; line-height: 1.5; }
.unit-content h3 button { color: #172d38; padding: 0; border: 0; background: transparent; font: inherit; font-size: 20px; font-weight: 600; text-align: left; overflow-wrap: anywhere; cursor: pointer; }
.unit-content h3 button:hover { color: #a73542; }
.unit-intro { color: #62727c; line-height: 1.8; font-size: 13px; margin: 0 0 12px; overflow-wrap: anywhere; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.unit-resources { display: flex; gap: 8px 16px; flex-wrap: wrap; list-style: none; margin: 0; padding: 0; color: #687b86; font-size: 11px; }
.unit-resources li + li::before { content: '·'; margin-right: 16px; color: #9dabb2; }
.unit-cover { width: 120px; height: 76px; object-fit: cover; border-radius: 3px; }
.unit-open { display: inline-flex; gap: 20px; padding: 12px 0 12px 16px; border: 0; background: transparent; color: #a73542; font: inherit; font-size: 13px; font-weight: 600; white-space: nowrap; cursor: pointer; }
.unit-pagination, .unit-page-error { padding: 28px 0; text-align: center; color: #62727c; font-size: 12px; }
@media (max-width: 760px) { .unit-cover { display: none; } .unit-row { gap: 16px; } }
@media (max-width: 480px) { .unit-row { flex-wrap: wrap; padding: 22px 0; column-gap: 12px; row-gap: 8px; } .unit-number { width: 28px; font-size: 15px; } .unit-content { flex-basis: calc(100% - 40px); } .unit-content h3 button { font-size: 18px; } .unit-open { margin-left: 40px; padding-left: 0; gap: 16px; } .course-back { margin-bottom: 24px; } }
</style>
