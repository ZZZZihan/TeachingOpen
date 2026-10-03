<template>
  <div class="course-discovery">
    <header class="page-heading">
      <p class="eyebrow">COURSES</p><h1>探索课程</h1><p class="page-description">浏览人工智能与编程课程，找到适合自己的学习内容。</p>
    </header>
    <div class="course-body">
      <CourseFilters
        ref="courseFilters"
        :course-category="courseCategory"
        :course-type="courseType"
        :course-name="courseName"
        @category="handleChangeCategory"
        @type="handleChangeType"
        @search="onSearch"
        @reset="clearFilters"
      />
      <section class="course-results" aria-labelledby="course-results-title" :aria-busy="String(loading)">
        <div class="results-heading">
          <h2 id="course-results-title">{{ hasFilters ? '筛选结果' : '全部课程' }}</h2>
          <p role="status">{{ total == null ? (loading ? '正在查找课程…' : '') : '共 ' + total + ' 门课程' }}</p>
        </div>
        <div class="course-grid">
          <article v-for="item in datasource" :key="item.id" class="course-card">
            <CourseCard :course="item" @open="toDetail" />
          </article>
        </div>
        <div v-if="loading" class="loading-state" role="status"><a-spin /><span>正在加载课程…</span></div>
        <div v-if="!loading && loadError" class="message-state error-state" role="alert"><a-icon type="exclamation-circle" /><p>{{ loadError }}</p><button type="button" @click="getData">重新加载</button></div>
        <div v-if="!loading && !loadError && datasource.length === 0" class="message-state empty-state">
          <a-icon type="search" /><h3>{{ hasFilters ? '没有找到符合条件的课程' : '课程正在准备中' }}</h3>
          <p>{{ hasFilters ? '试试其他课程名称，或清除筛选条件。' : '当前还没有公开课程，欢迎稍后再来。' }}</p>
          <button v-if="hasFilters" type="button" @click="$refs.courseFilters.reset()">查看全部课程</button>
        </div>
        <a-button v-if="!loading && !loadError && hasMore && datasource.length > 0" class="load-more" @click="getData">加载更多课程</a-button>
      </section>
    </div>
    <j-modal
      :visible="showCourseDetail"
      :title="currentCourse.courseName"
      :width="560"
      @cancel="showCourseDetail = false"
      @ok="toCourse"
      okText="去上课"
      cancelText="关闭">
      <div v-if="currentCourse.courseDesc" class="course-description" v-html="currentCourse.courseDesc"></div>
      <p v-else class="description-empty">这门课程暂未提供简介。</p>
    </j-modal>
  </div>
</template>

<script>
import { getAction } from '@/api/manage'
import CourseFilters from './modules/CourseFilters'
import CourseCard from './modules/CourseCard'
export default {
    name: 'CourseList',
    components: { CourseFilters, CourseCard },
    data () {
        return {
            loading: false,
            datasource: [],
            total: null,
            page: 0,
            hasMore: true,
            loadError: '',
            requestId: 0,
            courseType: '',
            courseCategory: '',
            courseName: '',
            showCourseDetail: false,
            currentCourse: {}
        }
    },
    computed: {
        hasFilters () { return Boolean(this.courseName || this.courseCategory || this.courseType) }
    },
    created () {
        this.getData()
    },
    beforeDestroy () {
        this.requestId += 1
    },
    methods: {
        clearFilters () {
            this.courseName = ''
            this.courseCategory = ''
            this.courseType = ''
            return this.resetData()
        },
        onSearch (v) {
            this.courseName = v
            return this.resetData()
        },
        handleChangeCategory (v) {
            this.courseCategory = v
            return this.resetData()
        },
        handleChangeType (v) {
            this.courseType = v
            return this.resetData()
        },
        resetData () {
            // Invalidate the previous query before starting a new first-page request.
            this.requestId += 1
            this.loading = false
            this.page = 0
            this.hasMore = true
            this.datasource = []
            this.total = null
            this.loadError = ''
            return this.getData()
        },
        getData () {
            if (this.loading || !this.hasMore) {
                return
            }
            const requestId = ++this.requestId
            const nextPage = this.page + 1
            this.loading = true
            this.loadError = ''
            return getAction('/teaching/teachingCourse/getHomeCourse', {
                courseType: this.courseType,
                courseCategory: this.courseCategory,
                courseName: this.courseName,
                orderBy: 'time',
                pageSize: this._isMobile() ? 12 : 24,
                pageNo: nextPage
            }).then((res) => {
                if (requestId !== this.requestId) {
                    return
                }
                if (!res || !res.success || !res.result || !Array.isArray(res.result.records) ||
                    typeof res.result.total !== 'number' || !Number.isFinite(res.result.total) || res.result.total < 0) {
                    throw new Error('Invalid course response')
                }
                const records = res.result.records
                this.datasource = this.datasource.concat(records)
                // Only advance after success so retrying a failed request cannot skip a page.
                this.page = nextPage
                this.total = res.result.total
                this.hasMore = records.length > 0 && this.datasource.length < res.result.total
            }).catch(() => {
                if (requestId === this.requestId) {
                    this.loadError = '课程加载失败，请重试。'
                }
            }).finally(() => {
                if (requestId === this.requestId) {
                    this.loading = false
                }
            })
        },
        toDetail (item) {
            this.showCourseDetail = true
            this.currentCourse = item
        },
        toCourse () {
            this.$router.push('/teaching/mineCourse/courseUnitCard?id=' + encodeURIComponent(this.currentCourse.id))
        },
        _isMobile () {
            return (
                navigator.userAgent.match(
                    /(phone|pad|pod|iPhone|iPod|ios|Android|Mobile|BlackBerry|IEMobile|MQQBrowser|JUC|Fennec|wOSBrowser|BrowserNG|WebOS|Symbian|Windows Phone)/i
                ) != null
            )
        }
    }
}
</script>

<style lang="less" scoped>
.course-discovery { padding-top: 4px; }
.page-heading { margin-bottom: 36px; padding-bottom: 30px; border-bottom: 1px solid #dfe4e9; }
.eyebrow { margin: 0 0 12px; color: #74256a; font-size: 10px; font-weight: 600; letter-spacing: 2px; }
.page-heading h1 { font-size: 36px; line-height: 1.4; font-weight: 600; color: #202c37; margin: 0 0 14px; }
.page-description { color: #687684; margin: 0; line-height: 1.8; font-size: 14px; }
.course-body { display: grid; grid-template-columns: 220px minmax(0, 1fr); gap: 40px; align-items: start; }
.results-heading { display: flex; justify-content: space-between; align-items: center; gap: 16px; margin-bottom: 24px; }
.results-heading h2 { color: #202c37; font-size: 21px; font-weight: 600; margin: 0; }
.results-heading p { color: #7a8692; margin: 0; font-size: 12px; }
.course-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 24px; }
.course-card { min-width: 0; }
.loading-state { display: flex; justify-content: center; gap: 12px; align-items: center; padding: 36px; color: #687684; }
.message-state { text-align: center; padding: 48px 24px; background: #fff; border: 1px solid #dce1e6; border-radius: 5px; color: #687684; }
.message-state > .anticon { font-size: 26px; margin-bottom: 18px; color: #82909b; }
.message-state h3 { font-size: 18px; color: #344553; margin-bottom: 12px; }
.message-state button { color: #74256a; background: #fff; border: 1px solid #74256a; border-radius: 4px; padding: 9px 18px; cursor: pointer; }
.message-state button:focus-visible { outline: 2px solid #74256a; outline-offset: 4px; }
.error-state { margin-top: 24px; border-color: #d8b6a1; }
.error-state > .anticon { color: #a36a40; }
.load-more { display: block; margin: 32px auto 0; border-radius: 4px; }
.course-description { overflow-wrap: anywhere; line-height: 1.8; }
.course-description /deep/ img { max-width: 100%; height: auto; }
.description-empty { color: #687684; }
@media (max-width: 1000px) { .course-body { grid-template-columns: minmax(0, 1fr); gap: 28px; } .course-grid { gap: 20px; } }
@media (max-width: 600px) { .course-grid { grid-template-columns: minmax(0, 1fr); gap: 18px; } .page-heading { padding-bottom: 24px; margin-bottom: 24px; } .page-heading h1 { font-size: 30px; } .page-description { font-size: 13px; } }
</style>
